-- CLOUD STORAGE MANAGEMENT SYSTEM
-- Local SQLite implementation of the cloud storage table architecture.
-- SQLite equivalents: NUMBER -> INTEGER/REAL, VARCHAR2 -> TEXT, TIMESTAMP -> TEXT.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS PLANS (
    plan_id INTEGER PRIMARY KEY,
    plan_name TEXT NOT NULL UNIQUE,
    storage_limit_mb REAL NOT NULL CHECK (storage_limit_mb > 0),
    monthly_price REAL NOT NULL DEFAULT 0 CHECK (monthly_price >= 0)
);

CREATE TABLE IF NOT EXISTS USERS (
    user_id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    plan_id INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (plan_id) REFERENCES PLANS(plan_id)
);

CREATE TABLE IF NOT EXISTS FOLDERS (
    folder_id INTEGER PRIMARY KEY,
    folder_name TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES USERS(user_id),
    UNIQUE (folder_id, user_id),
    UNIQUE (user_id, folder_name)
);

CREATE TABLE IF NOT EXISTS FILES (
    file_id INTEGER PRIMARY KEY,
    file_name TEXT NOT NULL,
    file_type TEXT,
    file_size_mb REAL NOT NULL CHECK (file_size_mb >= 0),
    folder_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (folder_id, user_id) REFERENCES FOLDERS(folder_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_files_user_uploaded ON FILES(user_id, uploaded_at DESC);

-- DML examples used by the application:
-- SELECT SUM(file_size_mb) FROM FILES WHERE user_id = ?;
-- INSERT INTO FILES (file_id, file_name, file_type, file_size_mb, folder_id, user_id)
-- VALUES (?, ?, ?, ?, ?, ?);
-- UPDATE USERS SET plan_id = ? WHERE user_id = ?;
-- DELETE FROM FILES WHERE file_id = ? AND user_id = ?;
