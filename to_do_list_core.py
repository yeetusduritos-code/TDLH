# imports programs for use
import sqlite3
import os
from datetime import datetime, timedelta

def add_task(cursor, conn):

    print("\n--- Display Layout Position ---")
    print("1. Weekday List\n2. Weekly List\n3. Monthly List\n4. Yearly List\n5. Custom")
    frame_choice = input("Choose (1-5): ")
    time_frame = ['day', 'week', 'month', 'year', 'custom'][int(frame_choice) - 1]

    if time_frame != "custom":
        target_date = input("Target date for this item (YYYY-MM-DD): ")
    else:
        add_custom_task(cursor, conn)
        return
    
    task = input("What is your task/habit ")

    category = get_or_create_category(cursor)
    
    print("\n--- Recurrence Type ---")
    print("1. Once\n2. Daily\n3. Weekly List\n4. Monthly List\n5. Custom Interval")
    recurrence_choice = input("Choose (1-5): ")
    recurrence_type = ["once", "daily", "weekly", "monthly", "custom_interval"][int(recurrence_choice) - 1]

    interval_days = 0
    if recurrence_type == "custom_interval":
        interval_days = int(input("Repeat every how many days? "))

    end_date = input("End date for recurrence (YYYY-MM-DD) [Press Enter for never]: ") or None
    
    custom_list = None
    
    cursor.execute(
    "INSERT INTO tasks (name, category, time_frame, target_date, recurrence_type, interval_days, end_date, custom_list) VALUES (?,?,?,?,?,?,?,?)",
    (task, category, time_frame, target_date, recurrence_type, interval_days, end_date, custom_list)
    )
    conn.commit()

    print("Task created with ID:", cursor.lastrowid)

def add_custom_task(cursor, conn):

    time_frame = "custom"
    category = get_or_create_category(cursor)
    target_date = None
    recurrence_type = "once"
    interval_days = 0
    end_date = None

    task = input("What is your task/habit ")
    custom_list = input("What custom list is this task/habit part off ")

    cursor.execute(
    "INSERT INTO tasks (name, category, time_frame, target_date, recurrence_type, interval_days, end_date, custom_list) VALUES (?,?,?,?,?,?,?,?)",
    (task, category, time_frame, target_date, recurrence_type, interval_days, end_date, custom_list)
    )
    conn.commit()

    print("Task created with ID:", cursor.lastrowid)

def inspect_task(cursor, conn):
    task_id = input("ID of task to inspect: ")

    cursor.execute(
        "SELECT * FROM tasks WHERE id = ?",
        (int(task_id),)
    )

    print("Task settings:", cursor.fetchone())

    comp_rec = input("Do you want to see the completion records? (Y/n) ")

    # Show completion records for this specific task
    if comp_rec.lower() != "n":
        cursor.execute("SELECT completed_date FROM task_completions WHERE task_id = ?", (int(task_id),))
        print("Historical Completion Logs:", cursor.fetchall())

    else:
        print("Operation cancelled")


def inspect_tasks(cursor, conn):
    cursor.execute("SELECT id, name, category, time_frame, recurrence_type FROM tasks")
    for t in cursor.fetchall():
        print(f"ID: {t[0]} | Name: {t[1]} | Cat: {t[2]} | Layout: {t[3]} | Recur: {t[4]}")


def remove_task(cursor, conn):
    # DELETE FROM = remove rows
    # WHERE = very important (otherwise deletes everything)

    task = input("ID of task to remove: ")

    cursor.execute(
        "SELECT * FROM tasks WHERE id = ?",
        (int(task),)
    )
    one_task = cursor.fetchone()

    if not one_task:
        print("No task found")
        return


    print("\nSelected task: ", one_task)
    yn = input("Are you sure you want to remove this task y/N ")


    if yn.lower() == "y":

        cursor.execute("DELETE FROM task_completions WHERE task_id = ?", (int(task),))
        cursor.execute("DELETE FROM tasks WHERE id = ?",(int(task),))

        print("Task",task,"and all associated logs have been removed")

    else:
        print("Operation cancelled")

    conn.commit()

def edit_task(cursor, conn):
    task = input("Id of task to edit: ")

    cursor.execute(
        "SELECT * FROM tasks WHERE id = ?",
        (int(task),)
    )

    one_task = cursor.fetchone()
    if not one_task:
        print("Task not found.")
        return

    print("This is the task you selected:", one_task)
    yn = input("Are you sure you want to edit this task y/N ")

    if yn.lower() == "y":
        print("\n1. name\n2. category\n3. time_frame & target_date\n4. target_date\n5. recurrence settings\n6. interval_days\n7. end_date\n8. custom_list")
        
        edit_select = int(input("What do you want to edit on this task choose (1-8): "))
        
        edit_choice = ["name", "category", "time_frame", "target_date", "recurrence_type", "interval_days", "end_date", "custom_list"][edit_select - 1]

        # This variable will hold our value for the single-column updates at the bottom
        edit_value = None

        if edit_select == 1:
            edit_value = input("What is the new name of the task: ")

        elif edit_select == 2:
            edit_value = get_or_create_category(cursor)

        elif edit_select == 3:
            print("\nSet new \n--- Display Layout Position ---")
            print("1. Weekday List\n2. Weekly List\n3. Monthly List\n4. Yearly List\n5. Custom Board")
            frame_choice = input("Choose [1-5]: ")
            time_frame = ['day','week', 'month', 'year', 'custom'][int(frame_choice) - 1]

            if time_frame != "custom":
                target_date = input("Target date for this item (YYYY-MM-DD): ")
            else:
                target_date = None

            cursor.execute(
                "UPDATE tasks SET time_frame = ?, target_date = ? WHERE id = ?",
                (time_frame, target_date, int(task))
            )
            print("Layout settings updated successfully!")

        elif edit_select == 4:
            edit_value = input("Target date for this item (YYYY-MM-DD): ")

        elif edit_select == 5:
            print("\nSet new \n--- Recurrence Type ---")
            print("\n1. Once\n2. Daily\n3. Weekly List\n4. Monthly List\n5. Custom Interval")
            recurrence_choice = input("Choose (1-5): ")
            recurrence_type = ["once", "daily", "weekly", "monthly", "custom_interval"][int(recurrence_choice) - 1]

            interval_days = 0
            if recurrence_type == "custom_interval":
                interval_days = int(input("Repeat every how many days? "))  
            
            end_date = input("End date for recurrence (YYYY-MM-DD) [Press Enter for never]: ") or None
            
            cursor.execute(
                "UPDATE tasks SET recurrence_type = ?, interval_days = ?, end_date = ? WHERE id = ?",
                (recurrence_type, interval_days, end_date, int(task))
            )
            print("Recurrence parameters updated successfully!")

        elif edit_select == 6:
            edit_value = int(input("Repeat every how many days? "))

        elif edit_select == 7:
            edit_value = input("End date for recurrence (YYYY-MM-DD) [Press Enter for never]: ") or None

        elif edit_select == 8:
            edit_value = input("What cutom list should your task be part of? [Press Enter for none]") or None
        
        # 4. MASTER ENGINE LOGIC (Runs for options 1, 2, 4, 6, and 7)
        if edit_select in [1, 2, 4, 6, 7, 8]: # safely allows None strings for skip options
            cursor.execute(
                f"UPDATE tasks SET {edit_choice} = ? WHERE id = ?",
                (edit_value, int(task))
            )
            print(f"Property '{edit_choice}' modified successfully.")
        
        conn.commit()
    else:
        print("Operation cancelled")




def mark_complete_task(cursor, conn):
    task = input("Id of completed task ")

    cursor.execute(
        "SELECT * FROM tasks WHERE id = ?",
        (int(task),)
    )

    one_task = cursor.fetchone()
    print("This is the task you selected:")
    print(one_task)

    yn = input("Are you sure you want to complete this task y/N ")


    if yn.lower() == "y":

        completed_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            "INSERT INTO task_completions (task_id, completed_date) VALUES (?, ?)",
            (int(task), completed_dt)
        )
        print("Task",task,"completed!")

    else:
        print("operation cancelled")
    
    conn.commit()

def mark_incomplete_task(cursor, conn):

    user_input = input("Id of task and date to remove (ID YYYY-MM-DD): ").strip()
    
    #Split the string by its space character into a list
    parts = user_input.split()
    
    if len(parts) < 2 or len(parts) > 2:
        print("Error: You must type BOTH the ID and the Date separated by a space.")
        return
        
    task_id = int(parts[0])   # The first part is your ID number
    target_date = parts[1]    # The second part is your YYYY-MM-DD date string

    # LIKE with a '%' wildcard because timestamps have hours/minutes/seconds attached
    cursor.execute(
        "SELECT * FROM task_completions WHERE task_id = ? AND completed_date LIKE ?",
        (task_id, f"{target_date}%")
    )

    one_log = cursor.fetchone()
    if not one_log:
        print(f"No completion log found for Task ID {task_id} on {target_date}.")
        return

    print("\nThis is the completion log you selected:")
    print(f"Log ID: {one_log[0]} | Task ID: {one_log[1]} | Timestamp: {one_log[2]}")

    yn = input("Are you sure you want to delete this completion record? y/N ")

    if yn.lower() == "y":
        # 4. Use DELETE to wipe out that exact specific log row
        cursor.execute(
            "DELETE FROM task_completions WHERE id = ?",
            (one_log[0],) # Targets the unique ID of the log row itself
        )
        print(f"Completion record for task {task_id} on {target_date} removed successfully.")
        conn.commit()

    else:
        print("Operation cancelled")

def show_list(cursor, conn, target_date=None):
    
    list_choice = input("What list would you like to view? (day(d), week(w), month(m), year(y), or custom(c)): ")

    if list_choice.lower() != "c":
        target_date = input("What date would you like to view? (YYYY-MM-DD)[Enter for today] ") or None

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if list_choice.lower() == "d":
        print("--- Daily list ---")
        print("Todays date and time", current_time)

        # 1. Handle the default: Use today's date if the user didn't type one in
        if target_date is None:
            target_date = datetime.now().strftime("%Y-%m-%d") # e.g., "2026-06-26"

        print(f"\n--- Fetching tasks for date: {target_date} ---")

        # 2. THE SQL QUERY
        # This selects tasks where the target_date matches exactly, 
        # OR daily tasks that started on or before the selected date (ignoring finished ones)
        cursor.execute("""
            SELECT id, name, category, recurrence_type 
            FROM tasks 
            WHERE (target_date = ? AND time_frame = 'day' AND recurrence_type = 'once')
            OR (recurrence_type = 'daily' AND target_date <= ? AND (end_date IS NULL OR end_date >= ?))
        """, (target_date, target_date, target_date))
        
        todays_tasks = cursor.fetchall()

        # 3. Display the raw results
        if not todays_tasks:
            print("No tasks found scheduled for this day.")
        else:
            for task in todays_tasks:
                # task is a tuple: (id, name, category, recurrence_type)
                print(f"ID: {task[0]} | Name: {task[1]} [{task[3]}]")

    elif list_choice.lower() == "w":

        print("--- This weeks list ---")
        print("Todays date and time", current_time)

        # 1. Handle the default: Use today's date if the user didn't type one in
        if target_date is None:
            target_date = datetime.now().strftime("%Y-%m-%d") # e.g., "2026-06-26"
        else:
            # If a full timestamp was passed, extract just the date part
            target_date = target_date.split()[0]

        # Convert the target date string into a real object to calculate week boundaries
        target_dt = datetime.strptime(target_date, "%Y-%m-%d")
        
        # target_dt.weekday() returns 0 for Monday, 1 for Tuesday... 6 for Sunday
        # This math finds the Monday and Sunday of that target date's week
        start_of_week = (target_dt - timedelta(days=target_dt.weekday())).strftime("%Y-%m-%d")
        end_of_week = (target_dt + timedelta(days=6 - target_dt.weekday())).strftime("%Y-%m-%d")

        print(f"Week Window: {start_of_week} to {end_of_week}")
        print(f"\n--- Fetching tasks for this week: {target_date} ---")

        # 2. THE SQL QUERY
        # This selects tasks where the target_date matches exactly, 
        # OR daily tasks that started on or before the selected date (ignoring finished ones)
        cursor.execute("""
            SELECT id, name, category, recurrence_type 
            FROM tasks 
            WHERE (target_date >= ? AND target_date <= ? AND time_frame = 'week' AND recurrence_type = 'once')
            OR (recurrence_type = 'weekly' AND target_date <= ? AND (end_date IS NULL OR end_date >= ?) AND time_frame = 'week')
        """, (start_of_week, end_of_week, end_of_week, start_of_week))

        weekly_tasks = cursor.fetchall()

        # 3. Display the raw results
        if not weekly_tasks:
            print("No tasks found scheduled for this week.")
        else:
            for task in weekly_tasks:
                # task is a tuple: (id, name, category, recurrence_type)
                print(f"ID: {task[0]} | Name: {task[1]} [{task[3]}]")

    elif list_choice.lower() == "m":
        print("--- This months list ---")
        print("Todays date and time", current_time)

        # 1. Handle the default: Use today's date if the user didn't type one in
        if target_date is None:
            target_date = datetime.now().strftime("%Y-%m-%d") # e.g., "2026-06-26"
        else:
            # If a full timestamp was passed, extract just the date part
            target_date = target_date.split()[0]
        
        current_month_str = target_date[:7]
        current_month_ub = current_month_str + "-31"
        current_month_lb = current_month_str + "-01"

        print(f"\n--- Fetching tasks for this month: {target_date} ---")

        # 2. THE SQL QUERY
        # This selects tasks where the target_date matches exactly, 
        # OR daily tasks that started on or before the selected date (ignoring finished ones)
        cursor.execute("""
            SELECT id, name, category, recurrence_type 
            FROM tasks 
            WHERE (target_date LIKE ? AND time_frame = 'month' AND recurrence_type = 'once')
            OR (target_date <= ? AND (end_date IS NULL OR end_date >= ?) AND time_frame = 'month' AND recurrence_type = 'monthly')
        """, (f"{current_month_str}%", current_month_ub, current_month_lb))

        monthly_tasks = cursor.fetchall()

        # 3. Display the raw results
        if not monthly_tasks:
            print("No tasks found scheduled for this month.")
        else:
            for task in monthly_tasks:
                # task is a tuple: (id, name, category, recurrence_type)
                print(f"ID: {task[0]} | Name: {task[1]} [{task[3]}]")
    

    elif list_choice.lower() == "y":
        print("--- This years list ---")
        print("Todays date and time", current_time)

        # 1. Handle the default: Use today's date if the user didn't type one in
        if target_date is None:
            target_date = datetime.now().strftime("%Y-%m-%d") # e.g., "2026-06-26"
        else:
            target_date = target_date.split()[0]

        print(f"\n--- Fetching tasks for this year: {target_date} ---")

        current_year_str = target_date[:4] # e.g., "2026"
        current_year_ub = current_year_str + "-12-31"
        current_year_lb = current_year_str + "-01-01"

        # 2. THE SQL QUERY
        # This selects tasks where the target_date matches exactly, 
        # OR daily tasks that started on or before the selected date (ignoring finished ones)
        cursor.execute("""
            SELECT id, name, category, recurrence_type 
            FROM tasks 
            WHERE (target_date LIKE ? AND time_frame = 'year' AND recurrence_type = 'once')
            OR (recurrence_type = 'yearly' AND time_frame = 'year' AND target_date <= ? AND (end_date IS NULL OR end_date >= ?))
        """, (f"{current_year_str}%", current_year_ub, current_year_lb))

        yearly_tasks = cursor.fetchall()

        # 3. Display the raw results
        if not yearly_tasks:
            print("No tasks found scheduled for this year.")
        else:
            for task in yearly_tasks:
                # task is a tuple: (id, name, category, recurrence_type)
                print(f"ID: {task[0]} | Name: {task[1]} [{task[3]}]")

    elif list_choice.lower() == "c":
        print("--- Custom lists ---")

        # 1. Query the DB for unique categories that aren't empty/NULL
        cursor.execute("SELECT DISTINCT custom_list FROM tasks WHERE custom_list IS NOT NULL AND custom_list != ''")
        results = cursor.fetchall()

        if results == None:
            print("There are currently no custom lists")
            return

        print("Which custom list would you like to view")

        for i, v in enumerate(results):
            print(f"{i + 1}: {v[0]}")

        try:
            c_list = int(input("(Enter corrisponding number) ")) -1
            if c_list < 0 or c_list >= len(results):
                print("please pick a valid number")
                return
            selected_list = results[c_list][0]

        except ValueError:
            print("please pick a valid number")
            return

        cursor.execute("""
            SELECT id, name, category 
            FROM tasks 
            WHERE (custom_list = ?)
        """, (selected_list,))
        custom_tasks = cursor.fetchall()
        print(f"--- {selected_list} ---")
        for task in custom_tasks:
            # task is a tuple: (id, name, category, recurrence_type)
            print(f"ID: {task[0]} | Name: {task[1]}")

    else:
        print("You did not select type a vaild viewing option")

        



#AI generated code
def get_or_create_category(cursor):
    """
    Fetches existing categories from the DB, lets the user select one,
    or allows them to type out a brand-new one.
    """
    print("\n--- Assign Category Tag ---")
    
    # 1. Query the DB for unique categories that aren't empty/NULL
    cursor.execute("SELECT DISTINCT category FROM tasks WHERE category IS NOT NULL AND category != ''")
    results = cursor.fetchall()
    
    # Flatten the list of tuples into a simple list of strings: ['Stretching', 'Work']
    existing_categories = [row[0] for row in results]
    
    # 2. If no categories exist yet, go straight to creation
    if not existing_categories:
        new_cat = input("No categories found. Enter a new category tag (or press Enter to skip): ").strip()
        return new_cat if new_cat else None

    # 3. Display the menu of existing tags
    print("Select an existing category or create a new one:")
    for index, cat in enumerate(existing_categories, start=1):
        print(f"{index}. {cat}")
    print(f"{len(existing_categories) + 1}. [Create New Category]")
    print(f"{len(existing_categories) + 2}. [Skip / No Category]")

    choice = input("Choice: ").strip()
    
    try:
        choice_idx = int(choice)
        
        # User picked an existing category
        if 1 <= choice_idx <= len(existing_categories):
            return existing_categories[choice_idx - 1]
            
        # User picked "[Create New Category]"
        elif choice_idx == len(existing_categories) + 1:
            new_cat = input("Enter new category name: ").strip()
            return new_cat if new_cat else None
            
        # User picked "[Skip / No Category]"
        else:
            return None
            
    except ValueError:
        # Fallback: If they typed out text instead of a number, just treat it as a new category
        if choice:
            return choice.strip()
        return None
#Back to human code



def run_function(cursor, conn):

    defpick = input("what function would you like to run ")

    if defpick == "ad":
        return add_task(cursor, conn)

    elif defpick == "inst":
        return inspect_task(cursor, conn)

    elif defpick == "insts":
        return inspect_tasks(cursor, conn)

    elif defpick == "rm":
        return remove_task(cursor, conn)

    elif defpick == "ed":
        return edit_task(cursor, conn)

    elif defpick == "ct":
        return mark_complete_task(cursor, conn)

    elif defpick == "uct":
        return mark_incomplete_task(cursor, conn)

    elif defpick == "sl":
        return show_list(cursor, conn, target_date=None)

    else:
        return None

def main():
    # Get the directory where THIS script is located
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Join that directory with the database filename
    db_path = os.path.join(base_dir, "todos.db")
    
    # Connect using that universal path
    # Defining the connection to the database file and setting up the selection cursor that will be the hing bridging the gap between the script and the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()


    # making the table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            time_frame TEXT,
            target_date TEXT,
            recurrence_type TEXT,
            interval_days INTEGER,
            end_date TEXT,
            custom_list TEXT
        )"""
    )
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            completed_date TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        )"""
    )
    conn.commit()


    while True:

        #print(help("module"))
        #import time 
        
        tester = run_function(cursor, conn)

        if tester is not None:

            test = tester

            print("Task added with ID:", cursor.lastrowid)

# makes sure that the core will only run the def if it was launched directly into core
if __name__ == "__main__":
    main()
