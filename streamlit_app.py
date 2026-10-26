from datetime import date

import streamlit as st

import planner


st.set_page_config(page_title="Smart Study Planner", page_icon="📚", layout="wide")
st.title("📚 Smart Study Planner")
st.caption("Organize coursework, build a study plan, and keep daily workload within capacity.")

try:
    planner.initialize_database()
except Exception as exc:
    st.error("Could not connect to the database. Check the DATABASE_URL secret and Supabase schema.")
    st.exception(exc)
    st.stop()


def tasks_data():
    connection = planner.connect_to_database()
    try:
        return connection.execute(
            """SELECT tasks.id, tasks.title, subjects.name AS subject,
                      tasks.due_date, tasks.estimated_hours, tasks.priority, tasks.completed
               FROM tasks JOIN subjects ON subjects.id = tasks.subject_id
               ORDER BY tasks.due_date, tasks.priority DESC, tasks.id"""
        ).fetchall()
    finally:
        connection.close()


def save_task(title, subject, due_date, hours, priority, task_id=None):
    connection = planner.connect_to_database()
    try:
        subject_id = planner.save_subject(connection, subject.strip())
        if task_id is None:
            connection.execute(
                """INSERT INTO tasks (title, subject_id, due_date, estimated_hours, priority)
                   VALUES (?, ?, ?, ?, ?)""",
                (title.strip(), subject_id, due_date.isoformat(), hours, priority),
            )
        else:
            connection.execute(
                """UPDATE tasks SET title = ?, subject_id = ?, due_date = ?,
                   estimated_hours = ?, priority = ? WHERE id = ?""",
                (title.strip(), subject_id, due_date.isoformat(), hours, priority, task_id),
            )
        connection.commit()
    finally:
        connection.close()
    planner.replan_if_configured()


def remove_task(task_id):
    connection = planner.connect_to_database()
    try:
        connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        connection.commit()
    finally:
        connection.close()
    planner.replan_if_configured()


def get_daily_limit():
    connection = planner.connect_to_database()
    try:
        row = connection.execute("SELECT daily_study_limit FROM planner_settings WHERE id = 1").fetchone()
        return row["daily_study_limit"] if row else None
    finally:
        connection.close()


def set_session(task_id, study_date, action):
    connection = planner.connect_to_database()
    try:
        connection.execute(
            "UPDATE schedule_entries SET completed = ? WHERE task_id = ? AND study_date = ?" if action == "completed"
            else "UPDATE schedule_entries SET missed = ? WHERE task_id = ? AND study_date = ?",
            (1, task_id, study_date),
        )
        connection.commit()
    finally:
        connection.close()
    setting = get_daily_limit()
    if setting:
        planner.build_schedule(setting)


with st.sidebar:
    page = st.radio("Navigate", ["Overview", "Tasks", "Study plan", "Workload"])

if page == "Tasks":
    st.subheader("Tasks")
    with st.form("new_task", clear_on_submit=True):
        title = st.text_input("Task title")
        subject = st.text_input("Subject")
        due_date = st.date_input("Due date", min_value=date.today())
        hours = st.number_input("Estimated hours", min_value=0.25, step=0.25)
        priority = st.selectbox("Priority", [1, 2, 3], index=1, format_func=lambda n: {1: "Low", 2: "Medium", 3: "High"}[n])
        if st.form_submit_button("Add task", type="primary"):
            if not title.strip() or not subject.strip():
                st.error("Enter both a task title and subject.")
            else:
                save_task(title, subject, due_date, hours, priority)
                st.success("Task added.")
                st.rerun()

    task_rows = tasks_data()
    if task_rows:
        st.dataframe([dict(row) for row in task_rows], use_container_width=True, hide_index=True)
        task_ids = [row["id"] for row in task_rows]
        selected = st.selectbox("Choose a task to update or remove", task_ids, format_func=lambda i: next(f"#{r['id']} · {r['title']}" for r in task_rows if r["id"] == i))
        selected_task = next(row for row in task_rows if row["id"] == selected)
        with st.expander("Edit selected task"):
            with st.form("edit_task"):
                edit_title = st.text_input("Title", selected_task["title"])
                edit_subject = st.text_input("Subject", selected_task["subject"])
                edit_due = st.date_input("Due date", date.fromisoformat(selected_task["due_date"]), key="edit_due")
                edit_hours = st.number_input("Estimated hours", min_value=0.25, value=float(selected_task["estimated_hours"]), step=0.25, key="edit_hours")
                edit_priority = st.selectbox("Priority", [1, 2, 3], index=int(selected_task["priority"]) - 1, key="edit_priority")
                if st.form_submit_button("Save changes"):
                    save_task(edit_title, edit_subject, edit_due, edit_hours, edit_priority, selected)
                    st.rerun()
        if st.button("Delete selected task", type="secondary"):
            remove_task(selected)
            st.rerun()
    else:
        st.info("No tasks yet. Add one above to get started.")

elif page == "Study plan":
    st.subheader("Study plan")
    current_limit = get_daily_limit()
    with st.form("plan_settings"):
        limit = st.number_input("Daily study availability (hours)", min_value=0.25, value=float(current_limit or 3.0), step=0.25)
        if st.form_submit_button("Generate plan", type="primary"):
            planner.build_schedule(limit)
            st.success("Plan generated.")
    schedule = planner.load_schedule_data()
    for day in schedule["days"]:
        with st.expander(f"{day['date']} · {day['total_hours']:.2f} hours"):
            for session in day["sessions"]:
                col1, col2, col3 = st.columns([5, 1, 2])
                col1.write(f"**{session['title']}** · {session['subject']}")
                col2.write(f"{session['hours']:.2f} h")
                if session["completed"]:
                    col3.caption("Done")
                else:
                    if col3.button("Mark done", key=f"done-{session['task_id']}-{day['date']}"):
                        set_session(session["task_id"], day["date"], "completed")
                        st.rerun()
                    if col3.button("Missed", key=f"missed-{session['task_id']}-{day['date']}"):
                        set_session(session["task_id"], day["date"], "missed")
                        st.rerun()
    if schedule["unscheduled"]:
        st.warning("Some estimated hours do not fit before their deadlines.")
        st.dataframe(schedule["unscheduled"], use_container_width=True, hide_index=True)

elif page == "Workload":
    st.subheader("Workload")
    schedule = planner.load_schedule_data()
    capacity = schedule["daily_limit"]
    if capacity is None:
        st.info("Set daily study availability in Study plan to analyze workload.")
    elif schedule["days"]:
        workload = [{"Date": d["date"], "Planned hours": d["total_hours"], "Daily limit": capacity,
                     "Over capacity": d["total_hours"] > capacity} for d in schedule["days"]]
        st.dataframe(workload, use_container_width=True, hide_index=True)
        st.bar_chart({d["date"]: d["total_hours"] for d in schedule["days"]})
        over = [d for d in schedule["days"] if d["total_hours"] > capacity]
        if over:
            st.warning(f"{len(over)} day(s) exceed your {capacity:g}-hour daily limit.")
        else:
            st.success("All scheduled days are within your daily limit.")
    else:
        st.info("No scheduled sessions yet. Generate a plan first.")

else:
    task_rows = tasks_data()
    schedule = planner.load_schedule_data()
    a, b, c = st.columns(3)
    a.metric("Open tasks", sum(not row["completed"] for row in task_rows))
    b.metric("Upcoming sessions", len(schedule["days"]))
    c.metric("Daily limit", f"{schedule['daily_limit']:g} h" if schedule["daily_limit"] else "Not set")
    st.subheader("Upcoming deadlines")
    upcoming = [dict(row) for row in task_rows if row["due_date"] >= date.today().isoformat() and not row["completed"]]
    if upcoming:
        st.dataframe(upcoming, use_container_width=True, hide_index=True)
    else:
        st.info("No open upcoming tasks. Add tasks or adjust their due dates in Tasks.")
