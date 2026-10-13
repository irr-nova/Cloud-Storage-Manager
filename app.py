from __future__ import annotations

import hashlib
import os
import shutil
from functools import wraps
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
import pyodbc

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "cloudvault.db"
ODBC_DSN = os.environ.get("CLOUDVAULT_DSN", "CLOUDVAULT_SQLITE")
app = Flask(__name__)
app.secret_key = os.environ.get("CLOUDVAULT_SECRET", "change-this-development-secret")


class ODBCRow:
    """Provide SQLite-like name and index access over a pyodbc row."""

    def __init__(self, columns, values):
        self._values = tuple(values)
        self._positions = {name.lower(): index for index, name in enumerate(columns)}

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._values[self._positions[key.lower()]]


class ODBCResult:
    def __init__(self, cursor):
        self._cursor = cursor
        self._columns = [column[0] for column in (cursor.description or [])]

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def fetchone(self):
        row = self._cursor.fetchone()
        return ODBCRow(self._columns, row) if row is not None else None

    def fetchall(self):
        return [ODBCRow(self._columns, row) for row in self._cursor.fetchall()]


class ODBCConnection:
    """Small connection adapter used by the Flask routes and seed scripts."""

    def __init__(self, dsn):
        self._connection = pyodbc.connect(f"DSN={dsn};", autocommit=True)
        cursor = self._connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()
        self._connection.autocommit = False

    def execute(self, sql, parameters=()):
        cursor = self._connection.cursor()
        if parameters:
            cursor.execute(sql, parameters)
        else:
            cursor.execute(sql)
        return ODBCResult(cursor)

    def executescript(self, script):
        # The project's SQL files contain one statement per semicolon and no
        # semicolons inside quoted values. Ignore their full-line SQL comments.
        for statement in script.split(";"):
            sql = "\n".join(line for line in statement.splitlines()
                              if not line.strip().startswith("--")).strip()
            if sql:
                self.execute(sql)

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self.rollback() if exc_type else self.commit()
        finally:
            self.close()


def connect_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        return ODBCConnection(ODBC_DSN)
    except pyodbc.Error as exc:
        raise RuntimeError(
            f"Cannot connect using ODBC DSN '{ODBC_DSN}'. Configure that DSN "
            f"to point to {DB_PATH} and install the SQLite ODBC driver."
        ) from exc


def init_db():
    with connect_db() as db:
        def save_backup(label):
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            backup_path = DB_PATH.with_name(f"cloudvault-{label}-{stamp}.db")
            shutil.copy2(DB_PATH, backup_path)

        # Upgrade the first prototype's SQLite database, whose USERS/FILES
        # columns do not match the PLANS/USERS/FOLDERS/FILES model. Keep both
        # a file backup and the legacy tables so existing lab data is not lost.
        user_columns = {row[1].lower() for row in db.execute("PRAGMA table_info(USERS)").fetchall()}
        if user_columns and "full_name" not in user_columns:
            save_backup("before-schema-update")
            db.execute("PRAGMA foreign_keys = OFF")
            db.execute("DROP INDEX IF EXISTS idx_files_user_uploaded")
            db.execute("ALTER TABLE USERS RENAME TO LEGACY_USERS")
            file_columns = {row[1].lower() for row in db.execute("PRAGMA table_info(FILES)").fetchall()}
            if file_columns:
                db.execute("ALTER TABLE FILES RENAME TO LEGACY_FILES")
            db.commit()
            db.execute("PRAGMA foreign_keys = ON")

        # A partially upgraded database may already have FOLDERS but still
        # point it at LEGACY_USERS (SQLite rewrites foreign keys on table
        # rename). Rebuild the app tables from the backed-up database in that
        # case; otherwise CREATE TABLE IF NOT EXISTS would keep the bad FK.
        folder_fks = db.execute("PRAGMA foreign_key_list(FOLDERS)").fetchall()
        if any(str(row[2]).upper() == "LEGACY_USERS" for row in folder_fks):
            save_backup("before-schema-repair")
            db.execute("PRAGMA foreign_keys = OFF")
            for table in ("FILES", "FOLDERS", "USERS", "PLANS"):
                db.execute(f"DROP TABLE IF EXISTS {table}")
            db.commit()
            db.execute("PRAGMA foreign_keys = ON")
        db.executescript((BASE_DIR / "schema.sql").read_text(encoding="utf-8"))
        db.executescript((BASE_DIR / "seed.sql").read_text(encoding="utf-8"))


def password_hash(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest().upper()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.before_request
def load_user():
    g.user = None
    if session.get("user_id") is not None:
        with connect_db() as db:
            g.user = db.execute("""SELECT u.user_id, u.full_name, u.email, u.plan_id,
                                         p.plan_name, p.storage_limit_mb, p.monthly_price
                                  FROM USERS u JOIN PLANS p ON p.plan_id = u.plan_id
                                  WHERE u.user_id = ?""", (session["user_id"],)).fetchone()
        if g.user is None:
            session.clear()


@app.template_filter("mb")
def format_mb(value):
    return f"{float(value):,.3f}".rstrip("0").rstrip(".")


@app.get("/")
@login_required
def dashboard():
    query = request.args.get("q", "").strip()
    selected_folder = request.args.get("folder", type=int)
    with connect_db() as db:
        folders = db.execute("""SELECT folder_id, folder_name, created_at FROM FOLDERS
                                WHERE user_id = ? ORDER BY folder_name""",
                             (g.user["user_id"],)).fetchall()
        used = db.execute("SELECT COALESCE(SUM(file_size_mb), 0) FROM FILES WHERE user_id = ?",
                          (g.user["user_id"],)).fetchone()[0]
        sql = """SELECT f.file_id, f.file_name, f.file_type, f.file_size_mb,
                        f.folder_id, f.uploaded_at, d.folder_name
                 FROM FILES f JOIN FOLDERS d ON d.folder_id = f.folder_id AND d.user_id = f.user_id
                 WHERE f.user_id = ?"""
        params = [g.user["user_id"]]
        if query:
            sql += " AND LOWER(f.file_name) LIKE ?"
            params.append(f"%{query.lower()}%")
        if selected_folder:
            sql += " AND f.folder_id = ?"
            params.append(selected_folder)
        sql += " ORDER BY f.uploaded_at DESC, f.file_id DESC"
        files = db.execute(sql, params).fetchall()
    quota = float(g.user["storage_limit_mb"])
    used = float(used)
    return render_template("dashboard.html", files=files, folders=folders, query=query,
                           selected_folder=selected_folder, used=used, quota=quota,
                           usage_percent=min(100, round(used * 100 / quota)) if quota else 0)


@app.get("/login")
@app.post("/login")
def login():
    if g.user:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        digest = password_hash(request.form.get("password", ""))
        with connect_db() as db:
            user = db.execute("SELECT user_id FROM USERS WHERE LOWER(email) = ? AND password_hash = ?",
                              (email, digest)).fetchone()
        if user:
            session.clear()
            session["user_id"] = user["user_id"]
            return redirect(url_for("dashboard"))
        flash("Email or password is incorrect.", "error")
    return render_template("auth.html", mode="login")


@app.get("/signup")
@app.post("/signup")
def signup():
    if g.user:
        return redirect(url_for("dashboard"))
    with connect_db() as db:
        plans = db.execute("SELECT plan_id, plan_name, storage_limit_mb, monthly_price FROM PLANS ORDER BY plan_id").fetchall()
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        try:
            plan_id = int(request.form.get("plan_id", ""))
        except ValueError:
            plan_id = 0
        valid_plan = any(plan["plan_id"] == plan_id for plan in plans)
        if not full_name or len(full_name) > 100 or not email or len(email) > 100 or len(password) < 8 or not valid_plan:
            flash("Enter your name and email, choose a plan, and use a password with at least 8 characters.", "error")
        else:
            try:
                with connect_db() as db:
                    user_id = db.execute("SELECT COALESCE(MAX(user_id), 0) + 1 FROM USERS").fetchone()[0]
                    folder_id = db.execute("SELECT COALESCE(MAX(folder_id), 0) + 1 FROM FOLDERS").fetchone()[0]
                    db.execute("INSERT INTO USERS (user_id, full_name, email, password_hash, plan_id) VALUES (?, ?, ?, ?, ?)",
                               (user_id, full_name, email, password_hash(password), plan_id))
                    db.execute("INSERT INTO FOLDERS (folder_id, folder_name, user_id) VALUES (?, 'My Files', ?)",
                               (folder_id, user_id))
                session.clear()
                session["user_id"] = user_id
                flash("Your account is ready. Add your first file record below.", "success")
                return redirect(url_for("dashboard"))
            except pyodbc.IntegrityError:
                flash("An account with that email already exists.", "error")
    return render_template("auth.html", mode="signup", plans=plans)


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.post("/folders")
@login_required
def create_folder():
    name = request.form.get("folder_name", "").strip()
    if not name or len(name) > 100:
        flash("Folder name is required and must be at most 100 characters.", "error")
        return redirect(url_for("dashboard"))
    try:
        with connect_db() as db:
            folder_id = db.execute("SELECT COALESCE(MAX(folder_id), 0) + 1 FROM FOLDERS").fetchone()[0]
            db.execute("INSERT INTO FOLDERS (folder_id, folder_name, user_id) VALUES (?, ?, ?)",
                       (folder_id, name, g.user["user_id"]))
        flash(f"Folder '{name}' created.", "success")
    except pyodbc.IntegrityError:
        flash("A folder with that name already exists in your account.", "error")
    return redirect(url_for("dashboard"))


@app.post("/folders/delete")
@login_required
def delete_folder():
    folder_id = request.form.get("folder_id", type=int)
    if not folder_id:
        flash("Choose a folder to delete.", "error")
        return redirect(url_for("dashboard"))
    with connect_db() as db:
        folder = db.execute("SELECT folder_name FROM FOLDERS WHERE folder_id = ? AND user_id = ?",
                            (folder_id, g.user["user_id"])).fetchone()
        if folder is None:
            abort(404)
        file_count = db.execute("SELECT COUNT(*) FROM FILES WHERE folder_id = ? AND user_id = ?",
                                (folder_id, g.user["user_id"])).fetchone()[0]
        if file_count:
            flash("This folder contains file records. Delete those records first, then remove the folder.", "error")
            return redirect(url_for("dashboard", folder=folder_id))
        db.execute("DELETE FROM FOLDERS WHERE folder_id = ? AND user_id = ?",
                   (folder_id, g.user["user_id"]))
    flash(f"Folder '{folder['folder_name']}' deleted.", "success")
    return redirect(url_for("dashboard"))


@app.post("/files")
@login_required
def add_file():
    name = request.form.get("file_name", "").strip()
    file_type = request.form.get("file_type", "").strip().upper() or None
    folder_id = request.form.get("folder_id", type=int)
    try:
        size = float(request.form.get("file_size_mb", ""))
        if not name or len(name) > 255 or size < 0 or not folder_id or (file_type and len(file_type) > 50):
            raise ValueError
    except ValueError:
        flash("Enter a valid file name, folder, and non-negative size in MB.", "error")
        return redirect(url_for("dashboard"))
    with connect_db() as db:
        owned_folder = db.execute("SELECT folder_id FROM FOLDERS WHERE folder_id = ? AND user_id = ?",
                                  (folder_id, g.user["user_id"])).fetchone()
        if not owned_folder:
            flash("Choose one of your own folders.", "error")
            return redirect(url_for("dashboard"))
        used = db.execute("SELECT COALESCE(SUM(file_size_mb), 0) FROM FILES WHERE user_id = ?",
                          (g.user["user_id"],)).fetchone()[0]
        if float(used) + size > float(g.user["storage_limit_mb"]):
            flash("This file would exceed your plan's storage limit.", "error")
            return redirect(url_for("dashboard", folder=folder_id))
        file_id = db.execute("SELECT COALESCE(MAX(file_id), 0) + 1 FROM FILES").fetchone()[0]
        db.execute("""INSERT INTO FILES (file_id, file_name, file_type, file_size_mb, folder_id, user_id)
                      VALUES (?, ?, ?, ?, ?, ?)""",
                   (file_id, name, file_type, size, folder_id, g.user["user_id"]))
    flash(f"'{name}' added to your cloud storage.", "success")
    return redirect(url_for("dashboard", folder=folder_id))


@app.post("/files/<int:file_id>/delete")
@login_required
def delete_file(file_id):
    with connect_db() as db:
        cur = db.execute("DELETE FROM FILES WHERE file_id = ? AND user_id = ?",
                         (file_id, g.user["user_id"]))
        if cur.rowcount == 0:
            abort(404)
    flash("File record deleted.", "success")
    return redirect(url_for("dashboard"))


@app.post("/account/delete")
@login_required
def delete_account():
    password = request.form.get("password", "")
    confirmation = request.form.get("confirmation", "").strip()
    if confirmation != "DELETE":
        flash("Type DELETE exactly to confirm account removal.", "error")
        return redirect(url_for("dashboard"))
    user_id = g.user["user_id"]
    with connect_db() as db:
        row = db.execute("SELECT password_hash FROM USERS WHERE user_id = ?", (user_id,)).fetchone()
        if row is None or password_hash(password) != row["password_hash"]:
            flash("Password is incorrect. Your account was not deleted.", "error")
            return redirect(url_for("dashboard"))
        db.execute("DELETE FROM FILES WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM FOLDERS WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM USERS WHERE user_id = ?", (user_id,))
    session.clear()
    flash("Your account and its folders and file records have been deleted.", "success")
    return redirect(url_for("login"))


init_db()

if __name__ == "__main__":
    app.run(debug=True)
