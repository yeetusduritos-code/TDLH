# imports programs for use
import sqlite3
import os
from datetime import datetime, timedelta
import calendar

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
    print("1. Once\n2. Daily\n3. Weekly List\n4. Monthly List\n5. Yearly List\n6. Custom Interval")
    recurrence_choice = input("Choose (1-6): ")
    recurrence_type = ["once", "daily", "weekly", "monthly", "yearly", "custom_interval"][int(recurrence_choice) - 1]

    interval_days = 0
    if recurrence_type == "custom_interval":
        interval_days = int(input("Repeat every how many days? "))
    elif recurrence_type == "daily":
        interval_days = 1
    elif recurrence_type == "weekly":
        interval_days = 7
        
    end_date = input("End date for recurrence (YYYY-MM-DD) [Press Enter for never]: ") or None
    
    note = input("Add a note if you want to [Press Enter to skip]: ") or None

    unit = input("Add a unit if you have somthing to log [Press Enter to skip]: ") or None

    custom_list = None
    
    cursor.execute(
    "INSERT INTO tasks (name, category, time_frame, target_date, recurrence_type, interval_days, end_date, custom_list, note, unit) VALUES (?,?,?,?,?,?,?,?,?,?)",
    (task, category, time_frame, target_date, recurrence_type, interval_days, end_date, custom_list, note, unit)
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

    note = input("Add a note if you want to [Press Enter to skip]: ") or None

    unit = input("Add a unit if you have somthing to log [Press Enter to skip]: ") or None

    cursor.execute(
    "INSERT INTO tasks (name, category, time_frame, target_date, recurrence_type, interval_days, end_date, custom_list, note, unit) VALUES (?,?,?,?,?,?,?,?,?,?)",
    (task, category, time_frame, target_date, recurrence_type, interval_days, end_date, custom_list, note, unit)
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
        print(f"ID: {t[0]} | Name: {t[1]} | Cat: {t[2]} | Layout: {t[3]} | Recur: {t[4]}| Note: {t[9]}")


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
        print("\n1. name\n2. category\n3. time_frame & target_date\n4. target_date\n5. recurrence settings\n6. interval_days\n7. end_date\n8. custom_list\n9. note\n10. unit")
        
        edit_select = int(input("What do you want to edit on this task choose (1-10): "))
        
        edit_choice = ["name", "category", "time_frame", "target_date", "recurrence_type", "interval_days", "end_date", "custom_list", "note", "unit"][edit_select - 1]

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
            print("\n1. Once\n2. Daily\n3. Weekly List\n4. Monthly List\n5. Yearly List\n6. Custom Interval")
            recurrence_choice = input("Choose (1-6): ")
            recurrence_type = ["once", "daily", "weekly", "monthly", "yearly", "custom_interval"][int(recurrence_choice) - 1]

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

        elif edit_select == 9:
            edit_value = input("Write a new note or [Press Enter for none]") or None

        elif edit_select == 10:
            edit_value = input("Write a new unit or [Press Enter for none]") or None
        
        # 4. MASTER ENGINE LOGIC (Runs for options 1, 2, 4, 6, and 7)
        if edit_select in [1, 2, 4, 6, 7, 8, 9, 10]: # safely allows None strings for skip options
            cursor.execute(
                f"UPDATE tasks SET {edit_choice} = ? WHERE id = ?",
                (edit_value, int(task))
            )
            print(f"Property '{edit_choice}' modified successfully.")
        
        conn.commit()
    else:
        print("Operation cancelled")




def mark_complete_task(cursor, conn):
    task = input("Id of completed task: ")

    cursor.execute(
        "SELECT * FROM tasks WHERE id = ?",
        (int(task),)
    )

    one_task = cursor.fetchone()
    print("This is the task you selected:")
    print(one_task)

    yn = input("Are you sure you want to complete this task y/N ")


    if yn.lower() == "y":

        yn = input("do you want to set your own date y/N ") 
        
        if yn.lower() == "y":
            completed_dt = input("set the date (YYYY-MM-DD): ")
        else:
            completed_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        unit = one_task[10]

        if unit != None:
            amount = int(input("Amount of unit: "))
        else:
            amount = None

        cursor.execute(
            "INSERT INTO task_completions (task_id, completed_date, unit, amount) VALUES (?, ?, ?, ?)",
            (int(task), completed_dt, unit, amount)
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



    elif list_choice.lower() == "h":
        print("--- Habits list ---")


        target_date = datetime.now().strftime("%Y-%m-%d") # e.g., "2026-06-26"
        
        current_month_str = target_date[:7]
        current_month_ub = current_month_str + "-31"


        # 1. Query the DB for unique categories that aren't empty/NULL
        cursor.execute("""
                        SELECT id, name, category, recurrence_type
                        FROM tasks 
                        WHERE recurrence_type != 'once' AND (target_date <= ? AND (end_date > ? OR end_date IS NULL))
                        GROUP BY name
                        ORDER BY name
                        """, (current_month_ub, target_date))
        on_habits = cursor.fetchall()


        cursor.execute("""
                        SELECT id, name, category, recurrence_type
                        FROM tasks 
                        WHERE recurrence_type != 'once' AND target_date > ?
                        GROUP BY name
                        ORDER BY name
                        """, (current_month_ub, ))
        up_habits = cursor.fetchall()



        cursor.execute("""
                        SELECT id, name, category, recurrence_type
                        FROM tasks 
                        WHERE recurrence_type != 'once' AND end_date < ?
                        GROUP BY name
                        ORDER BY name
                        """, (target_date, ))
        past_habits = cursor.fetchall()


        if (on_habits and up_habits and past_habits) == None:
            print("There are currently no habits")
            return

        print("What habits would you like to view\n1. Ongoing\n2. Upcoming\n3. Past")
        choice = input("Choose (1-3): ")
        habit_list = [1, 2, 3][int(choice) - 1]

        if habit_list == 1:
            print("--- Ongoing habits ---")
            for task in on_habits:
                print(f"ID: {task[0]} | Name: {task[1]} | Catagory: {task[2]}")
        elif habit_list == 2:
            print("--- Upcoming habits ---")
            for task in up_habits:
                print(f"ID: {task[0]} | Name: {task[1]} | Catagory: {task[2]}")
        elif habit_list == 3:
            print("--- Past habits ---")
            for task in past_habits:
                print(f"ID: {task[0]} | Name: {task[1]} | Catagory: {task[2]}")
        else:
            print("you didn't input a vaild number")
      

    else:
        print("You did not select type a vaild viewing option")
        return







#date maniulation tools using the calendar import
def next_month(dt):
    year = dt.year
    month = dt.month + 1
    day = dt.day

    if month > 12:
        month = 1
        year = year + 1
    
    # Check how many days are actually in the target month (e.g., Feb has 28/29)
    # calendar.monthrange returns (weekday_of_first_day, total_days_in_month)
    month_days_total = calendar.monthrange(year, month)[1]

    #if adding one month went past the bound of the previus month retain it to the months end
    if day > month_days_total:
        day = month_days_total
    

    current_date = datetime.now().strftime("%Y-%m-%d")
    current_date_obj = datetime.strptime(current_date, "%Y-%m-%d")
    target_date = datetime(year, month, day)

    return target_date

def next_year(dt):
    year = dt.year + 1
    month = dt.month
    day = dt.day

    if month == 2 and day == 29 and not calendar.isleap(year):
        day = 28

    current_date = datetime.now().strftime("%Y-%m-%d")
    current_date_obj = datetime.strptime(current_date, "%Y-%m-%d")
    target_date = datetime(year, month, day)

    return target_date



def streak_compleation_and_heatmap(cursor, conn):
    
    print("what habit or catagory would you like veiw the streak/completion'%'for")

    cursor.execute("""
            SELECT MIN(id), name, category, recurrence_type
            FROM tasks 
            WHERE recurrence_type != 'once'
            GROUP BY name
            ORDER BY name
            """)
    habits = cursor.fetchall()

    print("--- Habits ---")
    for task in habits:
        print(f"ID: {task[0]} | Name: {task[1]} | Catagory: {task[2]}")
    
    cursor.execute("""
        SELECT MIN(id), name, category, recurrence_type
        FROM tasks 
        WHERE category IS NOT NULL
        GROUP BY category
        ORDER BY name
        """)
    categories = cursor.fetchall()

    print("--- Categories ---")
    for task in categories:
        print(f"Catagory: {task[2]}")

    n_or_c = input("do you want to view by Name or Catagory (N/C): ")
    if n_or_c.lower() == "n":

        habit_name = input("Which habit (Name): ")
        cursor.execute("""
            SELECT target_date, recurrence_type, interval_days, end_date, id
            FROM tasks
            WHERE name = ? AND recurrence_type != 'once'
            """, (habit_name, ))

    elif n_or_c.lower() == "c":

        catagory_name = input("Which catagory (Catagory): ")
        cursor.execute("""
            SELECT target_date, recurrence_type, interval_days, end_date, id
            FROM tasks
            WHERE category = ?
            """, (catagory_name, ))
    
    habit_sql = cursor.fetchall()

    task_id = []
    for ids in habit_sql:
        task_id.append(ids[4])

    completions = []

    for task in task_id:
        cursor.execute("""
        SELECT completed_date
        FROM task_completions
        WHERE task_id = ?
        """, (task, ))
        comps = [row[0].split()[0] for row in cursor.fetchall()]
        completions.extend(comps)

    streak = 0
    longest_streak = 0
    completion = 0
    miss = 0
    completion_oppertunities = 0
    completion_dates = []

    cur_date = datetime.now().strftime("%Y-%m-%d") # e.g., "2026-06-26"
    cur_date_obj = datetime.strptime(cur_date, "%Y-%m-%d")

    for row in habit_sql:
        target_date_obj = datetime.strptime(row[0], "%Y-%m-%d")

        if row[1] == "once":
            completion_dates.append(target_date_obj)
            completion_oppertunities += 1

        else:
            while target_date_obj <= cur_date_obj:

                if row[1] in ["daily", "weekly", "custom_interval"]:
                    completion_dates.append(target_date_obj)
                    completion_oppertunities += 1
                    target_date_obj = target_date_obj + timedelta(days = row[2])

                elif row[1] == "monthly":
                    completion_dates.append(target_date_obj)
                    completion_oppertunities += 1
                    target_date_obj = next_month(target_date_obj)                

                elif row[1] == "yearly":
                    completion_dates.append(target_date_obj)
                    completion_oppertunities += 1
                    target_date_obj = next_year(target_date_obj)


    #streak calculator
    completion = sum(1 for task in completion_dates if task.strftime("%Y-%m-%d") in completions)
    miss = completion_oppertunities - completion

    heat_map_color = []
    heat_map_cli = []

    for x in completion_dates:
        if x.strftime("%Y-%m-%d") in completions:
            heat_map_color.append(1)
            heat_map_cli.append("⬛")
            streak += 1
            if longest_streak < streak:
                longest_streak = streak
        else:
            heat_map_color.append(0)
            heat_map_cli.append("⬜")
            streak = 0


    if miss == 0:
        completion_procent = 100
    elif completion_oppertunities == 0:
        completion_procent = 0
    else:
        completion_procent = (completion / completion_oppertunities) * 100


    print("your current streak is ", streak, " , your longest streak is ", longest_streak ," you missed ", miss ," and you have a completion procent of ", completion_procent, "%")
    print("--- Heat Map ---")
    print(heat_map_cli)


def graphed_haibt(cursor, conn):

    target_date = datetime.now().strftime("%Y-%m-%d")
    current_month_str = target_date[:7]
    current_month_ub = current_month_str + "-31"
    
    print("what habit would you like veiw heatmap for")

    cursor.execute("""
            SELECT id, name, category, recurrence_type
            FROM tasks 
            WHERE recurrence_type != 'once'
            GROUP BY name
            ORDER BY name
            """)
    habits = cursor.fetchall()

    for task in habits:
        print(f"ID: {task[0]} | Name: {task[1]} | Catagory: {task[2]}")

    habit_name = input("Choose (Name): ")

    cursor.execute("""
            SELECT id, recurrence_type, time_frame, target_date, end_date, interval_days
            FROM tasks
            WHERE name = ?
            """, (habit_name, ))



#AI generated code
def graphed_haibt(cursor, conn):
    print("\n--- Graphed Habit Trend View ---")

    # 1. Fetch available habits for selection
    cursor.execute("""
            SELECT MIN(id), name, category, recurrence_type
            FROM tasks 
            WHERE recurrence_type != 'once'
            GROUP BY name
            ORDER BY name
            """)
    habits = cursor.fetchall()

    if not habits:
        print("No recurring habits found.")
        return

    print("--- Habits ---")
    for task in habits:
        print(f"ID: {task[0]} | Name: {task[1]} | Category: {task[2]}")

    habit_name = input("Choose Habit Name to graph: ").strip()

    # 2. Get all task IDs matching this habit name
    cursor.execute("""
        SELECT id, target_date, recurrence_type 
        FROM tasks 
        WHERE name = ?
    """, (habit_name,))
    habit_rows = cursor.fetchall()

    if not habit_rows:
        print("Habit not found.")
        return

    task_ids = [row[0] for row in habit_rows]

    # 3. Pull all completion records for these task IDs
    completions = []
    for tid in task_ids:
        cursor.execute("""
            SELECT completed_date 
            FROM task_completions 
            WHERE task_id = ?
        """, (tid,))
        # Extract just the YYYY-MM-DD date part
        comps = [row[0].split()[0] for row in cursor.fetchall()]
        completions.extend(comps)

    if not completions:
        print("No completion records found for this habit yet.")
        return

    # 4. Group completions by ISO Week (e.g., "2026-W26") to show a trend over time
    from collections import defaultdict
    weekly_counts = defaultdict(int)

    for comp_date_str in completions:
        dt = datetime.strptime(comp_date_str, "%Y-%m-%d")
        # Get ISO year and week number as a sortable key like "2026-W26"
        iso_year, iso_week, _ = dt.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        weekly_counts[week_key] += 1

    # 5. Display the trend data as a simple text/bar graph
    print(f"\n--- Weekly Trend Graph for '{habit_name}' ---")
    sorted_weeks = sorted(weekly_counts.keys())

    for week in sorted_weeks:
        count = weekly_counts[week]
        # Draw a simple text bar using blocks to represent the frequency
        bar = "█" * count
        print(f"{week} | {bar} ({count})")

def get_unified_heatmap_data(cursor, conn):
    print("\n--- Master Heatmap Data Generator ---")
    print("1. Individual Habit\n2. Category\n3. Global (All Tasks)")
    choice = input("Choose view scope (1-3): ").strip()

    all_logs = []
    
    # --- OPTION 1: INDIVIDUAL HABIT ---
    if choice == "1":
        cursor.execute("SELECT MIN(id), name FROM tasks WHERE recurrence_type != 'once' GROUP BY name ORDER BY name")
        habits = cursor.fetchall()
        if not habits:
            print("No habits found.")
            return {}
        
        print("\nHabits:")
        for h in habits:
            print(f"ID: {h[0]} | Name: {h[1]}")
        
        habit_name = input("Enter Habit Name: ").strip()
        
        # Get all completion records for tasks matching this habit name
        cursor.execute("""
            SELECT tc.completed_date 
            FROM task_completions tc
            JOIN tasks t ON tc.task_id = t.id
            WHERE t.name = ?
        """, (habit_name,))
        all_logs = [row[0].split()[0] for row in cursor.fetchall()]

    # --- OPTION 2: CATEGORY ---
    elif choice == "2":
        cursor.execute("SELECT DISTINCT category FROM tasks WHERE category IS NOT NULL AND category != ''")
        categories = cursor.fetchall()
        if not categories:
            print("No categories found.")
            return {}
            
        print("\nCategories:")
        for idx, cat in enumerate(categories, 1):
            print(f"{idx}. {cat[0]}")
            
        cat_choice = input("Enter Category Name: ").strip()
        
        # Get all completion records for tasks under this category tag
        cursor.execute("""
            SELECT tc.completed_date 
            FROM task_completions tc
            JOIN tasks t ON tc.task_id = t.id
            WHERE t.category = ?
        """, (cat_choice,))
        all_logs = [row[0].split()[0] for row in cursor.fetchall()]

    # --- OPTION 3: GLOBAL (EVERYTHING) ---
    elif choice == "3":
        cursor.execute("SELECT completed_date FROM task_completions")
        all_logs = [row[0].split()[0] for row in cursor.fetchall()]
        
    else:
        print("Invalid choice.")
        return {}

    # If no logs exist for the chosen scope, return empty dictionary
    if not all_logs:
        print("No completion data found for this selection.")
        return {}

    # --- SHARED INTENSITY & TIMELINE ENGINE ---
    start_dt = datetime.strptime(min(all_logs), "%Y-%m-%d")
    end_dt = datetime.now()

    from collections import Counter
    completion_counts = Counter(all_logs)

    current_dt = start_dt
    heatmap_data = {}

    while current_dt <= end_dt:
        date_key = current_dt.strftime("%Y-%m-%d")
        count = completion_counts.get(date_key, 0)

        # Standard saturation intensity scale (0 to 4)
        if count == 0:
            intensity = 0
        elif count == 1:
            intensity = 1
        elif count == 2:
            intensity = 2
        elif count <= 4:
            intensity = 3
        else:
            intensity = 4

        heatmap_data[date_key] = {
            "count": count,
            "intensity": intensity
        }
        current_dt += timedelta(days=1)

    return heatmap_data



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
    
    elif defpick == "sac":
        return streak_compleation_and_heatmap(cursor, conn)

    elif defpick == "hmd":
        return get_unified_heatmap_data(cursor, conn)

    elif defpick == "grh":
        return graphed_haibt(cursor, conn)

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
            custom_list TEXT,
            note TEXT,
            unit TEXT
        )"""
    )
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id),
            completed_date TEXT NOT NULL,
            unit TEXT,
            amount INTEGER
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
