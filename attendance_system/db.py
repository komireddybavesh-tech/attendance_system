import os
import sqlite3
from werkzeug.security import generate_password_hash

DB_TYPE = os.environ.get("DB_TYPE", "sqlite").lower()
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "attendance.db")

# MySQL configuration
MYSQL_CONFIG = dict(
    host=os.environ.get("DB_HOST", "localhost"),
    user=os.environ.get("DB_USER", "root"),
    password=os.environ.get("DB_PASSWORD", ""),
    database=os.environ.get("DB_NAME", "attendance_db"),
)

try:
    import mysql.connector
    HAS_MYSQL = True
except ImportError:
    HAS_MYSQL = False

# Normalize IntegrityError
class UnifiedIntegrityError(Exception):
    pass

def get_connection():
    if DB_TYPE == "mysql" and HAS_MYSQL:
        try:
            return mysql.connector.connect(**MYSQL_CONFIG)
        except Exception as e:
            # If MySQL connection fails, inform and fallback to SQLite
            print(f"Warning: MySQL connection failed ({e}). Falling back to SQLite.")
            return get_sqlite_connection()
    return get_sqlite_connection()

def get_sqlite_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def is_using_sqlite(conn):
    return isinstance(conn, sqlite3.Connection)

def query(sql, args=(), one=False, write=False):
    conn = get_connection()
    using_sqlite = is_using_sqlite(conn)
    
    if using_sqlite:
        cur = conn.cursor()
        formatted_sql = sql.replace("%s", "?")
    else:
        cur = conn.cursor(dictionary=True)
        formatted_sql = sql

    try:
        cur.execute(formatted_sql, args)
        if write:
            conn.commit()
            return cur.lastrowid
        
        if one:
            row = cur.fetchone()
            return dict(row) if (row is not None and using_sqlite) else row
        else:
            rows = cur.fetchall()
            return [dict(r) for r in rows] if using_sqlite else rows
    except Exception as e:
        if "UNIQUE constraint failed" in str(e) or "Duplicate entry" in str(e) or isinstance(e, sqlite3.IntegrityError):
            raise UnifiedIntegrityError(str(e)) from e
        if HAS_MYSQL and isinstance(e, mysql.connector.IntegrityError):
            raise UnifiedIntegrityError(str(e)) from e
        raise e
    finally:
        cur.close()
        conn.close()

def save_attendance_batch(records):
    """
    records is a list of tuples: (student_id, att_date, status, marked_by)
    """
    if not records:
        return
    conn = get_connection()
    using_sqlite = is_using_sqlite(conn)
    cur = conn.cursor()
    try:
        if using_sqlite:
            sql = """INSERT INTO attendance (student_id, att_date, status, marked_by)
                     VALUES (?, ?, ?, ?)
                     ON CONFLICT(student_id, att_date) DO UPDATE SET
                         status = excluded.status,
                         marked_by = excluded.marked_by"""
        else:
            sql = """INSERT INTO attendance (student_id, att_date, status, marked_by)
                     VALUES (%s, %s, %s, %s)
                     ON DUPLICATE KEY UPDATE
                         status = VALUES(status),
                         marked_by = VALUES(marked_by)"""
        cur.executemany(sql, records)
        conn.commit()
    finally:
        cur.close()
        conn.close()

def init_db(force=False):
    """Initializes tables and seeds default users/sample data if not present."""
    conn = get_connection()
    using_sqlite = is_using_sqlite(conn)
    cur = conn.cursor()

    if using_sqlite:
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'faculty'
        );

        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            section TEXT DEFAULT '',
            UNIQUE (name, section)
        );

        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll_no TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            email TEXT DEFAULT '',
            class_id INTEGER NOT NULL,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            att_date TEXT NOT NULL,
            status TEXT NOT NULL,
            marked_by INTEGER NULL,
            UNIQUE (student_id, att_date),
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            FOREIGN KEY (marked_by) REFERENCES users(id) ON DELETE SET NULL
        );
        """)
        conn.commit()
    else:
        # MySQL schema creation
        schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
        if os.path.exists(schema_path):
            with open(schema_path) as f:
                for stmt in f.read().split(";"):
                    if stmt.strip():
                        cur.execute(stmt)
            cur.execute("USE attendance_db")
            conn.commit()

    # Seed default users
    for user, pw, role in [("admin", "admin123", "admin"), ("faculty", "faculty123", "faculty")]:
        try:
            if using_sqlite:
                cur.execute(
                    "INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?,?,?)",
                    (user, generate_password_hash(pw), role),
                )
            else:
                cur.execute(
                    "INSERT IGNORE INTO users (username, password_hash, role) VALUES (%s,%s,%s)",
                    (user, generate_password_hash(pw), role),
                )
        except Exception:
            pass

    # Check if classes table is empty, seed demo data for an out-of-the-box awesome experience
    cur.execute("SELECT COUNT(*) AS c FROM classes")
    row = cur.fetchone()
    count = row[0] if using_sqlite else row["c"]
    if count == 0:
        demo_classes = [
            ("Computer Science", "Year 3 - A"),
            ("Data Science", "Year 2 - B"),
            ("Information Technology", "Year 4 - A"),
        ]
        for name, sec in demo_classes:
            if using_sqlite:
                cur.execute("INSERT INTO classes (name, section) VALUES (?,?)", (name, sec))
            else:
                cur.execute("INSERT INTO classes (name, section) VALUES (%s,%s)", (name, sec))
        conn.commit()

        # Seed sample students
        cur.execute("SELECT id FROM classes LIMIT 1")
        first_class = cur.fetchone()
        class_id = first_class[0] if using_sqlite else first_class["id"]
        
        sample_students = [
            ("CS301", "Alex Johnson", "alex.j@example.edu", class_id),
            ("CS302", "Sophia Patel", "sophia.p@example.edu", class_id),
            ("CS303", "Marcus Aurelius Chen", "marcus.c@example.edu", class_id),
            ("CS304", "Emma Watson", "emma.w@example.edu", class_id),
            ("CS305", "Liam O'Connor", "liam.o@example.edu", class_id),
        ]
        for roll, name, email, cid in sample_students:
            if using_sqlite:
                cur.execute("INSERT INTO students (roll_no, name, email, class_id) VALUES (?,?,?,?)",
                            (roll, name, email, cid))
            else:
                cur.execute("INSERT INTO students (roll_no, name, email, class_id) VALUES (%s,%s,%s,%s)",
                            (roll, name, email, cid))
        conn.commit()

        # Seed a few days of sample attendance for demo visualization
        cur.execute("SELECT id FROM students WHERE class_id = ?", (class_id,)) if using_sqlite else cur.execute("SELECT id FROM students WHERE class_id = %s", (class_id,))
        stud_rows = cur.fetchall()
        from datetime import date, timedelta
        today = date.today()
        for i in range(1, 5):
            past_date = (today - timedelta(days=i)).isoformat()
            for s in stud_rows:
                sid = s[0] if using_sqlite else s["id"]
                # make CS305 have low attendance (<75%)
                status = "Absent" if (sid == stud_rows[-1][0] if using_sqlite else stud_rows[-1]["id"]) and i > 1 else "Present"
                if using_sqlite:
                    cur.execute("INSERT INTO attendance (student_id, att_date, status, marked_by) VALUES (?,?,?,?)",
                                (sid, past_date, status, 1))
                else:
                    cur.execute("INSERT INTO attendance (student_id, att_date, status, marked_by) VALUES (%s,%s,%s,%s)",
                                (sid, past_date, status, 1))
        conn.commit()

    conn.commit()
    cur.close()
    conn.close()
    print("Database initialized successfully.")
