from datetime import date

import altair as alt
import streamlit as st

import planner


st.set_page_config(page_title="Smart Study Planner", page_icon="📚", layout="wide")
st.markdown(
    """
    <style>
      .block-container { max-width: 1180px; padding-top: 2.3rem; padding-bottom: 4rem; }
      h1, h2, h3 { letter-spacing: -0.035em; }
      h1 { color: #173b37; font-weight: 650; }
      h2 { color: #173b37; font-weight: 600; }
      [data-testid="stSidebar"] { background: #173b37; }
      [data-testid="stSidebar"] * { color: #eaf2ed; }
      [data-testid="stSidebar"] [data-testid="stRadio"] label { border-radius: 7px; padding: .15rem .35rem; }
      [data-testid="stSidebar"] [data-testid="stRadio"] label:hover { background: rgba(255,255,255,.08); }
      .brand-lockup { display:flex; align-items:center; gap:.7rem; margin:.25rem 0 2.1rem; color:#fff; }
      .brand-mark { display:grid; place-items:center; width:2.45rem; height:2.45rem; border-radius:9px; background:#d4e7dc; font-size:1.35rem; }
      .brand-name { font-size:1.02rem; font-weight:700; letter-spacing:-.02em; }
      .page-kicker { margin:0 0 .45rem; color:#4b7866; font-size:.72rem; font-weight:750; letter-spacing:.13em; text-transform:uppercase; }
      .page-subtitle { margin-top:-.55rem; margin-bottom:1.8rem; color:#73817b; font-size:.98rem; }
      [data-testid="stMetric"] { height:100%; padding:1.05rem 1.2rem; border:1px solid #d9e2dc; border-radius:10px; background:#fff; }
      [data-testid="stMetricLabel"] { color:#73817b; }
      [data-testid="stMetricValue"] { color:#173b37; font-weight:650; }
      [data-testid="stForm"] { padding:1.25rem; border:1px solid #d9e2dc; border-radius:10px; background:#fff; }
      [data-testid="stDataFrame"] { border:1px solid #d9e2dc; border-radius:9px; overflow:hidden; }
      [data-testid="stExpander"] { border-color:#d9e2dc; border-radius:8px; background:rgba(255,255,255,.65); }
      div.stButton > button[kind="primary"], button[kind="primaryFormSubmit"] { border-radius:7px; font-weight:650; }
      @media (max-width: 720px) { .block-container { padding:1.3rem 1rem 3rem; } .brand-lockup { margin-bottom:1rem; } }
    </style>
    """,
    unsafe_allow_html=True,
)

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
    st.markdown('<div class="brand-lockup"><span class="brand-mark">📚</span><span class="brand-name">Smart Study Planner</span></div>', unsafe_allow_html=True)
    page = st.radio("Navigate", ["Overview", "Tasks", "Study plan", "Workload"])

page_details = {
    "Overview": ("YOUR STUDY SPACE", "Overview", "A clear view of deadlines, study time, and what needs attention."),
    "Tasks": ("COURSEWORK", "Tasks & deadlines", "Keep assignments organized by subject, deadline, effort, and priority."),
    "Study plan": ("MAKE A PLAN", "Study plan", "Turn your open tasks into manageable sessions across the week."),
    "Workload": ("DAILY CAPACITY", "Workload", "See how your planned study hours compare with your daily availability."),
}
kicker, heading, subtitle = page_details[page]
st.markdown(f'<p class="page-kicker">{kicker}</p>', unsafe_allow_html=True)
st.title(heading)
st.markdown(f'<p class="page-subtitle">{subtitle}</p>', unsafe_allow_html=True)

if page == "Tasks":
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
        st.dataframe(
            [{"Task": row["title"], "Subject": row["subject"], "Due": row["due_date"],
              "Hours": f'{row["estimated_hours"]:g} h',
              "Priority": {1: "Low", 2: "Medium", 3: "High"}[row["priority"]],
              "Status": "Complete" if row["completed"] else "Open"} for row in task_rows],
            use_container_width=True,
            hide_index=True,
        )
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
                col1, col2, col3, col4 = st.columns([5, 1, 1, 1])
                col1.write(f"**{session['title']}** · {session['subject']}")
                col2.write(f"{session['hours']:.2f} h")
                if session["completed"]:
                    col3.caption("Done")
                else:
                    if col3.button("Done", key=f"done-{session['task_id']}-{day['date']}"):
                        set_session(session["task_id"], day["date"], "completed")
                        st.rerun()
                    if col4.button("Missed", key=f"missed-{session['task_id']}-{day['date']}"):
                        set_session(session["task_id"], day["date"], "missed")
                        st.rerun()
    if schedule["unscheduled"]:
        st.warning("Some estimated hours do not fit before their deadlines.")
        st.dataframe(schedule["unscheduled"], use_container_width=True, hide_index=True)

elif page == "Workload":
    schedule = planner.load_schedule_data()
    capacity = schedule["daily_limit"]
    if capacity is None:
        st.info("Set daily study availability in Study plan to analyze workload.")
    elif schedule["days"]:
        over = [d for d in schedule["days"] if d["total_hours"] > capacity]
        metric_cols = st.columns(3)
        metric_cols[0].metric("Days planned", len(schedule["days"]))
        metric_cols[1].metric("Daily limit", f"{capacity:g} h")
        metric_cols[2].metric("Over capacity", len(over))
        st.write("")
        workload = [
            {
                "date": d["date"],
                "planned": round(d["total_hours"], 2),
                "limit": capacity,
                "status": "Over capacity" if d["total_hours"] > capacity else "Within limit",
            }
            for d in schedule["days"]
        ]
        chart = alt.Chart(alt.Data(values=workload)).mark_bar(size=22, cornerRadiusEnd=4).encode(
            x=alt.X("planned:Q", title="Study hours", axis=alt.Axis(grid=True)),
            y=alt.Y("date:N", title=None, sort="ascending", axis=alt.Axis(labelLimit=130)),
            color=alt.condition(
                alt.datum.planned > alt.datum.limit,
                alt.value("#a95e50"),
                alt.value("#4b7866"),
            ),
            tooltip=[
                alt.Tooltip("date:N", title="Date"),
                alt.Tooltip("planned:Q", title="Planned hours", format=".2f"),
                alt.Tooltip("limit:Q", title="Daily limit", format=".2f"),
                alt.Tooltip("status:N", title="Status"),
            ],
        ).properties(height=min(420, max(170, len(workload) * 48)))
        limit_rule = alt.Chart(alt.Data(values=[{"limit": capacity}])).mark_rule(
            color="#a95e50", strokeDash=[5, 4], size=2
        ).encode(x="limit:Q")
        st.altair_chart((chart + limit_rule).configure_view(stroke=None).configure_axis(
            labelColor="#53645c", titleColor="#53645c", gridColor="#e4ebe6"
        ), use_container_width=True)
        st.subheader("Daily breakdown")
        st.dataframe(
            [{"Date": row["date"], "Planned hours": f'{row["planned"]:.2f} h',
              "Daily limit": f'{row["limit"]:g} h', "Status": row["status"]} for row in workload],
            use_container_width=True,
            hide_index=True,
        )
        if over:
            st.warning(f"{len(over)} day(s) exceed your {capacity:g}-hour daily limit.")
        else:
            st.success("Your planned hours fit within the daily limit.")
    else:
        st.info("No scheduled sessions yet. Generate a plan first.")

else:
    task_rows = tasks_data()
    schedule = planner.load_schedule_data()
    open_tasks = [row for row in task_rows if not row["completed"]]
    today = date.today().isoformat()
    week_end = date.today().toordinal() + 7
    due_this_week = sum(
        today <= row["due_date"] <= date.fromordinal(week_end).isoformat() for row in open_tasks
    )
    week_sessions = sum(
        today <= day["date"] <= date.fromordinal(week_end).isoformat()
        for day in schedule["days"]
    )
    a, b, c = st.columns(3)
    a.metric("Open tasks", len(open_tasks))
    b.metric("Due this week", due_this_week)
    c.metric("Study days planned", week_sessions)
    st.subheader("Upcoming deadlines")
    upcoming = [dict(row) for row in task_rows if row["due_date"] >= date.today().isoformat() and not row["completed"]]
    if upcoming:
        st.dataframe(
            [{"Task": row["title"], "Subject": row["subject"], "Due": row["due_date"],
              "Hours": f'{row["estimated_hours"]:g} h',
              "Priority": {1: "Low", 2: "Medium", 3: "High"}[row["priority"]]} for row in upcoming],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No open upcoming tasks. Add tasks or adjust their due dates in Tasks.")
