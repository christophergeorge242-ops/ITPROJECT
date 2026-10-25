# Smart Study Planner and Workload Analyzer

A small app that helps a student organize assignments and study tasks by deadline, estimated effort, and priority. It will create a schedule and point out overloaded days or competing deadlines. Python stores task data in a local SQLite database.

## Build it step by step

1. **Basics and data:** decide what one task contains and save tasks in SQLite.
2. **Task entry:** add, list, edit, and remove tasks.
3. **First schedule:** split estimated hours into available study time before each deadline.
4. **Workload analysis:** total planned hours by day and flag days that exceed the student's capacity.
5. **Interactive UI:** make task entry and the schedule easy to use. The Flask UI is now available.
6. **Improve the scheduler:** account for priority, subject balance, and changes to availability.

The first version keeps each task simple: a title, subject, due date, estimated hours, and priority. A task is stored separately from its subject so that several tasks can belong to the same subject.

## Basic data model

- **Subject:** a course or topic, such as Biology.
- **Task:** a piece of work for one subject, with a deadline and estimated effort.
- **Priority:** an integer from 1 (low) to 3 (high).
- **Study plan:** generated schedule entries that connect a task to a date and number of planned hours.

The database schema is in [`schema.sql`](schema.sql). It creates subjects, tasks, a daily study limit setting, and schedule entries. [`planner.py`](planner.py) runs the interactive app and its local API. The HTML, styles, and browser interactions live in `templates/` and `static/`.

### Run the app

Install Python 3 if it is not already installed. SQLite is included with Python; Flask provides the local web interface.

From this project folder, install Flask and start the app:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe planner.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser. Use the side navigation to move between Overview, Tasks, Study plan, and Workload. Add and edit tasks in the Tasks view, generate a plan from Study plan, and see daily capacity checks in Workload. The app keeps tasks and schedules in `study_planner.db` in this folder.

The previous terminal menu is still available with `python planner.py --cli`.

## Scheduling idea

The scheduler treats every calendar day from today through the day before a deadline as available. It uses priority to bring high priority tasks forward, then spreads task hours across dates with lighter daily workloads and less time already assigned to the same subject. The daily study availability setting limits each day's total. Mark a session Done to keep its completed hours fixed, or Missed to redistribute those hours across the remaining days. Past unfinished sessions are treated as missed when the plan is opened. Adding a task or changing a task or deadline automatically rebuilds the plan when a daily availability setting exists. Completed sessions stay in place; the app reports any remaining hours that do not fit before their deadlines. Workload analysis totals the saved schedule per day and compares it with the current availability.
