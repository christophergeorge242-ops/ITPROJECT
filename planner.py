from datetime import date, timedelta
import math
import os
from pathlib import Path
import sqlite3
import sys

from flask import Flask, jsonify, render_template, request


APP_DIR = Path(__file__).resolve().parent
DATABASE_PATH = APP_DIR / "study_planner.db"
SCHEMA_PATH = APP_DIR / "schema.sql"
app = Flask(__name__)


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
        # Upgrade databases created before session completion was tracked.
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(schedule_entries)")}
        if "completed" not in columns:
            connection.execute(
                "ALTER TABLE schedule_entries ADD COLUMN completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1))"
            )
        if "missed" not in columns:
            connection.execute(
                "ALTER TABLE schedule_entries ADD COLUMN missed INTEGER NOT NULL DEFAULT 0 CHECK (missed IN (0, 1))"
            )
        connection.commit()
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

    replan_if_configured()
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

    summary = build_schedule(daily_limit)

    if not summary:
        print("No unfinished tasks to schedule.")
        return

    print(f"\nSchedule generated with a {daily_limit:g}-hour daily limit.")
    print("All calendar days are treated as available; deadlines are not study days.")
    for task in summary:
        print(
            f"Task #{task['id']} ({task['title']}): "
            f"{task['planned_hours']:g}/{task['estimated_hours']:g} hours scheduled"
        )
        if task["unscheduled_hours"] > 0:
            print(
                f"  Could not fit {task['unscheduled_hours']:g} hours before "
                f"the {task['due_date']} deadline."
            )


def build_schedule(daily_limit):
    today = date.today()
    connection = connect_to_database()
    try:
        tasks = connection.execute(
            """SELECT id, title, subject_id, due_date, estimated_hours, priority
               FROM tasks
               WHERE completed = 0"""
        ).fetchall()
        tasks.sort(
            key=lambda task: (
                date.fromisoformat(task["due_date"])
                - timedelta(days=task["priority"] - 1),
                date.fromisoformat(task["due_date"]),
                -task["priority"],
                task["id"],
            )
        )

    
        # Keep finished sessions fixed. Only unfinished sessions are moved.
        connection.execute(
            "DELETE FROM schedule_entries WHERE completed = 0 AND missed = 0"
        )
        fixed_entries = connection.execute(
            """SELECT schedule_entries.task_id, schedule_entries.study_date,
                      schedule_entries.planned_hours, tasks.subject_id
               FROM schedule_entries JOIN tasks ON tasks.id = schedule_entries.task_id
               WHERE schedule_entries.completed = 1"""
        ).fetchall()
        missed_entries = connection.execute(
            "SELECT task_id, study_date FROM schedule_entries WHERE missed = 1"
        ).fetchall()
        connection.execute(
            """INSERT INTO planner_settings (id, daily_study_limit)
               VALUES (1, ?)
               ON CONFLICT(id) DO UPDATE SET daily_study_limit = excluded.daily_study_limit""",
            (daily_limit,),
        )

        hours_by_day = {}
        subject_hours_by_day = {}
        completed_by_task = {}
        completed_days_by_task = {}
        missed_days_by_task = {}
        for entry in fixed_entries:
            day = date.fromisoformat(entry["study_date"])
            hours_by_day[day] = round(hours_by_day.get(day, 0) + entry["planned_hours"], 2)
            subject_key = (day, entry["subject_id"])
            subject_hours_by_day[subject_key] = round(
                subject_hours_by_day.get(subject_key, 0) + entry["planned_hours"], 2
            )
            completed_by_task[entry["task_id"]] = round(
                completed_by_task.get(entry["task_id"], 0) + entry["planned_hours"], 2
            )
            completed_days_by_task.setdefault(entry["task_id"], set()).add(day)
        for entry in missed_entries:
            missed_days_by_task.setdefault(entry["task_id"], set()).add(
                date.fromisoformat(entry["study_date"])
            )
        task_summaries = []

        for task in tasks:
            remaining = max(0, round(float(task["estimated_hours"]) - completed_by_task.get(task["id"], 0), 2))
            due_date = date.fromisoformat(task["due_date"])
            available_days = []
            study_day = today
            while study_day < due_date:
                if (
                    study_day not in completed_days_by_task.get(task["id"], set())
                    and study_day not in missed_days_by_task.get(task["id"], set())
                ):
                    available_days.append(study_day)
                study_day += timedelta(days=1)

            # Priority advances a task's effective deadline. Within each task,
            # prefer dates with less of its subject, then lighter days.
            available_days.sort(
                key=lambda day: (
                    subject_hours_by_day.get((day, task["subject_id"]), 0),
                    hours_by_day.get(day, 0),
                    day,
                )
            )
            for study_day in available_days:
                if remaining <= 0:
                    break
                free_hours = round(daily_limit - hours_by_day.get(study_day, 0), 2)
                if free_hours <= 0:
                    continue
                free_days = sum(
                    1 for candidate in available_days
                    if hours_by_day.get(candidate, 0) < daily_limit
                )
                target_for_day = remaining / max(free_days, 1)
                planned_hours = round(min(remaining, target_for_day, free_hours), 2)
                if planned_hours <= 0:
                    planned_hours = round(min(remaining, free_hours), 2)
                if planned_hours <= 0:
                    continue

                connection.execute(
                    """INSERT INTO schedule_entries
                       (task_id, study_date, planned_hours)
                       VALUES (?, ?, ?)""",
                    (task["id"], study_day.isoformat(), planned_hours),
                )
                hours_by_day[study_day] = round(
                    hours_by_day.get(study_day, 0) + planned_hours, 2
                )
                subject_key = (study_day, task["subject_id"])
                subject_hours_by_day[subject_key] = round(
                    subject_hours_by_day.get(subject_key, 0) + planned_hours, 2
                )
                remaining = round(remaining - planned_hours, 2)

            task_summaries.append(
                {
                    "id": task["id"],
                    "title": task["title"],
                    "due_date": task["due_date"],
                    "estimated_hours": round(float(task["estimated_hours"]), 2),
                    "planned_hours": round(
                        float(task["estimated_hours"]) - remaining, 2
                    ),
                    "unscheduled_hours": remaining,
                }
            )

        connection.commit()
    finally:
        connection.close()

    return task_summaries


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
               WHERE schedule_entries.missed = 0
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


def analyze_workload():
    connection = connect_to_database()
    try:
        settings = connection.execute(
            "SELECT daily_study_limit FROM planner_settings WHERE id = 1"
        ).fetchone()
        daily_totals = connection.execute(
            """SELECT study_date, SUM(planned_hours) AS total_hours
               FROM schedule_entries
               GROUP BY study_date
               ORDER BY study_date"""
        ).fetchall()
    finally:
        connection.close()

    if not settings:
        print("No schedule yet. Generate a schedule before analyzing workload.")
        return
    if not daily_totals:
        print("No scheduled study hours to analyze.")
        return

    daily_limit = settings["daily_study_limit"]
    overloaded_days = []

    print(f"\nWorkload analysis (daily capacity: {daily_limit:g} hours):")
    for day in daily_totals:
        total_hours = round(day["total_hours"], 2)
        if total_hours > daily_limit:
            excess_hours = round(total_hours - daily_limit, 2)
            overloaded_days.append(day["study_date"])
            status = f"OVER CAPACITY by {excess_hours:g}h"
        else:
            status = "Within capacity"
        print(f"{day['study_date']}: {total_hours:g}h / {daily_limit:g}h — {status}")

    if overloaded_days:
        print(f"Found {len(overloaded_days)} overloaded day(s).")
    else:
        print("No days exceed the daily study capacity.")


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

    replan_if_configured()
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

    replan_if_configured()
    print(f"Removed task #{task['id']}.")


def normalize_task_payload(data):
    title = str(data.get("title", "")).strip()
    subject = str(data.get("subject", "")).strip()
    due_date_text = str(data.get("due_date", "")).strip()

    if not title or len(title) > 255:
        return None, "Enter a task title up to 255 characters."
    if not subject or len(subject) > 150:
        return None, "Enter a subject up to 150 characters."

    try:
        parsed_due_date = date.fromisoformat(due_date_text)
        if parsed_due_date.isoformat() != due_date_text:
            raise ValueError
    except ValueError:
        return None, "Enter a valid due date in YYYY-MM-DD format."

    try:
        estimated_hours = float(data.get("estimated_hours", 0))
        if not math.isfinite(estimated_hours) or estimated_hours < 0:
            raise ValueError
        estimated_hours = round(estimated_hours, 2)
    except (TypeError, ValueError):
        return None, "Estimated hours must be a number greater than or equal to 0."

    try:
        priority = int(data.get("priority", 2))
        if priority not in (1, 2, 3):
            raise ValueError
    except (TypeError, ValueError):
        return None, "Priority must be 1 (low), 2 (medium), or 3 (high)."

    return {
        "title": title,
        "subject": subject,
        "due_date": due_date_text,
        "estimated_hours": estimated_hours,
        "priority": priority,
    }, None


def save_subject(connection, subject):
    connection.execute(
        "INSERT INTO subjects (name) VALUES (?) ON CONFLICT(name) DO NOTHING",
        (subject,),
    )
    return connection.execute(
        "SELECT id FROM subjects WHERE name = ?", (subject,)
    ).fetchone()["id"]


def replan_if_configured():
    connection = connect_to_database()
    try:
        settings = connection.execute(
            "SELECT daily_study_limit FROM planner_settings WHERE id = 1"
        ).fetchone()
    finally:
        connection.close()
    if settings:
        return build_schedule(settings["daily_study_limit"])
    return None


@app.get("/")
def home_page():
    return render_template("index.html")


@app.get("/api/tasks")
def api_list_tasks():
    connection = connect_to_database()
    try:
        tasks = connection.execute(
            """SELECT tasks.id, tasks.title, subjects.name AS subject,
                      tasks.due_date, tasks.estimated_hours,
                      tasks.priority, tasks.completed
               FROM tasks
               JOIN subjects ON subjects.id = tasks.subject_id
               ORDER BY tasks.due_date, tasks.priority DESC, tasks.id"""
        ).fetchall()
        return jsonify([dict(task) for task in tasks])
    finally:
        connection.close()


@app.post("/api/tasks")
def api_add_task():
    task, error = normalize_task_payload(request.get_json(silent=True) or {})
    if error:
        return jsonify(error=error), 400

    connection = connect_to_database()
    try:
        subject_id = save_subject(connection, task["subject"])
        cursor = connection.execute(
            """INSERT INTO tasks
               (title, subject_id, due_date, estimated_hours, priority)
               VALUES (?, ?, ?, ?, ?)""",
            (
                task["title"], subject_id, task["due_date"],
                task["estimated_hours"], task["priority"],
            ),
        )
        task_id = cursor.lastrowid
        connection.commit()
    finally:
        connection.close()

    replan_if_configured()
    return jsonify(get_task(task_id)), 201


@app.put("/api/tasks/<int:task_id>")
def api_edit_task(task_id):
    task, error = normalize_task_payload(request.get_json(silent=True) or {})
    if error:
        return jsonify(error=error), 400
    if not get_task(task_id):
        return jsonify(error="Task not found."), 404

    connection = connect_to_database()
    try:
        subject_id = save_subject(connection, task["subject"])
        connection.execute(
            """UPDATE tasks
               SET title = ?, subject_id = ?, due_date = ?,
                   estimated_hours = ?, priority = ?
               WHERE id = ?""",
            (
                task["title"], subject_id, task["due_date"],
                task["estimated_hours"], task["priority"], task_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    replan_if_configured()
    return jsonify(get_task(task_id))


@app.delete("/api/tasks/<int:task_id>")
def api_remove_task(task_id):
    connection = connect_to_database()
    try:
        cursor = connection.execute("SELECT id FROM tasks WHERE id = ?", (task_id,))
        if not cursor.fetchone():
            return jsonify(error="Task not found."), 404
        connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        connection.commit()
    finally:
        connection.close()
    replan_if_configured()
    return jsonify(message="Task removed.")


def load_schedule_data():
    connection = connect_to_database()
    try:
        settings = connection.execute(
            "SELECT daily_study_limit FROM planner_settings WHERE id = 1"
        ).fetchone()
        entries = connection.execute(
            """SELECT schedule_entries.study_date,
                      schedule_entries.planned_hours,
                      schedule_entries.completed AS session_completed,
                      tasks.id AS task_id, tasks.title,
                      subjects.name AS subject
               FROM schedule_entries
               JOIN tasks ON tasks.id = schedule_entries.task_id
               JOIN subjects ON subjects.id = tasks.subject_id
               WHERE schedule_entries.missed = 0
               ORDER BY schedule_entries.study_date, tasks.id"""
        ).fetchall()
        tasks = connection.execute(
            """SELECT tasks.id, tasks.title, tasks.due_date,
                      tasks.estimated_hours,
                      COALESCE(SUM(CASE WHEN schedule_entries.missed = 0
                                        THEN schedule_entries.planned_hours ELSE 0 END), 0)
                          AS scheduled_hours
               FROM tasks
               LEFT JOIN schedule_entries ON schedule_entries.task_id = tasks.id
               WHERE tasks.completed = 0
               GROUP BY tasks.id
               ORDER BY tasks.due_date, tasks.id"""
        ).fetchall()
    finally:
        connection.close()

    days = {}
    for entry in entries:
        study_day = days.setdefault(
            entry["study_date"], {"date": entry["study_date"], "total_hours": 0, "sessions": []}
        )
        study_day["total_hours"] = round(
            study_day["total_hours"] + entry["planned_hours"], 2
        )
        study_day["sessions"].append(
            {
                "task_id": entry["task_id"],
                "title": entry["title"],
                "subject": entry["subject"],
                "hours": entry["planned_hours"],
                "completed": bool(entry["session_completed"]),
            }
        )

    unscheduled = []
    for task in tasks:
        remaining = round(float(task["estimated_hours"]) - task["scheduled_hours"], 2)
        if remaining > 0:
            unscheduled.append(
                {
                    "id": task["id"],
                    "title": task["title"],
                    "due_date": task["due_date"],
                    "hours": remaining,
                }
            )

    return {
        "daily_limit": settings["daily_study_limit"] if settings else None,
        "days": list(days.values()),
        "unscheduled": unscheduled,
    }


@app.get("/api/schedule")
def api_get_schedule():
    # Past unfinished sessions count as missed and are moved forward on refresh.
    replan_if_configured()
    return jsonify(load_schedule_data())


@app.post("/api/schedule")
def api_generate_schedule():
    data = request.get_json(silent=True) or {}
    try:
        daily_limit = round(float(data.get("daily_limit", 0)), 2)
        if not math.isfinite(daily_limit) or daily_limit <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify(error="Daily study limit must be greater than 0."), 400

    build_schedule(daily_limit)
    return jsonify(load_schedule_data())


@app.post("/api/schedule/session")
def api_update_session():
    data = request.get_json(silent=True) or {}
    try:
        task_id = int(data.get("task_id"))
        study_date = date.fromisoformat(str(data.get("date", "")))
        if study_date.isoformat() != data.get("date"):
            raise ValueError
    except (TypeError, ValueError):
        return jsonify(error="Choose a valid study session."), 400
    action = data.get("action")
    if action not in ("completed", "missed"):
        return jsonify(error="Session action must be completed or missed."), 400

    connection = connect_to_database()
    try:
        row = connection.execute(
            "SELECT completed, missed FROM schedule_entries WHERE task_id = ? AND study_date = ?",
            (task_id, study_date.isoformat()),
        ).fetchone()
        if not row:
            return jsonify(error="Study session not found."), 404
        if row["completed"]:
            return jsonify(error="Completed work is preserved and cannot be rescheduled."), 409
        if row["missed"]:
            return jsonify(error="This session was already marked missed."), 409
        if action == "completed":
            connection.execute(
                "UPDATE schedule_entries SET completed = 1 WHERE task_id = ? AND study_date = ?",
                (task_id, study_date.isoformat()),
            )
        else:
            connection.execute(
                "UPDATE schedule_entries SET missed = 1 WHERE task_id = ? AND study_date = ?",
                (task_id, study_date.isoformat()),
            )
        setting = connection.execute(
            "SELECT daily_study_limit FROM planner_settings WHERE id = 1"
        ).fetchone()
        connection.commit()
    finally:
        connection.close()

    if setting:
        build_schedule(setting["daily_study_limit"])
    return jsonify(load_schedule_data())


@app.get("/api/workload")
def api_workload():
    schedule = load_schedule_data()
    daily_limit = schedule["daily_limit"]
    for day in schedule["days"]:
        day["over_capacity"] = daily_limit is not None and day["total_hours"] > daily_limit
        day["excess_hours"] = (
            round(day["total_hours"] - daily_limit, 2)
            if day["over_capacity"] else 0
        )
    return jsonify(schedule)


def main():
    initialize_database()
    print("Smart Study Planner — Steps 2–4: manage tasks, plan, and analyze workload")

    while True:
        print(
            "\n1. Add a task\n2. List tasks\n3. Generate a schedule\n"
            "4. View the schedule\n5. Analyze workload\n"
            "6. Edit a task\n7. Remove a task\n8. Exit"
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
            analyze_workload()
        elif choice == "6":
            edit_task()
        elif choice == "7":
            remove_task()
        elif choice == "8":
            print("Goodbye.")
            break
        else:
            print("Choose a number from 1 to 8.")


def run_web_app():
    initialize_database()
    port = int(os.environ.get("STUDY_PLANNER_PORT", "5000"))
    print(f"Open the planner at http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    if "--cli" in sys.argv:
        initialize_database()
        main()
    else:
        run_web_app()
