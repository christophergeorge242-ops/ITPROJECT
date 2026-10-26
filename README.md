# Smart Study Planner and Workload Analyzer

A small app that helps a student organize assignments and study tasks by deadline, estimated effort, and priority. It creates a schedule and points out overloaded days or competing deadlines. Use Streamlit with Supabase Postgres for deployment, or run the existing Flask app locally with SQLite.

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

The local SQLite schema is in [`schema.sql`](schema.sql); [`schema.postgres.sql`](schema.postgres.sql) is used automatically for Supabase Postgres. [`planner.py`](planner.py) contains the scheduling logic and local Flask app; [`streamlit_app.py`](streamlit_app.py) is the cloud UI.

### Deploy with Supabase and Streamlit Community Cloud

1. Create a Supabase project. In **Project Settings → Database**, copy the connection string for the **Session pooler** and replace its password placeholder. Use the URI form (`postgresql://...`) and keep the password private.
2. Push this `ITPROJECT` repository to GitHub.
3. In Streamlit Community Cloud, create an app from that repository, set the app file to `streamlit_app.py`, and choose the repository's `ITPROJECT` folder as the app root if the project is nested in a larger repository.
4. In the app's **Settings → Secrets**, add:

   ```toml
   DATABASE_URL = "postgresql://postgres.[project-ref]:[YOUR-PASSWORD]@[pooler-host]:5432/postgres?sslmode=require"
   ```

   Use the exact Session pooler URI shown by Supabase for your project; host, username, and port vary. `DATABASE_URL` is a server-side secret. Do not commit it.
5. Deploy. On first startup, the app creates the required tables and indexes in the Supabase database.

The Streamlit entry point is `streamlit_app.py`. Dependencies are in `requirements.txt`. For local Streamlit development, set `DATABASE_URL` in your environment (or `.streamlit/secrets.toml`, which must remain untracked) and run `streamlit run streamlit_app.py`. Without `DATABASE_URL`, the existing Flask app continues to use local SQLite.

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
