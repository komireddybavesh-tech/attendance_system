"""Creates the database/tables and default users. Run once: python init_db.py"""
from db import init_db

if __name__ == "__main__":
    init_db()
    print("Database ready. Logins -> admin/admin123, faculty/faculty123 (change these!)")
