"""Creates the database/tables and default users. Run once: python init_db.py"""
import os
import mysql.connector
from werkzeug.security import generate_password_hash

conn = mysql.connector.connect(
    host=os.environ.get("DB_HOST", "localhost"),
    user=os.environ.get("DB_USER", "root"),
    password=os.environ.get("DB_PASSWORD", ""),
)
cur = conn.cursor()
with open("schema.sql") as f:
    for stmt in f.read().split(";"):
        if stmt.strip():
            cur.execute(stmt)
cur.execute("USE attendance_db")
for user, pw, role in [("admin", "admin123", "admin"), ("faculty", "faculty123", "faculty")]:
    cur.execute(
        "INSERT IGNORE INTO users (username, password_hash, role) VALUES (%s,%s,%s)",
        (user, generate_password_hash(pw), role),
    )
conn.commit()
print("Database ready. Logins -> admin/admin123, faculty/faculty123 (change these!)")
