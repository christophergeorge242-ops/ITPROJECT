-- Initial data model for the Smart Study Planner.
-- The Python program runs this script when it first starts.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    subject_id INTEGER NOT NULL,
    due_date TEXT NOT NULL, -- ISO date: YYYY-MM-DD
    estimated_hours REAL NOT NULL CHECK (estimated_hours > 0),
    priority INTEGER NOT NULL DEFAULT 2 CHECK (priority BETWEEN 1 AND 3),
    completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_subject_id ON tasks(subject_id);

CREATE TABLE IF NOT EXISTS planner_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    daily_study_limit REAL NOT NULL CHECK (daily_study_limit > 0)
);

CREATE TABLE IF NOT EXISTS schedule_entries (
    id INTEGER PRIMARY KEY,
    task_id INTEGER NOT NULL,
    study_date TEXT NOT NULL, -- ISO date: YYYY-MM-DD
    planned_hours REAL NOT NULL CHECK (planned_hours > 0),
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    UNIQUE (task_id, study_date)
);

CREATE INDEX IF NOT EXISTS idx_schedule_entries_study_date
    ON schedule_entries(study_date);
