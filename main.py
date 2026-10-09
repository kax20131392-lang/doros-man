
import os
import sqlite3
import secrets
from functools import wraps
from flask import (
    Flask, request, redirect, url_for,
    session, render_template_string, flash
)
from werkzeug.security import generate_password_hash, check_password_hash

# ----------------------------------------
# تنظیمات اصلی برنامه دروس من
# ----------------------------------------

app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY", secrets.token_hex(32)
)

DATABASE = os.environ.get("DATABASE_PATH", "doroseman.db")


# ----------------------------------------
# اتصال و ساخت پایگاه داده
# ----------------------------------------

def connect_db():
    db = sqlite3.connect(DATABASE, timeout=20)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with connect_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            pin_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            school_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS schools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT NOT NULL UNIQUE,
            manager_id INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS homework (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL,
            school_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            homework_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            answer TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(homework_id, student_id)
        );

        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER NOT NULL,
            manager_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)


init_db()


# ----------------------------------------
# قالب مشترک صفحات فارسی
# ----------------------------------------

PAGE = """
<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport"
 content="width=device-width, initial-scale=1">
<title>دروس من</title>
<style>
* { box-sizing: border-box; }
body {
    font-family: Tahoma, sans-serif;
    background: #f1f5f9;
    color: #172033;
    margin: 0;
    padding: 16px;
}
main {
    max-width: 650px;
    margin: 20px auto;
    background: white;
    padding: 22px;
    border-radius: 16px;
    box-shadow: 0 4px 18px #0001;
}
h1 { color: #167647; font-size: 25px; }
h2 { font-size: 19px; }
input, select, textarea, button {
    font: inherit;
    width: 100%;
    padding: 12px;
    margin: 7px 0;
    border: 1px solid #cbd5e1;
    border-radius: 9px;
}
textarea { min-height: 100px; }
button, .btn {
    background: #167647;
    color: white;
    border: 0;
    cursor: pointer;
    display: inline-block;
    text-align: center;
    text-decoration: none;
    padding: 12px;
    border-radius: 9px;
}
.secondary { background: #475569; }
.item {
    padding: 12px;
    margin: 10px 0;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    overflow-wrap: anywhere;
}
a { color: #087443; }
small { color: #64748b; }
</style>
</head>
<body>
<main>
<h1>📚 دروس من</h1>
{% with messages = get_flashed_messages() %}
{% for message in messages %}
<div class="item">{{ message }}</div>
{% endfor %}
{% endwith %}
{{ content|safe }}
</main>
</body>
</html>
"""


def page(content, **kwargs):
    return render_template_string(
        PAGE, content=render_template_string(
            content, **kwargs
        )
    )


# ----------------------------------------
# بررسی ورود کاربر
# ----------------------------------------

def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper


def current_user():
    with connect_db() as db:
        return db.execute(
            "SELECT * FROM users WHERE id=?",
            (session.get("user_id"),)
        ).fetchone()


def role_required(*roles):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for("login"))
            if user["role"] not in roles:
                return "شما اجازه دسترسی به این بخش را ندارید.", 403
            return func(*args, **kwargs)
        return wrapper
    return decorator


# ----------------------------------------
# صفحه اصلی
# ----------------------------------------

@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    return page("""
    <h2>به مدرسه‌ای برای یادگیری خوش آمدی!</h2>
    <p>در دروس من می‌توانی مشق‌ها و اطلاعیه‌های مدرسه را ببینی.</p>
    <a class="btn" href="{{ url_for('register') }}">ثبت‌نام</a>
    <a class="btn secondary" href="{{ url_for('login') }}">ورود</a>
    """)


# ----------------------------------------
# ثبت‌نام و بررسی اطلاعات
# ----------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        first = request.form.get("first_name", "").strip()
        last = request.form.get("last_name", "").strip()
        phone = request.form.get("phone", "").strip()
        pin = request.form.get("pin", "").strip()
        role = request.form.get("role", "")

        if not first or not last or not phone:
            flash("لطفاً همه اطلاعات را وارد کن.")
            return redirect(url_for("register"))

        if not phone.isdigit() or not 10 <= len(phone) <= 13:
            flash("شماره تلفن را درست وارد کن.")
            return redirect(url_for("register"))

        if len(pin) != 4 or not pin.isdigit():
            flash("کد شخصی باید دقیقاً چهار رقم باشد.")
            return redirect(url_for("register"))

        if role not in ("student", "teacher", "manager"):
            flash("نقش انتخاب‌شده معتبر نیست.")
            return redirect(url_for("register"))

        with connect_db() as db:
            exists = db.execute(
                "SELECT id FROM users WHERE phone=?", (phone,)
            ).fetchone()

        if exists:
            flash("این شماره قبلاً ثبت شده است؛ وارد شو.")
            return redirect(url_for("login"))

        session["pending_user"] = {
            "first_name": first,
            "last_name": last,
            "phone": phone,
            "pin": pin,
            "role": role
        }
        return redirect(url_for("review"))

    return page("""
    <h2>ثبت‌نام</h2>
    <form method="post">
      <label>اسم</label>
      <input name="first_name" required maxlength="60">
      <label>فامیل</label>
      <input name="last_name" required maxlength="60">
      <label>شماره تلفن</label>
      <input name="phone" inputmode="numeric"
       required maxlength="13">
      <label>کد شخصی چهاررقمی</label>
      <input name="pin" type="password"
       inputmode="numeric" pattern="[0-9]{4}"
       maxlength="4" required>
      <label>نقش خود را انتخاب کن</label>
      <select name="role" required>
        <option value="student">دانش‌آموز</option>
        <option value="teacher">معلم</option>
        <option value="manager">مدیر</option>
      </select>
      <button>بررسی اطلاعات</button>
    </form>
    <a href="{{ url_for('index') }}">بازگشت</a>
    """)


@app.route("/review", methods=["GET", "POST"])
def review():
    data = session.get("pending_user")
    if not data:
        return redirect(url_for("register"))

    roles = {
        "student": "دانش‌آموز",
        "teacher": "معلم",
        "manager": "مدیر"
    }

    if request.method == "POST":
        with connect_db() as db:
            try:
                cur = db.execute("""
                    INSERT INTO users
                    (first_name, last_name, phone, pin_hash, role)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    data["first_name"],
                    data["last_name"],
                    data["phone"],
                    generate_password_hash(data["pin"]),
                    data["role"]
                ))
                user_id = cur.lastrowid
            except sqlite3.IntegrityError:
                flash("این شماره قبلاً ثبت شده است.")
                return redirect(url_for("login"))

        session.pop("pending_user", None)
        session.clear()
        session["user_id"] = user_id
        return redirect(url_for("dashboard"))

    return page("""
    <h2>بازبینی اطلاعات</h2>
    <div class="item">اسم: {{ data.first_name }}</div>
    <div class="item">فامیل: {{ data.last_name }}</div>
    <div class="item">شماره: {{ data.phone }}</div>
    <div class="item">کد شخصی: ****</div>
    <div class="item">نقش: {{ roles[data.role] }}</div>
    <p>اگر اطلاعات درست است ثبت‌نام را نهایی کن.</p>
    <form method="post">
      <button>تأیید و ثبت‌نام</button>
    </form>
    <a class="btn secondary" href="{{ url_for('register') }}">
      اصلاح اطلاعات
    </a>
    """, data=data, roles=roles)


# ----------------------------------------
# ورود به حساب
# ----------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        pin = request.form.get("pin", "").strip()

        with connect_db() as db:
            user = db.execute(
                "SELECT * FROM users WHERE phone=?", (phone,)
            ).fetchone()

        if user and check_password_hash(user["pin_hash"], pin):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))

        flash("شماره تلفن یا کد شخصی اشتباه است.")

    return page("""
    <h2>ورود به دروس من</h2>
    <form method="post">
      <label>شماره تلفن</label>
      <input name="phone" inputmode="numeric" required>
      <label>کد شخصی چهاررقمی</label>
      <input name="pin" type="password"
       inputmode="numeric" maxlength="4" required>
      <button>ورود</button>
    </form>
    <a href="{{ url_for('register') }}">هنوز ثبت‌نام نکرده‌ام</a>
    """)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ----------------------------------------
# داشبورد کاربران
# ----------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    if not user:
        session.clear()
        return redirect(url_for("login"))

    roles = {
        "student": "دانش‌آموز",
        "teacher": "معلم",
        "manager": "مدیر"
    }

    return page("""
    <h2>سلام {{ user.first_name }} عزیز!</h2>
    <p>نقش شما: {{ roles[user.role] }}</p>
    <div class="item">
      <a href="{{ url_for('school') }}">🏫 مدرسه من</a>
    </div>
    <div class="item">
      <a href="{{ url_for('ask_ai') }}">🤖 از هوش مصنوعی بپرس</a>
    </div>
    <a href="{{ url_for('logout') }}">خروج از حساب</a>
    """, user=user, roles=roles)


# ----------------------------------------
# هوش مصنوعی: فعلاً صفحه آماده‌سازی
# ----------------------------------------

@app.route("/ask-ai")
@login_required
def ask_ai():
    user = current_user()
    topics = {
        "student": "سؤال و جواب درسی",
        "teacher": "آموزش و تدریس",
        "manager": "نحوه مدیریت کردن"
    }
    return page("""
    <h2>از هوش مصنوعی بپرس</h2>
    <p>موضوع پیشنهادی برای شما: {{ topic }}</p>
    <p>اتصال به هوش مصنوعی هنوز راه‌اندازی نشده است.</p>
    <a href="{{ url_for('dashboard') }}">بازگشت</a>
    """, topic=topics[user["role"]])


# ----------------------------------------
# مدرسه من: ساخت یا عضویت در مدرسه
# ----------------------------------------

@app.route("/school", methods=["GET", "POST"])
@login_required
def school():
    user = current_user()

    if request.method == "POST":
        action = request.form.get("action")

        with connect_db() as db:
            if action == "create" and user["role"] == "manager":
                name = request.form.get("name", "").strip()
                code = request.form.get("code", "").strip()

                if not name or len(code) != 5 or not code.isdigit():
                    flash("نام مدرسه و کد پنج‌رقمی معتبر وارد کن.")
                    return redirect(url_for("school"))

                try:
                    cur = db.execute(
                        "INSERT INTO schools (name, code, manager_id) "
                        "VALUES (?, ?, ?)",
                        (name, code, user["id"])
                    )
                    db.execute(
                        "UPDATE users SET school_id=? WHERE id=?",
                        (cur.lastrowid, user["id"])
                    )
                    flash("مدرسه ساخته شد.")
                except sqlite3.IntegrityError:
                    flash("این کد مدرسه قبلاً استفاده شده است.")

            elif action == "join" and user["role"] in (
                "teacher", "student"
            ):
                code = request.form.get("code", "").strip()
                school_row = db.execute(
                    "SELECT id FROM schools WHERE code=?", (code,)
                ).fetchone()

                if school_row:
                    db.execute(
                        "UPDATE users SET school_id=? WHERE id=?",
                        (school_row["id"], user["id"])
                    )
                    flash("عضویت در مدرسه انجام شد.")
                else:
                    flash("کد مدرسه پیدا نشد.")

        return redirect(url_for("school"))

    with connect_db() as db:
        school_row = None
        if user["school_id"]:
            school_row = db.execute(
                "SELECT * FROM schools WHERE id=?",
                (user["school_id"],)
            ).fetchone()

    return page("""
    <h2>مدرسه من</h2>

    {% if school_row %}
      <div class="item">
        نام مدرسه: {{ school_row.name }}<br>
        کد مدرسه: {{ school_row.code }}
      </div>
      {% if user.role == 'manager' %}
        <a href="{{ url_for('announcement') }}">تابلو اعلانات</a>
      {% endif %}
      {% if user.role == 'teacher' %}
        <a href="{{ url_for('homework') }}">بخش مشق</a>
      {% endif %}
      {% if user.role == 'student' %}
        <a href="{{ url_for('homework') }}">دیدن مشق‌ها</a>
      {% endif %}
    {% else %}
      {% if user.role == 'manager' %}
        <h3>ساخت مدرسه</h3>
        <form method="post">
          <input type="hidden" name="action" value="create">
          <label>نام مدرسه</label>
          <input name="name" required maxlength="100">
          <label>کد پنج‌رقمی دلخواه</label>
          <input name="code" inputmode="numeric"
           pattern="[0-9]{5}" maxlength="5" required>
          <button>ساخت مدرسه</button>
        </form>
      {% else %}
        <h3>ورود به مدرسه</h3>
        <form method="post">
          <input type="hidden" name="action" value="join">
          <label>کد پنج‌رقمی مدرسه</label>
          <input name="code" inputmode="numeric"
           pattern="[0-9]{5}" maxlength="5" required>
          <button>ورود به مدرسه</button>
        </form>
      {% endif %}
    {% endif %}
    <a href="{{ url_for('dashboard') }}">بازگشت</a>
    """, user=user, school_row=school_row)


# ----------------------------------------
# بخش مشق معلم و دانش‌آموز
# ----------------------------------------

@app.route("/homework", methods=["GET", "POST"])
@login_required
@role_required("teacher", "student")
def homework():
    user = current_user()

    if not user["school_id"]:
        flash("ابتدا با کد مدرسه وارد مدرسه شو.")
        return redirect(url_for("school"))

    with connect_db() as db:
        if request.method == "POST" and user["role"] == "teacher":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()

            if title and description:
                db.execute("""
                    INSERT INTO homework
                    (teacher_id, school_id, title, description)
                    VALUES (?, ?, ?, ?)
                """, (
                    user["id"], user["school_id"],
                    title, description
                ))
                flash("مشق ثبت شد.")
                return redirect(url_for("homework"))

        if request.method == "POST" and user["role"] == "student":
            answer = request.form.get("answer", "").strip()
            homework_id = request.form.get("homework_id", type=int)

            task = db.execute(
                "SELECT id FROM homework WHERE id=? AND school_id=?",
                (homework_id, user["school_id"])
            ).fetchone()

            if task and answer:
                db.execute("""
                    INSERT INTO submissions
                    (homework_id, student_id, answer)
                    VALUES (?, ?, ?)
                    ON CONFLICT(homework_id, student_id)
                    DO UPDATE SET answer=excluded.answer,
                    created_at=CURRENT_TIMESTAMP
                """, (homework_id, user["id"], answer))
                flash("پاسخ مشق ارسال شد.")
                return redirect(url_for("homework"))

        tasks = db.execute("""
            SELECT homework.*, users.first_name, users.last_name
            FROM homework
            JOIN users ON users.id=homework.teacher_id
            WHERE homework.school_id=?
            ORDER BY homework.id DESC
        """, (user["school_id"],)).fetchall()

        answers = {}
        if user["role"] == "teacher":
            rows = db.execute("""
                SELECT submissions.*, users.first_name, users.last_name
                FROM submissions
                JOIN users ON users.id=submissions.student_id
                JOIN homework ON homework.id=submissions.homework_id
                WHERE homework.teacher_id=?
                ORDER BY submissions.id DESC
            """, (user["id"],)).fetchall()
            answers = {}
            for row in rows:
                answers.setdefault(row["homework_id"], []).append(row)

        if user["role"] == "student":
            rows = db.execute(
                "SELECT homework_id, answer FROM submissions "
                "WHERE student_id=?", (user["id"],)
            ).fetchall()
            answers = {r["homework_id"]: r["answer"] for r in rows}

    return page("""
    <h2>بخش مشق</h2>

    {% if user.role == 'teacher' %}
    <h3>ثبت مشق جدید</h3>
    <form method="post">
      <label>عنوان مشق</label>
      <input name="title" required maxlength="150">
      <label>توضیحات و متن مشق</label>
      <textarea name="description" required maxlength="5000"></textarea>
      <button>ثبت مشق</button>
    </form>
    {% endif %}

    <h3>مشق‌های مدرسه</h3>
    {% for task in tasks %}
      <div class="item">
        <b>{{ task.title }}</b>
        <p>{{ task.description }}</p>
        <small>معلم: {{ task.first_name }} {{ task.last_name }}</small>

        {% if user.role == 'student' %}
        <form method="post">
          <input type="hidden" name="homework_id"
           value="{{ task.id }}">
          <label>پاسخ شما (متن)</label>
          <textarea name="answer" required>{{ answers.get(task.id, '') }}</textarea>
          <button>ارسال پاسخ</button>
        </form>
        {% else %}
          {% for answer in answers.get(task.id, []) %}
            <div class="item">
              پاسخ {{ answer.fir
