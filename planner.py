from datetime import date
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
        connection.execute("DELETE FROM tasks WHERE id = ?", (task["id"],))
        connection.commit()
    finally:
        connection.close()

    print(f"Removed task #{task['id']}.")


def main():
    initialize_database()
    print("Smart Study Planner — Step 2: manage tasks in SQLite")

    while True:
        print("\n1. Add a task\n2. List tasks\n3. Edit a task\n4. Remove a task\n5. Exit")
        choice = input("Choose an option: ").strip()

        if choice == "1":
            add_task()
        elif choice == "2":
            list_tasks()
        elif choice == "3":
            edit_task()
        elif choice == "4":
            remove_task()
        elif choice == "5":
            print("Goodbye.")
            break
        else:
            print("Choose 1, 2, 3, 4, or 5.")


if __name__ == "__main__":
    main()
