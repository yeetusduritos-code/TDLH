# imports programs for use
import sqlite3
from datetime import datetime

def add_task(cursor, conn):

    task = input("What is your task/habit ")

    category = get_or_create_category(cursor)

    print("\n--- Display Layout Position ---")
    print("1. Weekday List\n2. Monthly List\n3. Yearly List\n4. Custom Board")
    frame_choice = input("Choose (1-4): ")
    time_frame = ['weekday', 'month', 'year', 'custom_frame'][int(frame_choice) - 1]

    if time_frame != "custom":
        target_date = input("Target date for this item (YYYY-MM-DD): ")
    else:
        target_date = None
    
    print("\n--- Recurrence Type ---")
    print("1. Once\n2. Daily\n3. Weekly List\n4. Monthly List\n5. Custom Interval")
    recurrence_choice = input("Choose (1-5): ")
    recurrence_type = ["once", "daily", "weekly", "monthly", "custom_interval"][int(recurrence_choice) - 1]

    interval_days = 0
    if recurrence_type == "custom_interval":
        interval_days = int(input("Repeat every how many days? "))

    end_date = input("End date for recurrence (YYYY-MM-DD) [Press Enter for never]: ") or None

    cursor.execute(
    "INSERT INTO tasks (name, category, time_frame, target_date, recurrence_type, interval_days, end_date) VALUES (?,?,?,?,?,?,?)",
    (task, category, time_frame, target_date, recurrence_type, interval_days, end_date)
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
        print("\n1. name\n2. category\n3. time_frame & target_date\n4. target_date\n5. recurrence settings\n6. interval_days\n7. end_date")
        
        edit_select = int(input("What do you want to edit on this task choose (1-7): "))
        
        edit_choice = ["name", "category", "time_frame", "target_date", "recurrence_type", "interval_days", "end_date"][edit_select - 1]

        # This variable will hold our value for the single-column updates at the bottom
        edit_value = None

        if edit_select == 1:
            edit_value = input("What is the new name of the task: ")

        elif edit_select == 2:
            edit_value = get_or_create_category(cursor)

        elif edit_select == 3:
            print("\nSet new \n--- Display Layout Position ---")
            print("1. Weekday List\n2. Monthly List\n3. Yearly List\n4. Custom Board")
            frame_choice = input("Choose (1-4): ")
            time_frame = ['weekday', 'month', 'year', 'custom'][int(frame_choice) - 1]

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
        
        # 4. MASTER ENGINE LOGIC (Runs for options 1, 2, 4, 6, and 7)
        if edit_select in [1, 2, 4, 6, 7]: # safely allows None strings for skip options
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

    if list_choice.lower() == "d":
        print("--- Todays list ---")
        print("Todays date and time", current_time)

        # 1. Handle the default: Use today's date if the user didn't type one in
        if target_date is None:
            target_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # e.g., "2026-06-26"

        print(f"\n--- Fetching tasks for date: {target_date} ---")

        # 2. THE SQL QUERY
        # This selects tasks where the target_date matches exactly, 
        # OR daily tasks that started on or before the selected date (ignoring finished ones)
        cursor.execute("""
            SELECT id, name, category, recurrence_type 
            FROM tasks 
            WHERE (target_date = ? AND recurrence_type = 'once')
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

    elif list_choice.lower() == "m":
        print("--- This months list ---")
        print("Todays date and time", current_time)

    elif list_choice.lower() == "y":
        print("--- This years list ---")
        print("Todays date and time", current_time)

    elif list_choice.lower() == "c":
        print("--- Custom lists ---")
        print("Todays date and time", current_time)


def custom_list(cursor, conn):
    pass


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

    else:
        return None

def main():


    # Defining the connection to the database file and setting up the selection cursor that will be the hing bridging the gap between the script and the database
    conn = sqlite3.connect("todos.db")
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
            end_date TEXT
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
