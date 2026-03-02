from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import mysql.connector
from mysql.connector import Error
from datetime import datetime, timedelta
import urllib.request, urllib.parse, json, hashlib

app = Flask(__name__)
app.secret_key = "lms_secret_2025_bala"

FINE_PER_DAY = 2.00   # ₹2 per day late fee
LOAN_DAYS    = 14     # 14-day loan period

@app.context_processor
def inject_now():
    return {"now": datetime.now}

# ═══════════════════════════════════════════════════════════════════
# DB CONFIG  — change only these four values
# ═══════════════════════════════════════════════════════════════════
DB_HOST = "localhost"
DB_USER = "bala"
DB_PASS = "Bala@2005"
DB_NAME = "library_db"

# ═══════════════════════════════════════════════════════════════════
# DB HELPERS
# ═══════════════════════════════════════════════════════════════════
def get_db():
    return mysql.connector.connect(
        host=DB_HOST, user=DB_USER,
        password=DB_PASS, database=DB_NAME
    )

def qone(sql, params=()):
    conn = get_db()
    cur  = conn.cursor(dictionary=True)
    cur.execute(sql, params)
    row  = cur.fetchone()
    cur.close(); conn.close()
    return row

def qall(sql, params=()):
    conn = get_db()
    cur  = conn.cursor(dictionary=True)
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def execute(sql, params=()):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    lid  = cur.lastrowid
    cur.close(); conn.close()
    return lid

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

# ═══════════════════════════════════════════════════════════════════
# BOOTSTRAP DATABASE
# Uses CREATE TABLE IF NOT EXISTS — data is NEVER wiped on restart.
# Registered students and all data persist across restarts.
# ═══════════════════════════════════════════════════════════════════
def init_db():
    # Connect without database to ensure the DB itself exists
    conn = mysql.connector.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASS
    )
    conn.autocommit = True
    cur = conn.cursor()

    # Create database if it doesn't exist (safe — never drops anything)
    cur.execute(
        f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
        f"DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    cur.execute(f"USE `{DB_NAME}`")
    cur.execute("SET FOREIGN_KEY_CHECKS = 0")

    # Create tables only if they don't already exist
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id       INT          AUTO_INCREMENT PRIMARY KEY,
            name     VARCHAR(100) NOT NULL,
            email    VARCHAR(100) NOT NULL UNIQUE,
            password VARCHAR(64)  NOT NULL
        ) ENGINE=InnoDB
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id         INT          AUTO_INCREMENT PRIMARY KEY,
            name       VARCHAR(100) NOT NULL,
            email      VARCHAR(100) NOT NULL UNIQUE,
            password   VARCHAR(64)  NOT NULL,
            roll_no    VARCHAR(30)  NOT NULL UNIQUE,
            department VARCHAR(80),
            phone      VARCHAR(15),
            joined_on  DATE         DEFAULT (CURDATE())
        ) ENGINE=InnoDB
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id           INT          AUTO_INCREMENT PRIMARY KEY,
            title        VARCHAR(200) NOT NULL,
            author       VARCHAR(150),
            isbn         VARCHAR(30)  UNIQUE,
            category     VARCHAR(80),
            publisher    VARCHAR(150),
            year         INT,
            total_copies INT          DEFAULT 1,
            available    INT          DEFAULT 1,
            cover_url    VARCHAR(600) DEFAULT \'\',
            description  TEXT,
            added_on     DATE         DEFAULT (CURDATE())
        ) ENGINE=InnoDB
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS issues (
            id          INT          AUTO_INCREMENT PRIMARY KEY,
            book_id     INT          NOT NULL,
            student_id  INT          NOT NULL,
            issue_date  DATE         NOT NULL,
            due_date    DATE         NOT NULL,
            return_date DATE,
            fine        DECIMAL(8,2) DEFAULT 0.00,
            status      ENUM(\'issued\',\'returned\',\'overdue\') DEFAULT \'issued\',
            FOREIGN KEY (book_id)    REFERENCES books(id)    ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
        ) ENGINE=InnoDB
    """)

    cur.execute("SET FOREIGN_KEY_CHECKS = 1")

    # Seed default admin ONLY if admins table is empty
    cur.execute("SELECT COUNT(*) FROM admins")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO admins (name, email, password) VALUES (%s, %s, %s)",
            ("Admin", "admin@library.com", hash_pw("admin123"))
        )
        print("  Default admin created: admin@library.com / admin123")

    cur.close()
    conn.close()
    print("Database ready — existing data preserved.")
    print("Admin login: admin@library.com  |  password: admin123")

init_db()

# ═══════════════════════════════════════════════════════════════════
# BOOK COVER  (Google Books API)
# ═══════════════════════════════════════════════════════════════════
def fetch_cover(title, author=""):
    try:
        q   = urllib.parse.quote(f"{title} {author}".strip())
        url = f"https://www.googleapis.com/books/v1/volumes?q={q}&maxResults=1"
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
        items = data.get("items", [])
        if items:
            imgs  = items[0]["volumeInfo"].get("imageLinks", {})
            cover = (imgs.get("large") or imgs.get("medium")
                     or imgs.get("thumbnail") or "")
            if cover:
                return (cover.replace("http://", "https://")
                             .replace("zoom=1", "zoom=3")
                             .replace("&edge=curl", ""))
    except Exception:
        pass
    initials = urllib.parse.quote(title[:2].upper())
    return f"https://placehold.co/240x340/1a1e28/f59e0b?text={initials}"

# ═══════════════════════════════════════════════════════════════════
# FINE CALCULATION
# ═══════════════════════════════════════════════════════════════════
def calc_fine(due_date, return_date=None):
    today = return_date or datetime.today().date()
    if isinstance(due_date, str):
        due_date = datetime.strptime(due_date, "%Y-%m-%d").date()
    if isinstance(today, str):
        today = datetime.strptime(today, "%Y-%m-%d").date()
    return round(max((today - due_date).days, 0) * FINE_PER_DAY, 2)

# ═══════════════════════════════════════════════════════════════════
# AUTH DECORATORS
# ═══════════════════════════════════════════════════════════════════
def student_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*a, **kw):
        if session.get("role") != "student":
            flash("Please login as student.", "error")
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*a, **kw):
        if session.get("role") != "admin":
            flash("Please login as admin.", "error")
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper

# ═══════════════════════════════════════════════════════════════════
# PUBLIC ROUTES
# ═══════════════════════════════════════════════════════════════════
@app.route("/")
def index():
    if session.get("role") == "admin":   return redirect(url_for("admin_dashboard"))
    if session.get("role") == "student": return redirect(url_for("student_dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip()
        pw    = hash_pw(request.form["password"])
        role  = request.form["role"]

        if role == "admin":
            user = qone("SELECT * FROM admins WHERE email=%s AND password=%s", (email, pw))
            if user:
                session.update({"uid": user["id"], "name": user["name"], "role": "admin"})
                flash(f"Welcome back, {user['name']}!", "success")
                return redirect(url_for("admin_dashboard"))
        else:
            user = qone("SELECT * FROM students WHERE email=%s AND password=%s", (email, pw))
            if user:
                session.update({"uid": user["id"], "name": user["name"], "role": "student"})
                flash(f"Welcome, {user['name']}!", "success")
                return redirect(url_for("student_dashboard"))

        flash("Invalid credentials. Please try again.", "error")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name  = request.form["name"].strip()
        email = request.form["email"].strip()
        pw    = hash_pw(request.form["password"])
        roll  = request.form["roll_no"].strip()
        dept  = request.form["department"].strip()
        phone = request.form["phone"].strip()
        try:
            execute(
                "INSERT INTO students (name,email,password,roll_no,department,phone) VALUES (%s,%s,%s,%s,%s,%s)",
                (name, email, pw, roll, dept, phone)
            )
            flash("Registration successful! Please login.", "success")
            return redirect(url_for("login"))
        except Error as e:
            flash(f"Registration failed: {e}", "error")
    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("login"))

# ═══════════════════════════════════════════════════════════════════
# STUDENT ROUTES
# ═══════════════════════════════════════════════════════════════════
@app.route("/student/dashboard")
@student_required
def student_dashboard():
    sid     = session["uid"]
    issued  = qall("""
        SELECT i.*, b.title, b.author, b.cover_url, b.category
        FROM   issues i
        JOIN   books  b ON i.book_id = b.id
        WHERE  i.student_id = %s AND i.status = 'issued'
        ORDER  BY i.issue_date DESC
    """, (sid,))

    for rec in issued:
        rec["live_fine"]  = calc_fine(rec["due_date"])
        rec["is_overdue"] = datetime.today().date() > rec["due_date"]

    history = qall("""
        SELECT i.*, b.title, b.author, b.cover_url
        FROM   issues i
        JOIN   books  b ON i.book_id = b.id
        WHERE  i.student_id = %s AND i.status = 'returned'
        ORDER  BY i.return_date DESC
        LIMIT  10
    """, (sid,))

    stats = {
        "issued":     len(issued),
        "returned":   qone("SELECT COUNT(*) AS c FROM issues WHERE student_id=%s AND status='returned'", (sid,))["c"],
        "overdue":    sum(1 for r in issued if r["is_overdue"]),
        "total_fine": sum(r["live_fine"] for r in issued),
    }
    student = qone("SELECT * FROM students WHERE id=%s", (sid,))
    return render_template("student_dashboard.html",
                           issued=issued, history=history,
                           stats=stats, student=student)


@app.route("/student/books")
@student_required
def student_books():
    q   = request.args.get("q",        "").strip()
    cat = request.args.get("category", "").strip()

    cats = [r["category"] for r in qall(
        "SELECT DISTINCT category FROM books WHERE category IS NOT NULL ORDER BY category"
    )]

    if q:
        books = qall("""
            SELECT * FROM books
            WHERE title LIKE %s OR author LIKE %s OR category LIKE %s
            ORDER BY title
        """, (f"%{q}%", f"%{q}%", f"%{q}%"))
    elif cat:
        books = qall("SELECT * FROM books WHERE category=%s ORDER BY title", (cat,))
    else:
        books = qall("SELECT * FROM books ORDER BY title")

    sid = session["uid"]
    issued_ids = {r["book_id"] for r in qall(
        "SELECT book_id FROM issues WHERE student_id=%s AND status='issued'", (sid,)
    )}
    for b in books:
        b["already_issued"] = b["id"] in issued_ids

    return render_template("student_books.html",
                           books=books, query=q, cats=cats, selected_cat=cat)


@app.route("/student/issue/<int:book_id>")
@student_required
def issue_book(book_id):
    sid  = session["uid"]
    book = qone("SELECT * FROM books WHERE id=%s", (book_id,))

    if not book:
        flash("Book not found.", "error")
        return redirect(url_for("student_books"))
    if book["available"] < 1:
        flash("This book is currently unavailable.", "error")
        return redirect(url_for("student_books"))
    if qone("SELECT id FROM issues WHERE book_id=%s AND student_id=%s AND status='issued'",
            (book_id, sid)):
        flash("You have already issued this book.", "error")
        return redirect(url_for("student_books"))

    today    = datetime.today().date()
    due_date = today + timedelta(days=LOAN_DAYS)
    execute(
        "INSERT INTO issues (book_id,student_id,issue_date,due_date,status) VALUES (%s,%s,%s,%s,'issued')",
        (book_id, sid, today, due_date)
    )
    execute("UPDATE books SET available=available-1 WHERE id=%s", (book_id,))
    flash(f'📚 "{book["title"]}" issued! Due date: {due_date.strftime("%d %b %Y")}', "success")
    return redirect(url_for("student_dashboard"))


@app.route("/student/return/<int:issue_id>")
@student_required
def return_book(issue_id):
    rec = qone("SELECT * FROM issues WHERE id=%s AND student_id=%s", (issue_id, session["uid"]))
    if not rec:
        flash("Issue record not found.", "error")
        return redirect(url_for("student_dashboard"))

    today = datetime.today().date()
    fine  = calc_fine(rec["due_date"], today)
    execute("UPDATE issues SET return_date=%s, fine=%s, status='returned' WHERE id=%s",
            (today, fine, issue_id))
    execute("UPDATE books SET available=available+1 WHERE id=%s", (rec["book_id"],))

    if fine > 0:
        flash(f'📕 Book returned with a late fine of ₹{fine:.2f}. Please clear at the counter.', "error")
    else:
        flash("✅ Book returned on time! No fine.", "success")
    return redirect(url_for("student_dashboard"))

# ═══════════════════════════════════════════════════════════════════
# ADMIN ROUTES
# ═══════════════════════════════════════════════════════════════════
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    stats = {
        "total_books":    qone("SELECT COALESCE(SUM(total_copies),0) AS c FROM books")["c"],
        "available":      qone("SELECT COALESCE(SUM(available),0) AS c FROM books")["c"],
        "issued_now":     qone("SELECT COUNT(*) AS c FROM issues WHERE status='issued'")["c"],
        "total_students": qone("SELECT COUNT(*) AS c FROM students")["c"],
        "overdue":        0,
        "total_fines":    0.0,
    }
    issued_records = qall("""
        SELECT i.*, b.title, b.cover_url, s.name AS student_name, s.roll_no
        FROM   issues   i
        JOIN   books    b ON i.book_id    = b.id
        JOIN   students s ON i.student_id = s.id
        WHERE  i.status = 'issued'
        ORDER  BY i.due_date ASC
    """)
    today = datetime.today().date()
    for r in issued_records:
        r["is_overdue"] = r["due_date"] < today
        r["live_fine"]  = calc_fine(r["due_date"])
        if r["is_overdue"]:
            stats["overdue"]     += 1
            stats["total_fines"] += r["live_fine"]

    recent_books = qall("SELECT * FROM books ORDER BY added_on DESC LIMIT 6")
    return render_template("admin_dashboard.html",
                           stats=stats, issued_records=issued_records,
                           recent_books=recent_books)


@app.route("/admin/books")
@admin_required
def admin_books():
    q = request.args.get("q", "").strip()
    books = qall(
        "SELECT * FROM books WHERE title LIKE %s OR author LIKE %s OR isbn LIKE %s ORDER BY title",
        (f"%{q}%", f"%{q}%", f"%{q}%")
    ) if q else qall("SELECT * FROM books ORDER BY title")
    return render_template("admin_books.html", books=books, query=q)


@app.route("/admin/books/add", methods=["GET", "POST"])
@admin_required
def admin_add_book():
    if request.method == "POST":
        title  = request.form["title"].strip()
        author = request.form["author"].strip()
        isbn   = request.form["isbn"].strip() or None
        cat    = request.form["category"].strip()
        pub    = request.form["publisher"].strip()
        year   = request.form["year"] or None
        copies = int(request.form["total_copies"] or 1)
        desc   = request.form["description"].strip()
        cover  = fetch_cover(title, author)
        try:
            execute(
                "INSERT INTO books (title,author,isbn,category,publisher,year,total_copies,available,cover_url,description) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (title, author, isbn, cat, pub, year, copies, copies, cover, desc)
            )
            flash(f'✅ "{title}" added to the library.', "success")
            return redirect(url_for("admin_books"))
        except Error as e:
            flash(f"Error: {e}", "error")
    return render_template("admin_book_form.html", book=None, action="Add")


@app.route("/admin/books/edit/<int:book_id>", methods=["GET", "POST"])
@admin_required
def admin_edit_book(book_id):
    book = qone("SELECT * FROM books WHERE id=%s", (book_id,))
    if not book:
        flash("Book not found.", "error")
        return redirect(url_for("admin_books"))
    if request.method == "POST":
        execute("""
            UPDATE books
            SET title=%s, author=%s, isbn=%s, category=%s, publisher=%s,
                year=%s, total_copies=%s, available=%s, description=%s
            WHERE id=%s
        """, (
            request.form["title"].strip(),
            request.form["author"].strip(),
            request.form["isbn"].strip() or None,
            request.form["category"].strip(),
            request.form["publisher"].strip(),
            request.form["year"] or None,
            int(request.form["total_copies"] or 1),
            int(request.form["available"] or 0),
            request.form["description"].strip(),
            book_id
        ))
        flash("Book updated.", "success")
        return redirect(url_for("admin_books"))
    return render_template("admin_book_form.html", book=book, action="Edit")


@app.route("/admin/books/delete/<int:book_id>")
@admin_required
def admin_delete_book(book_id):
    if qone("SELECT COUNT(*) AS c FROM issues WHERE book_id=%s AND status='issued'", (book_id,))["c"]:
        flash("Cannot delete — book has active issues.", "error")
    else:
        execute("DELETE FROM books WHERE id=%s", (book_id,))
        flash("Book deleted.", "success")
    return redirect(url_for("admin_books"))


@app.route("/admin/students")
@admin_required
def admin_students():
    q = request.args.get("q", "").strip()
    sql = """
        SELECT s.*,
            (SELECT COUNT(*) FROM issues WHERE student_id=s.id AND status='issued')   AS active_issues,
            (SELECT COUNT(*) FROM issues WHERE student_id=s.id AND status='returned') AS total_returned
        FROM students s
        {where}
        ORDER BY s.name
    """
    if q:
        students = qall(
            sql.format(where="WHERE s.name LIKE %s OR s.roll_no LIKE %s OR s.email LIKE %s"),
            (f"%{q}%", f"%{q}%", f"%{q}%")
        )
    else:
        students = qall(sql.format(where=""))
    return render_template("admin_students.html", students=students, query=q)


@app.route("/admin/students/<int:sid>")
@admin_required
def admin_student_detail(sid):
    student = qone("SELECT * FROM students WHERE id=%s", (sid,))
    if not student:
        flash("Student not found.", "error")
        return redirect(url_for("admin_students"))

    issues = qall("""
        SELECT i.*, b.title, b.author, b.cover_url
        FROM   issues i
        JOIN   books  b ON i.book_id = b.id
        WHERE  i.student_id = %s
        ORDER  BY i.issue_date DESC
    """, (sid,))

    today = datetime.today().date()
    total_fine = 0.0
    for r in issues:
        r["is_overdue"] = r["status"] == "issued" and r["due_date"] < today
        r["live_fine"]  = calc_fine(r["due_date"]) if r["status"] == "issued" else float(r["fine"] or 0)
        total_fine += r["live_fine"]

    return render_template("admin_student_detail.html",
                           student=student, issues=issues, total_fine=total_fine)


@app.route("/admin/issued")
@admin_required
def admin_issued():
    records = qall("""
        SELECT i.*, b.title, b.author, b.cover_url, b.category,
               s.name AS student_name, s.roll_no, s.email AS student_email
        FROM   issues   i
        JOIN   books    b ON i.book_id    = b.id
        JOIN   students s ON i.student_id = s.id
        WHERE  i.status = 'issued'
        ORDER  BY i.due_date ASC
    """)
    today = datetime.today().date()
    for r in records:
        r["is_overdue"] = r["due_date"] < today
        r["live_fine"]  = calc_fine(r["due_date"])
        r["days_left"]  = (r["due_date"] - today).days
    return render_template("admin_issued.html", records=records, today=today)


@app.route("/admin/return/<int:issue_id>")
@admin_required
def admin_return_book(issue_id):
    rec = qone("SELECT * FROM issues WHERE id=%s", (issue_id,))
    if not rec:
        flash("Record not found.", "error")
        return redirect(url_for("admin_issued"))
    today = datetime.today().date()
    fine  = calc_fine(rec["due_date"], today)
    execute("UPDATE issues SET return_date=%s, fine=%s, status='returned' WHERE id=%s",
            (today, fine, issue_id))
    execute("UPDATE books SET available=available+1 WHERE id=%s", (rec["book_id"],))
    flash(f"Book returned. Fine: ₹{fine:.2f}", "success" if fine == 0 else "error")
    return redirect(url_for("admin_issued"))


@app.route("/api/cover")
def api_cover():
    return jsonify({"cover": fetch_cover(
        request.args.get("title",  ""),
        request.args.get("author", "")
    )})


if __name__ == "__main__":
    app.run(debug=True)