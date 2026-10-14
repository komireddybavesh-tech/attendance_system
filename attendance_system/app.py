import csv
import io
import os
from datetime import date
from functools import wraps

from flask import (Flask, Response, flash, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash

from db import query, save_attendance_batch, UnifiedIntegrityError, init_db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "student-attendance-secret-key-2026")
THRESHOLD = 75  # minimum attendance percentage

# Ensure database and seed tables are created on startup
with app.app_context():
    init_db()


def login_required(role=None):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("Admin access is required for that action.", "error")
                return redirect(url_for("dashboard"))
            return fn(*a, **kw)
        return wrapper
    return deco


def build_report(class_id=None):
    sql = """SELECT s.id, s.roll_no, s.name, c.name AS class_name, c.section,
                    COUNT(a.id) AS total,
                    COALESCE(SUM(a.status='Present'),0) AS present
             FROM students s
             JOIN classes c ON c.id = s.class_id
             LEFT JOIN attendance a ON a.student_id = s.id"""
    args = ()
    if class_id:
        sql += " WHERE s.class_id=%s"
        args = (class_id,)
    sql += " GROUP BY s.id, s.roll_no, s.name, c.name, c.section ORDER BY s.roll_no"
    rows = query(sql, args)
    for r in rows:
        r["total"], r["present"] = int(r["total"]), int(r["present"])
        r["pct"] = round(100 * r["present"] / r["total"], 1) if r["total"] else 0.0
        r["low"] = r["total"] > 0 and r["pct"] < THRESHOLD
    return rows


# ---------- Auth ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        u = query("SELECT * FROM users WHERE username=%s", (username,), one=True)
        if u and check_password_hash(u["password_hash"], password):
            session.update(user_id=u["id"], username=u["username"], role=u["role"])
            flash(f"Welcome back, {u['username']}!", "ok")
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "ok")
    return redirect(url_for("login"))


# ---------- Dashboard ----------
@app.route("/")
@login_required()
def dashboard():
    report = build_report()
    student_count_row = query("SELECT COUNT(*) AS n FROM students", one=True)
    class_count_row = query("SELECT COUNT(*) AS n FROM classes", one=True)
    today_count_row = query("SELECT COUNT(DISTINCT student_id) AS n FROM attendance WHERE att_date=%s",
                            (date.today().isoformat(),), one=True)
    stats = {
        "students": student_count_row["n"] if student_count_row else 0,
        "classes": class_count_row["n"] if class_count_row else 0,
        "today": today_count_row["n"] if today_count_row else 0,
        "low": sum(1 for r in report if r["low"]),
    }
    return render_template("dashboard.html", stats=stats,
                           low=[r for r in report if r["low"]][:10],
                           threshold=THRESHOLD)


# ---------- Classes ----------
@app.route("/classes", methods=["GET", "POST"])
@login_required()
def classes():
    if request.method == "POST":
        if session.get("role") != "admin":
            flash("Admin access is required to add classes.", "error")
        else:
            name = request.form.get("name", "").strip()
            section = request.form.get("section", "").strip()
            if not name:
                flash("Class name is required.", "error")
            else:
                try:
                    query("INSERT INTO classes (name, section) VALUES (%s,%s)",
                          (name, section), write=True)
                    flash(f"Class '{name} {section}' created successfully.", "ok")
                except UnifiedIntegrityError:
                    flash(f"Class '{name} {section}' already exists.", "error")
        return redirect(url_for("classes"))
    
    classes_list = query(
        "SELECT c.*, (SELECT COUNT(*) FROM students s WHERE s.class_id=c.id) AS n "
        "FROM classes c ORDER BY c.name, c.section"
    )
    return render_template("classes.html", classes=classes_list)


@app.route("/classes/<int:cid>/delete", methods=["POST"])
@login_required("admin")
def delete_class(cid):
    query("DELETE FROM classes WHERE id=%s", (cid,), write=True)
    flash("Class and associated students deleted.", "ok")
    return redirect(url_for("classes"))


# ---------- Students ----------
@app.route("/students", methods=["GET", "POST"])
@login_required()
def students():
    if request.method == "POST":
        if session.get("role") != "admin":
            flash("Admin access is required to add students.", "error")
        else:
            roll_no = request.form.get("roll_no", "").strip()
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip()
            class_id = request.form.get("class_id")
            if not roll_no or not name or not class_id:
                flash("Roll number, name, and class are required.", "error")
            else:
                try:
                    query("INSERT INTO students (roll_no, name, email, class_id) VALUES (%s,%s,%s,%s)",
                          (roll_no, name, email, class_id), write=True)
                    flash(f"Student '{name}' ({roll_no}) registered successfully.", "ok")
                except UnifiedIntegrityError:
                    flash(f"Roll number '{roll_no}' already exists.", "error")
        return redirect(url_for("students"))
    
    classes_list = query("SELECT * FROM classes ORDER BY name, section")
    students_list = query(
        "SELECT s.*, c.name AS class_name, c.section FROM students s "
        "JOIN classes c ON c.id=s.class_id ORDER BY s.roll_no"
    )
    return render_template("students.html", classes=classes_list, students=students_list)


@app.route("/students/<int:sid>/delete", methods=["POST"])
@login_required("admin")
def delete_student(sid):
    query("DELETE FROM students WHERE id=%s", (sid,), write=True)
    flash("Student removed successfully.", "ok")
    return redirect(url_for("students"))


# ---------- Attendance ----------
@app.route("/attendance", methods=["GET", "POST"])
@login_required()
def attendance():
    classes_list = query("SELECT * FROM classes ORDER BY name, section")
    class_id = request.values.get("class_id", type=int)
    att_date = request.values.get("att_date") or date.today().isoformat()

    if request.method == "POST" and class_id:
        studs = query("SELECT id FROM students WHERE class_id=%s", (class_id,))
        present_ids = set(request.form.getlist("present"))
        records = [
            (s["id"], att_date, "Present" if str(s["id"]) in present_ids else "Absent", session["user_id"])
            for s in studs
        ]
        save_attendance_batch(records)
        flash(f"Attendance recorded for {len(records)} students on {att_date}.", "ok")
        return redirect(url_for("attendance", class_id=class_id, att_date=att_date))

    rows = []
    selected_class = None
    if class_id:
        selected_class = query("SELECT * FROM classes WHERE id=%s", (class_id,), one=True)
        rows = query(
            "SELECT s.id, s.roll_no, s.name, a.status FROM students s "
            "LEFT JOIN attendance a ON a.student_id=s.id AND a.att_date=%s "
            "WHERE s.class_id=%s ORDER BY s.roll_no", (att_date, class_id)
        )
    return render_template("attendance.html", classes=classes_list, class_id=class_id,
                           selected_class=selected_class, att_date=att_date, rows=rows)


# ---------- Reports ----------
@app.route("/reports")
@login_required()
def reports():
    class_id = request.args.get("class_id", type=int)
    classes_list = query("SELECT * FROM classes ORDER BY name, section")
    rows = build_report(class_id)
    return render_template("reports.html", rows=rows,
                           classes=classes_list,
                           class_id=class_id, threshold=THRESHOLD)


@app.route("/reports/export")
@login_required()
def export_report():
    class_id = request.args.get("class_id", type=int)
    rows = build_report(class_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Roll No", "Name", "Class", "Total Days", "Present", "Attendance %", "Status"])
    for r in rows:
        w.writerow([r["roll_no"], r["name"], f'{r["class_name"]} {r["section"]}'.strip(),
                    r["total"], r["present"], f"{r['pct']}%", "BELOW THRESHOLD" if r["low"] else "SATISFACTORY"])
    filename = f"attendance_report_{class_id or 'all'}_{date.today().isoformat()}.csv"
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
