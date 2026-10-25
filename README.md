# Smart Study Planner and Workload Analyzer

A small app that helps a student organize assignments and study tasks by deadline, estimated effort, and priority. It will create a schedule and point out overloaded days or competing deadlines. Python stores task data in a local SQLite database.

## Build it step by step

1. **Basics and data:** decide what one task contains and save tasks in SQLite.
2. **Task entry:** add, list, edit, and remove tasks.
3. **First schedule:** split estimated hours into available study time before each deadline.
4. **Workload analysis:** total planned hours by day and flag days that exceed the student's capacity.
5. **Interactive UI:** make task entry and the schedule easy to use.
6. **Improve the scheduler:** account for priority, subject balance, and changes to availability.

The first version keeps each task simple: a title, subject, due date, estimated hours, and priority. A task is stored separately from its subject so that several tasks can belong to the same subject.

## Basic data model

- **Subject:** a course or topic, such as Biology.
- **Task:** a piece of work for one subject, with a deadline and estimated effort.
- **Priority:** an integer from 1 (low) to 3 (high).
- **Study plan:** generated schedule entries that connect a task to a date and number of planned hours.

The database schema is in [`schema.sql`](schema.sql). It creates subjects, tasks, a daily study limit setting, and schedule entries. [`planner.py`](planner.py) provides a menu to add, list, edit, remove, and schedule tasks.

### Run the app

Install Python 3 if it is not already installed. SQLite is included with Python, so no database server or extra package is needed.

Then start the app from this project folder:

```text
python planner.py
```

Choose **1** to add a task, **2** to list tasks, **3** to generate a schedule, **4** to view it, **5** to analyze workload, **6** to edit a task, **7** to remove one, or **8** to exit. Schedule generation asks for the maximum study hours per day. Workload analysis totals scheduled hours by day and flags any day over that limit. During editing, press Enter to keep a field's current value. Removal asks for confirmation. The program creates `study_planner.db` in this folder and keeps tasks and schedules there after it exits.

## Scheduling idea

The first scheduler treats every calendar day from today through the day before a deadline as available. It orders tasks by deadline and then priority, and spreads each task's estimated hours across that date range while staying under the daily study limit. The due date itself is reserved for submission. If there is not enough capacity, it reports the hours it could not schedule. Workload analysis totals the saved schedule per day and compares it with the daily limit. Adding, editing, or removing a task clears the old schedule, so generate it again after changing tasks.

This first scheduling rule is intentionally basic. Priority-aware ordering and subject balancing are later improvements, after the data and schedule are working.
