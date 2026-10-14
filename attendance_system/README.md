# Student Attendance Management System

Flask + MySQL web app (HTML/CSS/JavaScript front end).

## Features
- Role-based login (admin / faculty)
- Admin: manage classes and students
- Faculty/Admin: mark and edit daily attendance (one record per student per day)
- Automatic attendance percentage, low-attendance flagging (below 75%)
- Dashboard summary and CSV export of reports

## Setup
1. Install Python 3.9+ and MySQL.
2. `pip install -r requirements.txt`
3. Set DB credentials (defaults: localhost / root / empty password):
   `export DB_USER=root DB_PASSWORD=yourpassword`
4. `python init_db.py` (creates tables and default users)
5. `python app.py` then open http://127.0.0.1:5000

Default logins: `admin / admin123`, `faculty / faculty123`. Change them before real use,
and set a strong `SECRET_KEY` environment variable.

## Structure
- `app.py` routes and logic, `schema.sql` tables, `init_db.py` setup
- `templates/` pages, `static/style.css` styling

## Database
users, classes, students (-> classes), attendance (-> students, users; unique per student per date)
