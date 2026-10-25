const state = { tasks: [], schedule: null };
let toastTimer;

const byId = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[char]));
const formatHours = (value) => Number(value || 0).toLocaleString(undefined, {
  maximumFractionDigits: 2
});
const formatDate = (value, options = { month: "short", day: "numeric", year: "numeric" }) => {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, options).format(new Date(`${value}T00:00:00`));
};
const localDateKey = (date = new Date()) => {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
};

async function api(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) }
  });
  const responseText = await response.text();
  let data;
  try {
    data = responseText ? JSON.parse(responseText) : {};
  } catch {
    if (url === "/api/schedule/session" && response.status === 404) {
      throw new Error("This page is connected to an older planner server. Stop it with Ctrl+C, start ITPROJECT\\planner.py from the project folder, then hard-refresh this page.");
    }
    throw new Error(`The planner server returned an unexpected response (HTTP ${response.status}).`);
  }
  if (!response.ok) throw new Error(data.error || "Something went wrong.");
  return data;
}

function notify(message, isError = false) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.classList.toggle("is-error", isError);
  toast.classList.add("is-visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 3000);
}

function showView(name) {
  document.querySelectorAll(".page-view").forEach((view) => {
    view.classList.toggle("is-hidden", view.id !== `view-${name}`);
  });
  document.querySelectorAll(".nav-link").forEach((link) => {
    const active = link.dataset.view === name;
    link.classList.toggle("is-active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  history.replaceState(null, "", `#${name}`);
  loadView(name).catch((error) => notify(error.message, true));
}

async function loadView(name) {
  if (name === "overview") await loadOverview();
  if (name === "tasks") await loadTasks();
  if (name === "schedule") await loadSchedule();
  if (name === "workload") await loadWorkload();
}

function dueText(dueDate) {
  const days = Math.round((new Date(`${dueDate}T00:00:00`) - new Date(`${localDateKey()}T00:00:00`)) / 86400000);
  if (days < 0) return `Overdue by ${Math.abs(days)} day${Math.abs(days) === 1 ? "" : "s"}`;
  if (days === 0) return "Due today";
  if (days === 1) return "Due tomorrow";
  return `Due ${formatDate(dueDate, { month: "short", day: "numeric" })}`;
}

async function loadTasks() {
  state.tasks = await api("/api/tasks");
  renderTasks();
}

function renderTasks() {
  const tasks = state.tasks;
  const activeCount = tasks.filter((task) => !task.completed).length;
  byId("task-count-label").textContent = `${activeCount} ${activeCount === 1 ? "task" : "tasks"}`;
  if (!tasks.length) {
    byId("task-list").innerHTML = '<div class="empty-state">No tasks yet. Add one to start your study plan.</div>';
    return;
  }

  byId("task-list").innerHTML = tasks.map((task) => `
    <div class="task-row">
      <div class="task-name"><strong>${escapeHtml(task.title)}</strong><span>${escapeHtml(task.subject)}</span></div>
      <div class="task-due">${formatDate(task.due_date)}<br><span class="task-cell-label">${dueText(task.due_date)}</span></div>
      <div class="task-hours">${formatHours(task.estimated_hours)}h</div>
      <span class="priority priority-${task.priority}">${["", "Low", "Medium", "High"][task.priority]}</span>
      <div class="task-actions">
        <button class="task-action" data-edit-task="${task.id}">Edit</button>
        <button class="task-action" data-delete-task="${task.id}">Remove</button>
      </div>
    </div>`).join("");

  document.querySelectorAll("[data-edit-task]").forEach((button) => {
    button.addEventListener("click", () => {
      const task = state.tasks.find((item) => item.id === Number(button.dataset.editTask));
      if (task) openTaskForm(task);
    });
  });
  document.querySelectorAll("[data-delete-task]").forEach((button) => {
    button.addEventListener("click", () => removeTask(Number(button.dataset.deleteTask)));
  });
}

function openTaskForm(task = null) {
  const form = byId("task-form");
  form.reset();
  form.elements.task_id.value = task?.id || "";
  form.elements.title.value = task?.title || "";
  form.elements.subject.value = task?.subject || "";
  form.elements.due_date.value = task?.due_date || "";
  form.elements.estimated_hours.value = task?.estimated_hours || "";
  form.elements.priority.value = task?.priority || "2";
  byId("task-form-heading").textContent = task ? "Edit task" : "New task";
  byId("save-task-button").textContent = task ? "Save changes" : "Save task";
  form.classList.remove("is-hidden");
  form.scrollIntoView({ behavior: "smooth", block: "center" });
  form.elements.title.focus();
}

function closeTaskForm() {
  byId("task-form").classList.add("is-hidden");
  byId("task-form").reset();
}

async function removeTask(taskId) {
  const task = state.tasks.find((item) => item.id === taskId);
  if (!task || !window.confirm(`Remove “${task.title}”?`)) return;
  try {
    await api(`/api/tasks/${taskId}`, { method: "DELETE" });
    notify("Task removed.");
    await loadAllViews();
  } catch (error) {
    notify(error.message, true);
  }
}

async function loadSchedule() {
  state.schedule = await api("/api/schedule");
  if (state.schedule.daily_limit) byId("daily-limit").value = state.schedule.daily_limit;
  renderSchedule(state.schedule);
}

function renderSchedule(data) {
  const notice = byId("schedule-notice");
  const list = byId("schedule-list");
  notice.classList.add("is-hidden");
  notice.innerHTML = "";

  if (data.daily_limit == null) {
    list.innerHTML = '<div class="empty-state">Add tasks, then generate a study plan.</div>';
    return;
  }

  if (data.unscheduled?.length) {
    notice.innerHTML = `<strong>Time still needed</strong><br>${data.unscheduled.map((task) =>
      `${escapeHtml(task.title)}: ${formatHours(task.hours)}h could not fit before ${formatDate(task.due_date)}`
    ).join("<br>")}`;
    notice.classList.remove("is-hidden");
  }

  if (!data.days.length) {
    list.innerHTML = '<div class="empty-state">No study sessions fit before the current deadlines.</div>';
    return;
  }

  list.innerHTML = data.days.map((day) => `
    <section class="schedule-day">
      <div class="schedule-date">${formatDate(day.date, { weekday: "long", month: "short", day: "numeric" })}<span>${formatHours(day.total_hours)} hours planned</span></div>
      <div class="session-list">${day.sessions.map((session) => `
        <div class="session-row">
          <span class="session-hours">${formatHours(session.hours)}h</span>
          <span class="session-title">${escapeHtml(session.title)}</span>
          <span class="session-subject">${escapeHtml(session.subject)}</span>
          ${session.completed
            ? '<span class="session-state">Completed</span>'
            : `<div class="session-actions">
                <button class="task-action" data-session-action="completed" data-task-id="${session.task_id}" data-date="${day.date}">Done</button>
                <button class="task-action" data-session-action="missed" data-task-id="${session.task_id}" data-date="${day.date}">Missed</button>
              </div>`}
        </div>`).join("")}</div>
    </section>`).join("");

  document.querySelectorAll("[data-session-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await api("/api/schedule/session", {
          method: "POST",
          body: JSON.stringify({
            task_id: Number(button.dataset.taskId),
            date: button.dataset.date,
            action: button.dataset.sessionAction
          })
        });
        notify(button.dataset.sessionAction === "completed"
          ? "Session completed; remaining hours replanned."
          : "Missed session moved into the remaining plan.");
        await loadAllViews();
      } catch (error) {
        notify(error.message, true);
      }
    });
  });
}

async function loadWorkload() {
  const data = await api("/api/workload");
  const summary = byId("workload-summary");
  const list = byId("workload-list");
  if (data.daily_limit == null) {
    summary.textContent = "Generate a study plan to compare daily hours with your capacity.";
    list.innerHTML = "";
    return;
  }
  if (!data.days.length) {
    summary.textContent = "No scheduled study hours to analyze.";
    list.innerHTML = "";
    return;
  }

  const overloaded = data.days.filter((day) => day.over_capacity).length;
  summary.textContent = overloaded
    ? `${overloaded} ${overloaded === 1 ? "day is" : "days are"} over your ${formatHours(data.daily_limit)}h daily capacity.`
    : `All scheduled days are within your ${formatHours(data.daily_limit)}h daily capacity.`;
  list.innerHTML = data.days.map((day) => {
    const percentage = Math.min(100, (day.total_hours / data.daily_limit) * 100);
    return `
      <div class="workload-row">
        <div class="workload-date">${formatDate(day.date, { weekday: "short", month: "short", day: "numeric" })}</div>
        <div class="bar-track" aria-label="${formatHours(day.total_hours)} of ${formatHours(data.daily_limit)} hours">
          <div class="bar-fill ${day.over_capacity ? "is-over" : ""}" style="width:${percentage}%"></div>
        </div>
        <div class="workload-total">${formatHours(day.total_hours)}h / ${formatHours(data.daily_limit)}h</div>
        <div class="workload-status ${day.over_capacity ? "is-over" : ""}">${day.over_capacity ? `Over by ${formatHours(day.excess_hours)}h` : "Within capacity"}</div>
      </div>`;
  }).join("");
}

async function loadOverview() {
  const [tasks, schedule] = await Promise.all([api("/api/tasks"), api("/api/schedule")]);
  state.tasks = tasks;
  state.schedule = schedule;
  const openTasks = tasks.filter((task) => !task.completed);
  const today = localDateKey();
  const weekEnd = localDateKey(new Date(Date.now() + 7 * 86400000));
  const dueSoon = openTasks.filter((task) => task.due_date >= today && task.due_date <= weekEnd);
  byId("stat-task-count").textContent = openTasks.length;
  byId("stat-due-soon").textContent = dueSoon.length;
  byId("stat-hours").textContent = formatHours(schedule.days
    .filter((day) => day.date >= today && day.date <= weekEnd)
    .reduce((sum, day) => sum + day.total_hours, 0));

  const upcoming = openTasks.slice(0, 4);
  byId("upcoming-list").innerHTML = upcoming.length ? upcoming.map((task) => `
    <div class="simple-row">
      <div><strong>${escapeHtml(task.title)}</strong><span>${escapeHtml(task.subject)}</span></div>
      <span class="due-label">${dueText(task.due_date)}</span>
    </div>`).join("") : '<div class="empty-state">No upcoming tasks. Add a deadline to get started.</div>';

  const firstSession = schedule.days[0]?.sessions[0];
  if (firstSession) {
    byId("next-session").innerHTML = `
      <p class="next-session-title">${escapeHtml(firstSession.title)}</p>
      <p class="next-session-meta">${formatDate(schedule.days[0].date)} · ${formatHours(firstSession.hours)} hours · ${escapeHtml(firstSession.subject)}</p>`;
  } else {
    byId("next-session").innerHTML = '<p class="empty-copy">No study sessions yet.</p>';
  }
}

async function loadAllViews() {
  await Promise.all([loadTasks(), loadOverview(), loadSchedule(), loadWorkload()]);
}

document.querySelectorAll(".nav-link").forEach((button) => {
  button.addEventListener("click", () => showView(button.dataset.view));
});
document.querySelectorAll("[data-go]").forEach((button) => {
  button.addEventListener("click", () => {
    showView(button.dataset.go);
    if (button.dataset.openForm) setTimeout(() => openTaskForm(), 50);
  });
});
byId("show-task-form").addEventListener("click", () => openTaskForm());
byId("close-task-form").addEventListener("click", closeTaskForm);
byId("cancel-task-form").addEventListener("click", closeTaskForm);

byId("task-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = Object.fromEntries(new FormData(form).entries());
  const taskId = values.task_id;
  delete values.task_id;
  values.estimated_hours = Number(values.estimated_hours);
  values.priority = Number(values.priority);
  try {
    await api(taskId ? `/api/tasks/${taskId}` : "/api/tasks", {
      method: taskId ? "PUT" : "POST",
      body: JSON.stringify(values)
    });
    closeTaskForm();
    notify(taskId ? "Task updated." : "Task saved.");
    await loadAllViews();
  } catch (error) {
    notify(error.message, true);
  }
});

byId("schedule-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type=submit]");
  button.disabled = true;
  button.textContent = "Planning…";
  try {
    await api("/api/schedule", {
      method: "POST",
      body: JSON.stringify({ daily_limit: Number(byId("daily-limit").value) })
    });
    notify("Study plan generated.");
    await loadAllViews();
  } catch (error) {
    notify(error.message, true);
  } finally {
    button.disabled = false;
    button.innerHTML = 'Generate plan <span aria-hidden="true">↗</span>';
  }
});

const initialView = ["overview", "tasks", "schedule", "workload"].includes(location.hash.slice(1))
  ? location.hash.slice(1) : "overview";
showView(initialView);
