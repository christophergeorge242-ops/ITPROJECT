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
- **Study plan:** later, generated schedule entries that connect a task to a date and number of planned hours.

The initial database schema is in [`schema.sql`](schema.sql). It creates subjects and tasks; generated schedule entries come in a later step. [`planner.py`](planner.py) provides a menu to add, list, edit, and remove tasks.

### Run step 1

Install Python 3 if it is not already installed. SQLite is included with Python, so no database server or extra package is needed.

Then start the app from this project folder:

```text
python planner.py
```

Choose **1** to add a task, **2** to list tasks, **3** to edit a task, or **4** to remove one. During editing, press Enter to keep a field's current value. Removal asks for confirmation. The program creates `study_planner.db` in this folder and keeps the tasks there after it exits.

## Scheduling idea

For a task due on a future date, the planner will look at the available study days before that date and distribute the estimated hours across them. It will then total hours across all tasks for each day. If a day's total is above the student's daily study limit, that day is a workload conflict.

This first scheduling rule is intentionally basic. Priority-aware ordering and subject balancing are later improvements, after the data and schedule are working.
