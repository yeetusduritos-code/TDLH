# backend.py
import sqlite3
from datetime import datetime, timedelta

# =============================================================================
# >>> SECTION B1 START: DATABASE CONNECTION & SCHEMA INIT <<<
# =============================================================================
DB_NAME = "tasks.db"


def get_db_connection():
    return sqlite3.connect(DB_NAME)


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            time_frame TEXT,
            target_date TEXT,
            recurrence_type TEXT DEFAULT 'once',
            interval_days INTEGER DEFAULT 0,
            end_date TEXT,
            custom_list TEXT,
            note TEXT,
            unit TEXT,
            custom_days TEXT,
            custom_months TEXT,
            reminder_time TEXT
        )
        """
    )
    # Safe migration for existing databases without reminder_time
    cursor.execute("PRAGMA table_info(tasks)")
    columns = [col[1] for col in cursor.fetchall()]
    if "reminder_time" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN reminder_time TEXT")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            completed_date TEXT,
            amount REAL,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS habit_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_name TEXT NOT NULL,
            goal_type TEXT NOT NULL,
            target_value REAL NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            achieved INTEGER DEFAULT 0,
            achieved_date TEXT
        )
        """
    )
    conn.commit()
    conn.close()

# =============================================================================
# >>> SECTION B1 END: DATABASE CONNECTION & SCHEMA INIT <<<
# =============================================================================


# =============================================================================
# >>> SECTION B2 START: RECURRENCE & DUE-DATE ENGINE <<<
# =============================================================================
def is_task_due_on_date(task_row, date_str: str) -> bool:
    tid, name, cat, tf, t_date, rec, interval, end_d, clist, note, unit, custom_days = task_row[:12]
    custom_months = task_row[12] if len(task_row) > 12 else None

    if tf != "day" or not t_date:
        return False
    if end_d and date_str > end_d:
        return False

    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        orig_dt = datetime.strptime(t_date, "%Y-%m-%d")
    except Exception:
        return False

    if date_str < t_date:
        return False

    rec = rec or "once"
    if rec == "once":
        return t_date == date_str
    elif rec == "daily":
        return True
    elif rec == "weekly":
        if custom_days:
            day_name = dt.strftime("%a")
            selected_days = [d.strip() for d in custom_days.split(",") if d.strip()]
            return day_name in selected_days
        else:
            return orig_dt.weekday() == dt.weekday()
    elif rec == "monthly":
        if custom_months:
            sel_months = [int(m.strip()) for m in custom_months.split(",") if m.strip().isdigit()]
            if dt.month not in sel_months:
                return False
        if custom_days:
            day_name = dt.strftime("%a")
            selected_days = [d.strip() for d in custom_days.split(",") if d.strip()]
            return day_name in selected_days
        return orig_dt.day == dt.day
    elif rec == "yearly":
        target_months = (
            [int(m.strip()) for m in custom_months.split(",") if m.strip().isdigit()]
            if custom_months
            else [orig_dt.month]
        )
        if dt.month not in target_months:
            return False
        if custom_days:
            day_name = dt.strftime("%a")
            selected_days = [d.strip() for d in custom_days.split(",") if d.strip()]
            return day_name in selected_days
        return orig_dt.day == dt.day
    elif rec == "custom_interval":
        int_days = int(interval) if (interval and int(interval) > 0) else 1
        diff = (dt - orig_dt).days
        return diff >= 0 and (diff % int_days == 0)

    return False
# =============================================================================
# >>> SECTION B2 END: RECURRENCE & DUE-DATE ENGINE <<<
# =============================================================================


# =============================================================================
# >>> SECTION B3 START: TASK CRUD, EDIT & BACKLOG OPERATIONS <<<
# =============================================================================
def add_task_db(
    name, category="General", time_frame="day", target_date=None,
    recurrence_type="once", interval_days=0, end_date=None,
    custom_list=None, note=None, unit=None, custom_days=None,
    custom_months=None, reminder_time=None
):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO tasks (
            name, category, time_frame, target_date, recurrence_type,
            interval_days, end_date, custom_list, note, unit,
            custom_days, custom_months, reminder_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name, category, time_frame, target_date, recurrence_type,
            interval_days, end_date, custom_list, note, unit,
            custom_days, custom_months, reminder_time
        )
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id


def update_task_db(
    task_id, name, category, time_frame, target_date, recurrence_type,
    interval_days, end_date, note, unit, custom_days, custom_months,
    reminder_time=None
):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE tasks SET
            name = ?, category = ?, time_frame = ?, target_date = ?,
            recurrence_type = ?, interval_days = ?, end_date = ?,
            note = ?, unit = ?, custom_days = ?, custom_months = ?,
            reminder_time = ?
        WHERE id = ?
        """,
        (
            name, category, time_frame, target_date, recurrence_type,
            interval_days, end_date, note, unit, custom_days,
            custom_months, reminder_time, task_id
        )
    )
    conn.commit()
    conn.close()


def fetch_all_tasks():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, name, category, time_frame, target_date, recurrence_type,
               interval_days, end_date, custom_list, note, unit,
               custom_days, custom_months, reminder_time
        FROM tasks
        ORDER BY id DESC
        """
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def fetch_tasks_for_date(date_str: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, name, category, time_frame, target_date, recurrence_type,
               interval_days, end_date, custom_list, note, unit,
               custom_days, custom_months, reminder_time
        FROM tasks
        WHERE (custom_list IS NULL OR custom_list != 'Backlog')
        """
    )
    rows = cursor.fetchall()
    conn.close()

    target_dt = datetime.strptime(date_str, "%Y-%m-%d")
    weekday_str = target_dt.strftime("%a")
    month_int = target_dt.month

    valid_tasks = []
    for r in rows:
        t_id, t_name, t_cat, t_tf, t_target, t_rec, t_int, t_end, t_list, t_note, t_unit, t_cdays, t_cmonths, t_rem = r
        if t_end and date_str > t_end:
            continue
        if t_target and date_str < t_target and t_rec == "once":
            continue

        if t_rec == "once":
            if t_target == date_str:
                valid_tasks.append(r)
        elif t_rec == "daily":
            if not t_target or date_str >= t_target:
                valid_tasks.append(r)
        elif t_rec == "weekly":
            if not t_target or date_str >= t_target:
                active_days = [d.strip() for d in (t_cdays or "").split(",") if d.strip()]
                if not active_days or weekday_str in active_days:
                    valid_tasks.append(r)
        elif t_rec in ["monthly", "yearly"]:
            if not t_target or date_str >= t_target:
                start_day = datetime.strptime(t_target, "%Y-%m-%d").day if t_target else 1
                if target_dt.day == start_day:
                    active_months = [int(m.strip()) for m in (t_cmonths or "").split(",") if m.strip().isdigit()]
                    if not active_months or month_int in active_months:
                        valid_tasks.append(r)
        elif t_rec == "custom_interval":
            if t_target and date_str >= t_target and t_int and t_int > 0:
                start_dt = datetime.strptime(t_target, "%Y-%m-%d")
                delta_days = (target_dt - start_dt).days
                if delta_days >= 0 and delta_days % t_int == 0:
                    valid_tasks.append(r)

    return valid_tasks


def fetch_backlog_tasks():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, name, category, time_frame, target_date, recurrence_type,
               interval_days, end_date, custom_list, note, unit,
               custom_days, custom_months, reminder_time
        FROM tasks
        WHERE custom_list = 'Backlog'
        ORDER BY id DESC
        """
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def schedule_backlog_task_db(task_id, target_date_str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE tasks
        SET time_frame = 'day', target_date = ?, custom_list = NULL
        WHERE id = ?
        """,
        (target_date_str, task_id),
    )
    conn.commit()
    conn.close()


def remove_task_db(task_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM task_completions WHERE task_id = ?", (task_id,))
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()


def batch_remove_tasks_db(task_ids):
    if not task_ids:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in task_ids)
    cursor.execute(f"DELETE FROM task_completions WHERE task_id IN ({placeholders})", task_ids)
    cursor.execute(f"DELETE FROM tasks WHERE id IN ({placeholders})", task_ids)
    conn.commit()
    conn.close()
# =============================================================================
# >>> SECTION B3 END: TASK CRUD, EDIT & BACKLOG OPERATIONS <<<
# =============================================================================


# =============================================================================
# >>> SECTION B4 START: TASK COMPLETIONS & LOGGING <<<
# =============================================================================
def mark_complete_db(task_id, completed_dt=None, amount=None):
    if not completed_dt:
        completed_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date_prefix = completed_dt[:10]

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT unit FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    unit_val = row[0] if row else None

    cursor.execute(
        "SELECT id FROM task_completions WHERE task_id = ? AND substr(completed_date, 1, 10) = ?",
        (task_id, date_prefix),
    )
    existing = cursor.fetchone()

    if existing:
        cursor.execute(
            "UPDATE task_completions SET completed_date = ?, amount = ?, unit = ? WHERE id = ?",
            (completed_dt, amount, unit_val, existing[0]),
        )
    else:
        cursor.execute(
            "INSERT INTO task_completions (task_id, completed_date, unit, amount) VALUES (?, ?, ?, ?)",
            (task_id, completed_dt, unit_val, amount),
        )
    conn.commit()
    conn.close()


def remove_completion_db(task_id, date_str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM task_completions WHERE task_id = ? AND substr(completed_date, 1, 10) = ?",
        (task_id, date_str[:10]),
    )
    conn.commit()
    conn.close()


def get_completions_for_date(date_str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT task_id, amount, unit
        FROM task_completions
        WHERE substr(completed_date, 1, 10) = ?
        """,
        (date_str[:10],),
    )
    rows = cursor.fetchall()
    conn.close()
    result = {}
    for tid, amt, u in rows:
        result[tid] = {"amount": amt, "unit": u}
    return result
# =============================================================================
# >>> SECTION B4 END: TASK COMPLETIONS & LOGGING <<<
# =============================================================================


# =============================================================================
# >>> SECTION B5 START: ANALYTICS, HEATMAPS, STREAKS & GOALS <<<
# =============================================================================
def ensure_goals_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS habit_goals_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_name TEXT NOT NULL,
            goal_type TEXT NOT NULL DEFAULT 'max',
            target_value REAL NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            achieved INTEGER DEFAULT 0,
            achieved_date TEXT
        )
        """
    )
    conn.commit()
    conn.close()


ensure_goals_table()


def format_ui_date(iso_str: str, style: str = "short_text") -> str:
    """
    Converts 'YYYY-MM-DD' into clean Day-Month-Year formats:
    - 'short_text': '02 Nov 2026'
    - 'day_month':  '02 Nov'
    - 'numeric':    '02-11-2026'
    - 'header':     'Mon, 02 Nov 2026'
    """
    if not iso_str:
        return ""
    try:
        dt = datetime.strptime(iso_str[:10], "%Y-%m-%d")
        if style == "numeric":
            return dt.strftime("%d-%m-%Y")
        elif style == "day_month":
            return dt.strftime("%d %b")
        elif style == "header":
            return dt.strftime("%a, %d %b %Y")
        return dt.strftime("%d %b %Y")
    except Exception:
        return iso_str


def parse_ui_date_to_iso(date_input: str) -> str:
    """Accepts 'DD-MM-YYYY', 'DD/MM/YYYY', or 'YYYY-MM-DD' and returns 'YYYY-MM-DD'."""
    if not date_input or not date_input.strip():
        return None
    s = date_input.strip().replace("/", "-")
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def get_distinct_categories():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT category FROM tasks WHERE category IS NOT NULL AND category != ''")
    rows = [r[0] for r in cursor.fetchall()]
    conn.close()
    return sorted(rows)


def get_distinct_habits():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT DISTINCT name FROM tasks
        WHERE recurrence_type IS NOT NULL AND recurrence_type != 'once'
        """
    )
    rows = [r[0] for r in cursor.fetchall()]
    conn.close()
    return sorted(rows)


def is_habit_daily(habit_name: str) -> bool:
    """Returns True if the habit is scheduled every day (daily or all 7 weekdays)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT recurrence_type, custom_days, interval_days FROM tasks WHERE name = ? AND time_frame = 'day'",
        (habit_name,),
    )
    rows = cursor.fetchall()
    conn.close()
    for rec, cdays, int_d in rows:
        if rec == "daily":
            return True
        if rec == "weekly" and cdays and len([d for d in cdays.split(",") if d.strip()]) >= 7:
            return True
        if rec == "custom_interval" and int_d == 1:
            return True
    return False


def _filter_tasks_by_scope(all_tasks, scope, identifier):
    if scope == "global":
        return [t for t in all_tasks if t[3] == "day"]
    elif scope == "habit" and identifier:
        return [t for t in all_tasks if t[3] == "day" and t[1] == identifier and t[5] != "once"]
    elif scope == "category" and identifier:
        return [t for t in all_tasks if t[3] == "day" and (t[2] or "General") == identifier]
    return []


def get_habit_date_bounds(habit_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT MIN(target_date), MAX(COALESCE(end_date, target_date))
        FROM tasks
        WHERE name = ? AND time_frame = 'day'
        """,
        (habit_name,),
    )
    row = cursor.fetchone()
    conn.close()
    today_s = datetime.now().strftime("%Y-%m-%d")
    if row and row[0]:
        start_b = row[0]
        # If any chained task has no end_date, the habit is still ongoing up to at least today
        conn2 = get_db_connection()
        c2 = conn2.cursor()
        c2.execute(
            "SELECT COUNT(*) FROM tasks WHERE name = ? AND time_frame = 'day' AND (end_date IS NULL OR end_date = '')",
            (habit_name,),
        )
        has_open_ended = c2.fetchone()[0] > 0
        conn2.close()
        end_b = max(row[1] or today_s, today_s) if has_open_ended else (row[1] or today_s)
        return start_b, end_b
    return today_s, today_s


def get_unified_heatmap_data(scope="global", identifier=None, start_override=None, end_override=None):
    all_tasks = fetch_all_tasks()
    scoped_tasks = _filter_tasks_by_scope(all_tasks, scope, identifier)
    if not scoped_tasks:
        return {}

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT task_id, substr(completed_date, 1, 10) FROM task_completions")
    comp_rows = cursor.fetchall()
    conn.close()

    comp_by_date = {}
    for tid, d_str in comp_rows:
        comp_by_date.setdefault(d_str, set()).add(tid)

    today_dt = datetime.now()

    iso_start = parse_ui_date_to_iso(start_override) if start_override else None
    iso_end = parse_ui_date_to_iso(end_override) if end_override else None

    if iso_start:
        earliest_dt = datetime.strptime(iso_start, "%Y-%m-%d")
    else:
        valid_dates = [t[4] for t in scoped_tasks if t[4]]
        earliest_dt = (
            min(datetime.strptime(d, "%Y-%m-%d") for d in valid_dates)
            if valid_dates
            else (today_dt - timedelta(days=90))
        )

    if iso_end:
        latest_dt = datetime.strptime(iso_end, "%Y-%m-%d")
    else:
        has_open = any(len(t) <= 7 or not t[7] for t in scoped_tasks)
        valid_ends = [t[7] for t in scoped_tasks if len(t) > 7 and t[7]]
        if has_open:
            latest_dt = max([datetime.strptime(d, "%Y-%m-%d") for d in valid_ends] + [today_dt])
        else:
            latest_dt = max(datetime.strptime(d, "%Y-%m-%d") for d in valid_ends) if valid_ends else today_dt

    if scope == "global" and not iso_start:
        # Show at least 26 weeks (~6 months) for the Anki-style review heatmap
        earliest_dt = min(earliest_dt, today_dt - timedelta(days=180))

    heatmap = {}
    curr = earliest_dt
    while curr <= latest_dt:
        d_str = curr.strftime("%Y-%m-%d")
        due_tasks = [t for t in scoped_tasks if is_task_due_on_date(t, d_str)]
        due_ids = {t[0] for t in due_tasks}
        done_ids = comp_by_date.get(d_str, set()).intersection(due_ids)

        due_count = len(due_ids)
        done_count = len(done_ids)

        if due_count == 0:
            intensity = 0
        else:
            ratio = done_count / due_count
            intensity = 4 if ratio >= 1.0 else (3 if ratio >= 0.75 else (2 if ratio >= 0.4 else (1 if ratio > 0 else 0)))

        heatmap[d_str] = {
            "count": done_count,
            "due": due_count,
            "intensity": intensity,
        }
        curr += timedelta(days=1)

    return heatmap


def get_streak_and_stats(scope="global", identifier=None, start_override=None, end_override=None):
    heatmap = get_unified_heatmap_data(scope, identifier, start_override, end_override)
    today_str = datetime.now().strftime("%Y-%m-%d")
    scheduled_days = [
        d for d in sorted(heatmap.keys())
        if d <= today_str and heatmap[d].get("due", 0) > 0
    ]

    if not scheduled_days:
        return {
            "current_streak": 0,
            "longest_streak": 0,
            "completion_rate": 0,
            "completed_days": 0,
            "missed_days": 0,
        }

    completed_days = 0
    missed_days = 0
    longest_streak = 0
    running_streak = 0

    for d in scheduled_days:
        info = heatmap[d]
        is_hit = (info["count"] >= info["due"]) if scope == "global" else (info["count"] > 0)
        if is_hit:
            completed_days += 1
            running_streak += 1
            if running_streak > longest_streak:
                longest_streak = running_streak
        else:
            if d == today_str:
                continue
            missed_days += 1
            running_streak = 0

    current_streak = 0
    for d in reversed(scheduled_days):
        info = heatmap[d]
        is_hit = (info["count"] >= info["due"]) if scope == "global" else (info["count"] > 0)
        if is_hit:
            current_streak += 1
        else:
            if d == today_str:
                continue
            break

    total_eval = completed_days + missed_days
    rate = round((completed_days / total_eval) * 100) if total_eval > 0 else 0

    return {
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "completion_rate": rate,
        "completed_days": completed_days,
        "missed_days": missed_days,
    }


def get_habit_unit_logs(habit_name, start_override=None, end_override=None):
    if not habit_name:
        return None, []
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, unit FROM tasks WHERE name = ? AND unit IS NOT NULL AND unit != 'None'",
        (habit_name,),
    )
    task_rows = cursor.fetchall()
    if not task_rows:
        conn.close()
        return None, []

    unit_name = task_rows[0][1]
    task_ids = [r[0] for r in task_rows]
    placeholders = ",".join("?" for _ in task_ids)

    cursor.execute(
        f"""
        SELECT substr(completed_date, 1, 10) as d_str, SUM(amount)
        FROM task_completions
        WHERE task_id IN ({placeholders}) AND amount IS NOT NULL
        GROUP BY d_str
        ORDER BY d_str ASC
        """,
        task_ids,
    )
    logs = [(r[0], r[1]) for r in cursor.fetchall()]
    conn.close()

    iso_start = parse_ui_date_to_iso(start_override) if start_override else None
    iso_end = parse_ui_date_to_iso(end_override) if end_override else None
    if iso_start:
        logs = [item for item in logs if item[0] >= iso_start]
    if iso_end:
        logs = [item for item in logs if item[0] <= iso_end]

    # Evaluate multi-goals whenever logs are fetched
    evaluate_habit_goals_progress(habit_name, logs)
    return unit_name, logs


def get_habit_trend_data(scope="global", identifier=None):
    all_tasks = fetch_all_tasks()
    scoped_tasks = _filter_tasks_by_scope(all_tasks, scope, identifier)
    if not scoped_tasks:
        return {}

    task_ids = [t[0] for t in scoped_tasks]
    placeholders = ",".join("?" for _ in task_ids)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        SELECT substr(completed_date, 1, 10), amount
        FROM task_completions
        WHERE task_id IN ({placeholders})
        ORDER BY completed_date ASC
        """,
        task_ids,
    )
    rows = cursor.fetchall()
    conn.close()

    weekly_totals = {}
    for d_str, amt in rows:
        try:
            dt = datetime.strptime(d_str, "%Y-%m-%d")
            iso_yr, iso_wk, _ = dt.isocalendar()
            wk_key = f"{iso_yr}-W{iso_wk:02d}"
            val = amt if (scope == "habit" and amt is not None) else 1
            weekly_totals[wk_key] = weekly_totals.get(wk_key, 0) + val
        except Exception:
            pass

    return weekly_totals


# --- Multi-Goal System (Peak/Max, Weekly Avg, All-Time Avg + Completion Windows) ---
def add_habit_goal_db(habit_name: str, goal_type: str, target_value: float, start_date: str, end_date: str = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO habit_goals_history (habit_name, goal_type, target_value, start_date, end_date, achieved, achieved_date)
        VALUES (?, ?, ?, ?, ?, 0, NULL)
        """,
        (habit_name, goal_type, target_value, start_date, end_date),
    )
    conn.commit()
    conn.close()


def delete_habit_goal_db(goal_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM habit_goals_history WHERE id = ?", (goal_id,))
    conn.commit()
    conn.close()


def evaluate_habit_goals_progress(habit_name: str, all_logs: list):
    """Checks all unachieved goals for this habit and marks them achieved if hit within their window."""
    if not all_logs:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, goal_type, target_value, start_date, end_date, achieved
        FROM habit_goals_history
        WHERE habit_name = ?
        ORDER BY id ASC
        """,
        (habit_name,),
    )
    goals = cursor.fetchall()

    for gid, gtype, target_val, s_date, e_date, achieved in goals:
        if achieved:
            continue
        window_logs = [
            (d, val) for d, val in all_logs
            if (not s_date or d >= s_date) and (not e_date or d <= e_date)
        ]
        if not window_logs:
            continue

        hit_date = None
        if gtype == "max":
            for d, val in window_logs:
                if val >= target_val:
                    hit_date = d
                    break
        elif gtype == "all_time_avg":
            running_sum = 0.0
            for idx, (d, val) in enumerate(window_logs, 1):
                running_sum += val
                if (running_sum / idx) >= target_val:
                    hit_date = d
                    break
        elif gtype == "weekly_avg":
            # Check 7-day rolling window average or ISO week average
            for idx, (d_str, val) in enumerate(window_logs):
                d_dt = datetime.strptime(d_str, "%Y-%m-%d")
                w_start = (d_dt - timedelta(days=6)).strftime("%Y-%m-%d")
                wk_vals = [v for dt_s, v in window_logs[: idx + 1] if dt_s >= w_start]
                if wk_vals and (sum(wk_vals) / len(wk_vals)) >= target_val:
                    hit_date = d_str
                    break

        if hit_date:
            cursor.execute(
                "UPDATE habit_goals_history SET achieved = 1, achieved_date = ? WHERE id = ?",
                (hit_date, gid),
            )

    conn.commit()
    conn.close()


def get_habit_goals_list(habit_name: str) -> list:
    if not habit_name:
        return []
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, goal_type, target_value, start_date, end_date, achieved, achieved_date
        FROM habit_goals_history
        WHERE habit_name = ?
        ORDER BY achieved ASC, id DESC
        """,
        (habit_name,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "goal_type": r[1],
            "target_value": r[2],
            "start_date": r[3],
            "end_date": r[4],
            "achieved": bool(r[5]),
            "achieved_date": r[6],
        }
        for r in rows
    ]


# Keep legacy wrappers so nothing in older code breaks
def get_habit_goals(habit_name):
    goals = get_habit_goals_list(habit_name)
    if goals:
        active = next((g for g in goals if not g["achieved"]), goals[0])
        return active["target_value"], (1 if active["goal_type"] != "max" else 0), None
    return None, 0, None


def update_habit_goals(habit_name, target_goal, is_average_goal, hard_limit):
    if habit_name and target_goal is not None:
        gtype = "all_time_avg" if is_average_goal else "max"
        add_habit_goal_db(habit_name, gtype, target_goal, datetime.now().strftime("%Y-%m-%d"), None)
# =============================================================================
# >>> SECTION B5 END: ANALYTICS, HEATMAPS, STREAKS & GOALS <<<
# =============================================================================

# =============================================================================
# >>> SECTION B6: APP SETTINGS & THEME PERSISTENCE <<<
# =============================================================================
def init_settings_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    conn.commit()
    conn.close()

def get_all_settings() -> dict:
    init_settings_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM app_settings")
    rows = cursor.fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}

def save_setting(key: str, value: str):
    init_settings_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO app_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()
    conn.close()

# =============================================================================
# >>> SECTION B6 END: APP SETTINGS & THEME PERSISTENCE <<<
# =============================================================================