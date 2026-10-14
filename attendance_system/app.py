import csv
import io
import os
from datetime import date
from functools import wraps

import mysql.connector
from flask import (Flask, Response, flash, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret")
THRESHOLD = 75  # minimum attendance percentage

DB_CONFIG = dict(
    host=os.environ.get("DB_HOST", "localhost"),
    user=os.environ.get("DB_USER", "root"),
    password=os.environ.get("DB_PASSWORD", ""),
    database=os.environ.get("DB_NAME", "attendance_db"),
)


def query(sql, args=(), one=False, write=False):
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(sql, args)
        if write:
            conn.commit()
            return cur.lastrowid
        return cur.fetchone() if one else cur.fetchall()
    finally:
        cur.close()
        conn.close()


def login_required(role=None):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("Admin access required.", "error")
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
    if request.method == "POST":
        u = query("SELECT * FROM users WHERE username=%s",
                  (request.form["username"].strip(),), one=True)
        if u and check_password_hash(u["password_hash"], request.form["password"]):
            session.update(user_id=u["id"], username=u["username"], role=u["role"])
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- Dashboard ----------
@app.route("/")
@login_required()
def dashboard():
    report = build_report()
    stats = {
        "students": query("SELECT COUNT(*) n FROM students", one=True)["n"],
        "classes": query("SELECT COUNT(*) n FROM classes", one=True)["n"],
        "today": query("SELECT COUNT(*) n FROM attendance WHERE att_date=%s",
                       (date.today(),), one=True)["n"],
        "low": sum(1 for r in report if r["low"]),
    }
    return render_template("dashboard.html", stats=stats,
                           low=[r for r in report if r["low"]][:10])


# ---------- Classes ----------
@app.route("/classes", methods=["GET", "POST"])
@login_required()
def classes():
    if request.method == "POST":
        if session["role"] != "admin":
            flash("Admin access required.", "error")
        else:
            try:
                query("INSERT INTO classes (name, section) VALUES (%s,%s)",
                      (request.form["name"].strip(), request.form["section"].strip()),
                      write=True)
                flash("Class added.", "ok")
            except mysql.connector.IntegrityError:
                flash("That class already exists.", "error")
        return redirect(url_for("classes"))
    return render_template("classes.html", classes=query(
        "SELECT c.*, (SELECT COUNT(*) FROM students s WHERE s.class_id=c.id) AS n "
        "FROM classes c ORDER BY c.name, c.section"))


@app.route("/classes/<int:cid>/delete", methods=["POST"])
@login_required("admin")
def delete_class(cid):
    query("DELETE FROM classes WHERE id=%s", (cid,), write=True)
    flash("Class deleted.", "ok")
    return redirect(url_for("classes"))


# ---------- Students ----------
@app.route("/students", methods=["GET", "POST"])
@login_required()
def students():
    if request.method == "POST":
        if session["role"] != "admin":
            flash("Admin access required.", "error")
        else:
            try:
                query("INSERT INTO students (roll_no, name, email, class_id) VALUES (%s,%s,%s,%s)",
                      (request.form["roll_no"].strip(), request.form["name"].strip(),
                       request.form["email"].strip(), request.form["class_id"]), write=True)
                flash("Student added.", "ok")
            except mysql.connector.IntegrityError:
                flash("Roll number already exists.", "error")
        return redirect(url_for("students"))
    return render_template(
        "students.html",
        classes=query("SELECT * FROM classes ORDER BY name, section"),
        students=query("SELECT s.*, c.name AS class_name, c.section FROM students s "
                       "JOIN classes c ON c.id=s.class_id ORDER BY s.roll_no"))


@app.route("/students/<int:sid>/delete", methods=["POST"])
@login_required("admin")
def delete_student(sid):
    query("DELETE FROM students WHERE id=%s", (sid,), write=True)
    flash("Student deleted.", "ok")
    return redirect(url_for("students"))


# ---------- Attendance ----------
@app.route("/attendance", methods=["GET", "POST"])
@login_required()
def attendance():
    classes_ = query("SELECT * FROM classes ORDER BY name, section")
    class_id = request.values.get("class_id", type=int)
    att_date = request.values.get("att_date") or date.today().isoformat()

    if request.method == "POST" and class_id:
        studs = query("SELECT id FROM students WHERE class_id=%s", (class_id,))
        present = set(request.form.getlist("present"))
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.executemany(
            "INSERT INTO attendance (student_id, att_date, status, marked_by) "
            "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
            "status=VALUES(status), marked_by=VALUES(marked_by)",
            [(s["id"], att_date, "Present" if str(s["id"]) in present else "Absent",
              session["user_id"]) for s in studs])
        conn.commit()
        cur.close()
        conn.close()
        flash(f"Attendance saved for {att_date}.", "ok")
        return redirect(url_for("attendance", class_id=class_id, att_date=att_date))

    rows = []
    if class_id:
        rows = query("SELECT s.id, s.roll_no, s.name, a.status FROM students s "
                     "LEFT JOIN attendance a ON a.student_id=s.id AND a.att_date=%s "
                     "WHERE s.class_id=%s ORDER BY s.roll_no", (att_date, class_id))
    return render_template("attendance.html", classes=classes_, class_id=class_id,
                           att_date=att_date, rows=rows)


# ---------- Reports ----------
@app.route("/reports")
@login_required()
def reports():
    class_id = request.args.get("class_id", type=int)
    return render_template("reports.html", rows=build_report(class_id),
                           classes=query("SELECT * FROM classes ORDER BY name, section"),
                           class_id=class_id, threshold=THRESHOLD)


@app.route("/reports/export")
@login_required()
def export_report():
    rows = build_report(request.args.get("class_id", type=int))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Roll No", "Name", "Class", "Total Days", "Present", "Percentage", "Status"])
    for r in rows:
        w.writerow([r["roll_no"], r["name"], f'{r["class_name"]} {r["section"]}'.strip(),
                    r["total"], r["present"], r["pct"], "LOW" if r["low"] else "OK"])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=attendance_report.csv"})


if __name__ == "__main__":
    app.run(debug=True)
