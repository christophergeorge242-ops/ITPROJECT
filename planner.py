from datetime import date, timedelta
from pathlib import Path
import sqlite3


APP_DIR = Path(__file__).resolve().parent
DATABASE_PATH = APP_DIR / "study_planner.db"
SCHEMA_PATH = APP_DIR / "schema.sql"


def connect_to_database():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    connection = connect_to_database()
    try:
        connection.executescript(schema)
    finally:
        connection.close()


def ask_for_nonempty_text(prompt):
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("enter a value.")


def add_task():
    title = ask_for_nonempty_text("Task title: ")
    subject = ask_for_nonempty_text("Subject (for example, Biology): ")

    while True:
        due_date = input("Due date (YYYY-MM-DD): ").strip()
        try:
            date.fromisoformat(due_date)
            break
        except ValueError:
            print("Enter a real date in YYYY-MM-DD format, for example 2026-11-05.")

    while True:
        try:
            estimated_hours = float(input("Estimated hours: ").strip())
            if estimated_hours > 0:
                break
        except ValueError:
            pass
        print("Estimated hours must be a number greater than 0.")

    while True:
        try:
            priority = int(input("Priority (1 = low, 2 = medium, 3 = high): ").strip())
            if priority in (1, 2, 3):
                break
        except ValueError:
            pass
        print("Choose 1, 2, or 3.")

    connection = connect_to_database()
    try:
        connection.execute(
            "INSERT INTO subjects (name) VALUES (?) ON CONFLICT(name) DO NOTHING",
            (subject,),
        )
        subject_id = connection.execute(
            "SELECT id FROM subjects WHERE name = ?", (subject,)
        ).fetchone()["id"]

        cursor = connection.execute(
            """INSERT INTO tasks
               (title, subject_id, due_date, estimated_hours, priority)
               VALUES (?, ?, ?, ?, ?)""",
            (title, subject_id, date.fromisoformat(due_date).isoformat(), estimated_hours, priority),
        )
        task_id = cursor.lastrowid
        connection.execute("DELETE FROM schedule_entries")
        connection.commit()
    finally:
        connection.close()

    print(f"Saved task #{task_id}: {title}")


def list_tasks():
    connection = connect_to_database()
    try:
        tasks = connection.execute(
            """SELECT tasks.id, tasks.title, subjects.name AS subject,
                      tasks.due_date, tasks.estimated_hours, tasks.priority
               FROM tasks
               JOIN subjects ON subjects.id = tasks.subject_id
               ORDER BY tasks.due_date, tasks.priority DESC, tasks.id"""
        ).fetchall()
    finally:
        connection.close()

    if not tasks:
        print("No tasks saved yet.")
        return

    print("\nSaved tasks:")
    for task in tasks:
        priority_name = {1: "Low", 2: "Medium", 3: "High"}[task["priority"]]
        print(
            f"#{task['id']} | {task['title']} | {task['subject']} | "
            f"due {task['due_date']} | {task['estimated_hours']:g} hours | "
            f"{priority_name} priority"
        )


def generate_schedule():
    while True:
        try:
            daily_limit = round(float(input("Maximum study hours per day: ").strip()), 2)
            if daily_limit > 0:
                break
        except ValueError:
            pass
        print("Enter a number greater than 0 (up to two decimal places).")

    today = date.today()
    connection = connect_to_database()
    try:
        tasks = connection.execute(
            """SELECT id, title, due_date, estimated_hours, priority
               FROM tasks
               WHERE completed = 0
               ORDER BY due_date, priority DESC, id"""
        ).fetchall()

        # Replace the previous plan each time the user generates a schedule.
        connection.execute("DELETE FROM schedule_entries")
        connection.execute(
            """INSERT INTO planner_settings (id, daily_study_limit)
               VALUES (1, ?)
               ON CONFLICT(id) DO UPDATE SET daily_study_limit = excluded.daily_study_limit""",
            (daily_limit,),
        )

        hours_by_day = {}
        task_summaries = []

        for task in tasks:
            remaining = round(float(task["estimated_hours"]), 2)
            due_date = date.fromisoformat(task["due_date"])
            study_day = due_date - timedelta(days=1)

            # Spread work across the days before the deadline, working back
            # from the day before it and respecting the daily study limit.
            while study_day >= today and remaining > 0:
                days_left = (study_day - today).days + 1
                target_for_day = remaining / days_left
                free_hours = round(daily_limit - hours_by_day.get(study_day, 0), 2)
                planned_hours = round(min(remaining, target_for_day, free_hours), 2)

                if planned_hours > 0:
                    connection.execute(
                        """INSERT INTO schedule_entries
                           (task_id, study_date, planned_hours)
                           VALUES (?, ?, ?)""",
                        (task["id"], study_day.isoformat(), planned_hours),
                    )
                    hours_by_day[study_day] = round(
                        hours_by_day.get(study_day, 0) + planned_hours, 2
                    )
                    remaining = round(remaining - planned_hours, 2)

                study_day -= timedelta(days=1)

            task_summaries.append((task, remaining))

        connection.commit()
    finally:
        connection.close()

    if not tasks:
        print("No unfinished tasks to schedule.")
        return

    print(f"\nSchedule generated with a {daily_limit:g}-hour daily limit.")
    print("All calendar days are treated as available; deadlines are not study days.")
    for task, unscheduled_hours in task_summaries:
        planned = round(float(task["estimated_hours"]) - unscheduled_hours, 2)
        print(
            f"Task #{task['id']} ({task['title']}): "
            f"{planned:g}/{task['estimated_hours']:g} hours scheduled"
        )
        if unscheduled_hours > 0:
            print(
                f"  Could not fit {unscheduled_hours:g} hours before "
                f"the {task['due_date']} deadline."
            )


def view_schedule():
    connection = connect_to_database()
    try:
        settings = connection.execute(
            "SELECT daily_study_limit FROM planner_settings WHERE id = 1"
        ).fetchone()
        entries = connection.execute(
            """SELECT schedule_entries.study_date,
                      schedule_entries.planned_hours,
                      tasks.id AS task_id, tasks.title,
                      subjects.name AS subject
               FROM schedule_entries
               JOIN tasks ON tasks.id = schedule_entries.task_id
               JOIN subjects ON subjects.id = tasks.subject_id
               ORDER BY schedule_entries.study_date, tasks.id"""
        ).fetchall()
    finally:
        connection.close()

    if not settings:
        print("No schedule yet. Choose 'Generate a schedule' first.")
        return
    if not entries:
        print("The saved schedule has no study sessions. Generate it again after changing tasks.")
        return

    print(f"\nStudy schedule (daily limit: {settings['daily_study_limit']:g} hours):")
    entries_by_day = {}
    for entry in entries:
        entries_by_day.setdefault(entry["study_date"], []).append(entry)

    for study_day, day_entries in entries_by_day.items():
        day_total = round(sum(entry["planned_hours"] for entry in day_entries), 2)
        print(f"\n{study_day} — {day_total:g} hours")
        for entry in day_entries:
            print(
                f"  {entry['planned_hours']:g}h — Task #{entry['task_id']}: "
                f"{entry['title']} ({entry['subject']})"
            )


def get_task(task_id):
    connection = connect_to_database()
    try:
        row = connection.execute(
            """SELECT tasks.id, tasks.title, tasks.due_date,
                      tasks.estimated_hours, tasks.priority,
                      subjects.name AS subject
               FROM tasks
               JOIN subjects ON subjects.id = tasks.subject_id
               WHERE tasks.id = ?""",
            (task_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def ask_for_task_id():
    while True:
        try:
            task_id = int(input("Task number: ").strip())
            if task_id > 0:
                task = get_task(task_id)
                if task:
                    return task
                print("No task found with that number.")
            else:
                print("Enter a task number greater than 0.")
        except ValueError:
            print("Enter the task number shown in the task list.")


def edit_task():
    print("Enter the task number to edit. Press Enter on a field to keep its current value.")
    task = ask_for_task_id()

    title = input(f"Title [{task['title']}]: ").strip() or task["title"]
    subject = input(f"Subject [{task['subject']}]: ").strip() or task["subject"]

    while True:
        due_date_text = input(f"Due date [{task['due_date']}] (YYYY-MM-DD): ").strip()
        if not due_date_text:
            due_date = task["due_date"]
            break
        try:
            due_date = date.fromisoformat(due_date_text).isoformat()
            break
        except ValueError:
            print("Enter a real date in YYYY-MM-DD format.")

    while True:
        hours_text = input(f"Estimated hours [{task['estimated_hours']:g}]: ").strip()
        if not hours_text:
            estimated_hours = task["estimated_hours"]
            break
        try:
            estimated_hours = float(hours_text)
            if estimated_hours > 0:
                break
        except ValueError:
            pass
        print("Estimated hours must be a number greater than 0.")

    while True:
        priority_text = input(f"Priority (1 low, 2 medium, 3 high) [{task['priority']}]: ").strip()
        if not priority_text:
            priority = task["priority"]
            break
        try:
            priority = int(priority_text)
            if priority in (1, 2, 3):
                break
        except ValueError:
            pass
        print("Choose 1, 2, or 3.")

    connection = connect_to_database()
    try:
        connection.execute(
            "INSERT INTO subjects (name) VALUES (?) ON CONFLICT(name) DO NOTHING",
            (subject,),
        )
        subject_id = connection.execute(
            "SELECT id FROM subjects WHERE name = ?", (subject,)
        ).fetchone()["id"]
        connection.execute(
            """UPDATE tasks
               SET title = ?, subject_id = ?, due_date = ?,
                   estimated_hours = ?, priority = ?
               WHERE id = ?""",
            (title, subject_id, due_date, estimated_hours, priority, task["id"]),
        )
        connection.execute("DELETE FROM schedule_entries")
        connection.commit()
    finally:
        connection.close()

    print(f"Updated task #{task['id']}.")


def remove_task():
    print("Enter the task number to remove.")
    task = ask_for_task_id()
    confirmation = input(f"Remove '{task['title']}'? (y/N): ").strip().lower()
    if confirmation != "y":
        print("Removal cancelled.")
        return

    connection = connect_to_database()
    try:
        connection.execute("DELETE FROM schedule_entries")
        connection.execute("DELETE FROM tasks WHERE id = ?", (task["id"],))
        connection.commit()
    finally:
        connection.close()

    print(f"Removed task #{task['id']}.")


def main():
    initialize_database()
    print("Smart Study Planner — Steps 2 and 3: manage tasks and plan study time")

    while True:
        print(
            "\n1. Add a task\n2. List tasks\n3. Generate a schedule\n"
            "4. View the schedule\n5. Edit a task\n6. Remove a task\n7. Exit"
        )
        choice = input("Choose an option: ").strip()

        if choice == "1":
            add_task()
        elif choice == "2":
            list_tasks()
        elif choice == "3":
            generate_schedule()
        elif choice == "4":
            view_schedule()
        elif choice == "5":
            edit_task()
        elif choice == "6":
            remove_task()
        elif choice == "7":
            print("Goodbye.")
            break
        else:
            print("Choose a number from 1 to 7.")


if __name__ == "__main__":
    main()
