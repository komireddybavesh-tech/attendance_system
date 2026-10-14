# Attendify &mdash; Student Attendance Management System

Modern Flask web application with responsive UI, role-based access, attendance tracking, and reporting.

## Features
- **Role-based Authentication**: Admin and Faculty accounts.
- **Admin Management**: Create, view, and delete classes and students.
- **Faculty & Admin Attendance**: Daily roll call marking with quick "Mark All Present/Absent" toggles.
- **Automatic Analytics**: Attendance percentage calculation and real-time low attendance flagging (< 75%).
- **Interactive Reports & CSV Export**: Cumulative records with spreadsheet download.
- **Dual Database Architecture**: Runs zero-configuration on **SQLite** by default, with seamless **MySQL** support when configured.

## Quick Start (Zero-Configuration SQLite)
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the server (auto-initializes tables and demo data):
   ```bash
   python app.py
   ```
3. Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

### Default Credentials
- **Admin**: `admin` / `admin123` (Class & student management, attendance, reports)
- **Faculty**: `faculty` / `faculty123` (Attendance marking and reports)

*(Click the demo quick-login buttons on the login page for instant sign-in)*

## Using MySQL (Optional)
If you wish to connect to an external MySQL server:
1. Set the environment variables:
   ```bash
   export DB_TYPE=mysql
   export DB_HOST=localhost
   export DB_USER=root
   export DB_PASSWORD=yourpassword
   export DB_NAME=attendance_db
   ```
2. Initialize MySQL database:
   ```bash
   python init_db.py
   ```
3. Run the app:
   ```bash
   python app.py
   ```
