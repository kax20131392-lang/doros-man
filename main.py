"""
دروس من - نسخه یکپارچه قابل توسعه
Flask + SQLite
نکته: پیش از استفاده واقعی، SECRET_KEY و AI_API_KEY را در متغیرهای محیطی تنظیم کنید.
"""
import os, re, json, secrets, sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, request, redirect, url_for, session, flash,
                   render_template, abort, jsonify, render_template_string)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DATABASE_PATH", str(BASE / "doros_man.sqlite3")))
UPLOAD_DIR = BASE / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_UPLOADS = {"png", "jpg", "jpeg", "webp", "gif", "mp3", "wav", "ogg", "m4a"}

app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "CHANGE-ME-before-deployment-" + secrets.token_hex(16)
)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "0") == "1"

ROLES = {
    "manager": "مدیر",
    "teacher": "معلم",
    "student": "دانش‌آموز"
}


def db_conn():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with db_conn() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          first_name TEXT NOT NULL,
          last_name TEXT NOT NULL,
          phone TEXT NOT NULL UNIQUE,
          pin_hash TEXT NOT NULL,
          role TEXT NOT NULL
            CHECK(role IN ('manager','teacher','student')),
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS schools(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          code TEXT NOT NULL UNIQUE,
          manager_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS classes(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          school_id INTEGER NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
          name TEXT NOT NULL,
          UNIQUE(school_id,name)
        );

        CREATE TABLE IF NOT EXISTS memberships(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          school_id INTEGER NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          class_id INTEGER REFERENCES classes(id) ON DELETE SET NULL,
          status TEXT NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending','approved','rejected')),
          method TEXT NOT NULL DEFAULT 'request',
          UNIQUE(school_id,user_id)
        );

        CREATE TABLE IF NOT EXISTS notices(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          school_id INTEGER NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
          author_id INTEGER NOT NULL REFERENCES users(id),
          title TEXT NOT NULL,
          body TEXT NOT NULL,
          image_path TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS homework(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          school_id INTEGER NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
          teacher_id INTEGER NOT NULL REFERENCES users(id),
          title TEXT NOT NULL,
          description TEXT NOT NULL,
          due_at TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS submissions(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          homework_id INTEGER NOT NULL REFERENCES homework(id) ON DELETE CASCADE,
          student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          answer TEXT DEFAULT '',
          file_path TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(homework_id,student_id)
        );

        CREATE TABLE IF NOT EXISTS exams(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          school_id INTEGER NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
          teacher_id INTEGER NOT NULL REFERENCES users(id),
          title TEXT NOT NULL,
          entry_start TEXT NOT NULL,
          entry_end TEXT NOT NULL,
          duration_minutes INTEGER NOT NULL,
          class_id INTEGER REFERENCES classes(id) ON DELETE SET NULL,
          published INTEGER NOT NULL DEFAULT 0,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS questions(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
          question_text TEXT NOT NULL,
          a TEXT NOT NULL,
          b TEXT NOT NULL,
          c TEXT NOT NULL,
          d TEXT NOT NULL,
          correct TEXT NOT NULL CHECK(correct IN ('a','b','c','d')),
          points REAL NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS exam_attempts(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
          student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          started_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          submitted_at TEXT,
          score REAL,
          status TEXT NOT NULL DEFAULT 'in_progress',
          authorized_reentry INTEGER NOT NULL DEFAULT 0,
          UNIQUE(exam_id,student_id)
        );

        CREATE TABLE IF NOT EXISTS exam_answers(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          attempt_id INTEGER NOT NULL REFERENCES exam_attempts(id) ON DELETE CASCADE,
          question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
          answer TEXT,
          UNIQUE(attempt_id,question_id)
        );

        CREATE TABLE IF NOT EXISTS exam_events(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          attempt_id INTEGER NOT NULL REFERENCES exam_attempts(id) ON DELETE CASCADE,
          event_type TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ai_messages(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          role TEXT NOT NULL,
          content TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)


init_db()
SHELL = """
<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} | دروس من</title>
<style>
:root{font-family:Tahoma,Arial,sans-serif;color:#172033;background:#f1f5f9}
body{margin:0;padding:16px}
main{max-width:850px;margin:18px auto;background:white;padding:22px;border-radius:16px;box-shadow:0 5px 25px #17203312}
h1{color:#176b52;font-size:25px}
h2{font-size:20px;color:#203047}
h3{font-size:17px}
input,select,textarea,button{box-sizing:border-box;width:100%;padding:11px;margin:6px 0 13px;border:1px solid #cbd5e1;border-radius:9px;font:inherit}
textarea{min-height:90px}
button,.btn{background:#176b52;color:white;border:0;padding:11px 14px;border-radius:9px;text-decoration:none;display:inline-block;cursor:pointer}
.btn.secondary{background:#e7edf2;color:#172033}
.nav{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 20px}
.nav .btn{font-size:14px}
.card{background:#f6f8fa;border:1px solid #e4e9ef;border-radius:12px;padding:14px;margin:12px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}
small,.muted{color:#64748b}
.error{color:#b42318}
.ok{color:#087443}
table{width:100%;border-collapse:collapse}
td,th{padding:9px;border-bottom:1px solid #e2e8f0;text-align:right;vertical-align:top}
img.upload{max-width:100%;max-height:260px;border-radius:10px}
.pill{background:#e8f3ee;padding:4px 8px;border-radius:20px}
</style></head><body><main><h1>دروس من</h1>
{% for message in get_flashed_messages() %}<p class="ok">{{ message }}</p>{% endfor %}
{% block content %}{% endblock %}</main></body></html>
"""

# ساخت پوشه قالب‌ها و ذخیره قالب پایه
(BASE / "templates").mkdir(parents=True, exist_ok=True)
(BASE / "templates" / "base.html").write_text(SHELL, encoding="utf-8")


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None

    with db_conn() as db:
        return db.execute(
            "SELECT * FROM users WHERE id=?",
            (uid,)
        ).fetchone()


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped


def role_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            user = current_user()

            if not user:
                return redirect(url_for("login"))

            if user["role"] not in roles:
                abort(403)

            return fn(*args, **kwargs)
        return wrapped
    return deco


def page(title, body, **ctx):
    return render_template_string(
        SHELL.replace(
            "{% block content %}{% endblock %}",
            body
        ),
        title=title,
        user=current_user(),
        roles=ROLES,
        **ctx
    )


def school_for_user(user):
    with db_conn() as db:
        if user["role"] == "manager":
            return db.execute(
                "SELECT * FROM schools WHERE manager_id=?",
                (user["id"],)
            ).fetchone()

        return db.execute("""
            SELECT s.*
            FROM schools s
            JOIN memberships m ON m.school_id=s.id
            WHERE m.user_id=? AND m.status='approved'
            ORDER BY m.id DESC
            LIMIT 1
        """, (user["id"],)).fetchone()


def membership_for(user, school_id):
    with db_conn() as db:
        return db.execute(
            "SELECT * FROM memberships WHERE user_id=? AND school_id=?",
            (user["id"], school_id)
        ).fetchone()


def allowed_file(file):
    return bool(
        file
        and "." in file.filename
        and file.filename.rsplit(".", 1)[1].lower() in ALLOWED_UPLOADS
    )


def save_upload(file):
    if not file or not file.filename:
        return None

    if not allowed_file(file):
        raise ValueError("نوع فایل مجاز نیست.")

    ext = file.filename.rsplit(".", 1)[1].lower()
    name = secrets.token_hex(16) + "." + ext
    file.save(UPLOAD_DIR / name)

    return "uploads/" + name


def parse_local_time(value):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


@app.route("/")
def index():
    user = current_user()

    if user:
        return redirect(url_for("home"))

    return page("خانه", """
    <p>سامانه آموزشی آنلاین برای مدیران، معلمان و دانش‌آموزان.</p>
    <div class="nav">
      <a class="btn" href="{{ url_for('register') }}">ثبت‌نام</a>
      <a class="btn secondary" href="{{ url_for('login') }}">ورود</a>
    </div>
    """)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user():
        return redirect(url_for("home"))

    if request.method == "POST":
        first = request.form.get("first_name", "").strip()
        last = request.form.get("last_name", "").strip()
        phone = request.form.get("phone", "").strip()
        pin = request.form.get("pin", "")
        role = request.form.get("role", "")

        if not first or not last or len(first) > 60 or len(last) > 60:
            flash("نام و نام خانوادگی را بررسی کن.")

        elif not re.fullmatch(r"[0-9]{8,15}", phone):
            flash("شماره تلفن باید ۸ تا ۱۵ رقم انگلیسی باشد.")

        elif not re.fullmatch(r"[0-9]{4}", pin):
            flash("رمز شخصی باید چهار رقم انگلیسی باشد.")

        elif role not in ROLES:
            flash("نقش معتبر نیست.")

        else:
            with db_conn() as db:
                exists = db.execute(
                    "SELECT id FROM users WHERE phone=?",
                    (phone,)
                ).fetchone()

            if exists:
                flash("این شماره قبلاً ثبت شده است.")
            else:
                session["registration"] = {
                    "first_name": first,
                    "last_name": last,
                    "phone": phone,
                    "pin": pin,
                    "role": role
                }
                return redirect(url_for("review_registration"))

    return page("ثبت‌نام", """
    <h2>ثبت‌نام</h2>
    <form method="post">
      <label>نام</label>
      <input name="first_name" maxlength="60" required>

      <label>نام خانوادگی</label>
      <input name="last_name" maxlength="60" required>

      <label>شماره تلفن (با ارقام انگلیسی)</label>
      <input name="phone" inputmode="numeric" maxlength="15" required>

      <label>رمز شخصی چهاررقمی</label>
      <input name="pin" type="password" inputmode="numeric"
             pattern="[0-9]{4}" maxlength="4" required>

      <label>نقش</label>
      <select name="role" required>
        <option value="">انتخاب کن</option>
        <option value="manager">مدیر</option>
        <option value="teacher">معلم</option>
        <option value="student">دانش‌آموز</option>
      </select>

      <button>بررسی اطلاعات</button>
    </form>
    <small>فیلد پایهٔ تحصیلی در ثبت‌نام وجود ندارد.</small>
    """)


@app.route("/register/review", methods=["GET", "POST"])
def review_registration():
    data = session.get("registration")

    if not data:
        return redirect(url_for("register"))

    if request.method == "POST":
        with db_conn() as db:
            try:
                cur = db.execute("""
                    INSERT INTO users(
                        first_name, last_name, phone, pin_hash, role
                    )
                    VALUES(?,?,?,?,?)
                """, (
                    data["first_name"],
                    data["last_name"],
                    data["phone"],
                    generate_password_hash(data["pin"]),
                    data["role"]
                ))
                uid = cur.lastrowid

            except sqlite3.IntegrityError:
                flash("این شماره قبلاً ثبت شده است.")
                return redirect(url_for("register"))

        session.clear()
        session["user_id"] = uid
        return redirect(url_for("home"))

    return page("تأیید ثبت‌نام", """
    <h2>بررسی اطلاعات</h2>
    <div class="card">
      <p>نام: {{ data.first_name }}</p>
      <p>نام خانوادگی: {{ data.last_name }}</p>
      <p>شماره: {{ data.phone }}</p>
      <p>رمز شخصی: ••••</p>
      <p>نقش: {{ roles[data.role] }}</p>
    </div>

    <a class="btn secondary" href="{{ url_for('register') }}">
      بازگشت برای اصلاح
    </a>

    <form method="post">
      <button>تأیید و ساخت حساب</button>
    </form>
    """, data=data)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("home"))

    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        pin = request.form.get("pin", "")

        with db_conn() as db:
            user = db.execute(
                "SELECT * FROM users WHERE phone=?",
                (phone,)
            ).fetchone()

        if user and check_password_hash(user["pin_hash"], pin):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("home"))

        flash("شماره یا رمز اشتباه است.")

    return page("ورود", """
    <h2>ورود</h2>
    <form method="post">
      <label>شماره تلفن</label>
      <input name="phone" required>

      <label>رمز چهاررقمی</label>
      <input name="pin" type="password" inputmode="numeric"
             maxlength="4" required>

      <button>ورود</button>
    </form>
    <a href="{{ url_for('register') }}">ثبت‌نام</a>
    """)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))
  @app.route("/home")
@login_required
def home():
    u = current_user()
    school = school_for_user(u)

    with db_conn() as db:
        notices = []
        upcoming = []

        if school:
            notices = db.execute(
                "SELECT * FROM notices WHERE school_id=? ORDER BY id DESC LIMIT 5",
                (school["id"],)
            ).fetchall()

            if u["role"] == "student":
                upcoming = db.execute(
                    """SELECT * FROM exams
                       WHERE school_id=? AND published=1
                       ORDER BY entry_start LIMIT 10""",
                    (school["id"],)
                ).fetchall()

    body = """
    <h2>سلام {{ u['first_name'] }} {{ u['last_name'] }} 👋</h2>

    {% if school %}
      <p>مدرسه شما: <b>{{ school['name'] }}</b></p>
      <p>کد مدرسه: <b>{{ school['code'] }}</b></p>
      <p><a href="{{ url_for('school') }}">ورود به مدرسه من</a></p>
    {% else %}
      <p>هنوز به مدرسه‌ای متصل نشده‌اید.</p>
      {% if u['role'] == 'manager' %}
        <p><a href="{{ url_for('school') }}">ساخت مدرسه</a></p>
      {% else %}
        <p><a href="{{ url_for('school') }}">پیوستن به مدرسه</a></p>
      {% endif %}
    {% endif %}

    <h3>تابلو اطلاعیه‌ها</h3>
    {% for n in notices %}
      <div class="card">
        <b>{{ n['title'] }}</b>
        <p>{{ n['body'] }}</p>
        {% if n['image_path'] %}
          <img src="{{ url_for('uploaded_file', filename=n['image_path']) }}"
               style="max-width:100%;height:auto">
        {% endif %}
      </div>
    {% else %}
      <p>هنوز اطلاعیه‌ای ثبت نشده است.</p>
    {% endfor %}

    {% if u['role'] == 'student' %}
      <h3>امتحان‌های منتشرشده</h3>
      {% for e in upcoming %}
        <div class="card">
          <b>{{ e['title'] }}</b>
          <p><a href="{{ url_for('take_exam', exam_id=e['id']) }}">
            ورود به امتحان
          </a></p>
        </div>
      {% else %}
        <p>امتحان منتشرشده‌ای وجود ندارد.</p>
      {% endfor %}
    {% endif %}

    <p><a href="{{ url_for('ai_chat') }}">از هوش مصنوعی بپرس</a></p>
    """
    return page(
        "صفحه اصلی",
        body,
        u=u,
        school=school,
        notices=notices,
        upcoming=upcoming
    )


@app.route("/school", methods=["GET", "POST"])
@login_required
def school():
    u = current_user()

    if request.method == "POST":
        action = request.form.get("action", "").strip()

        if action == "create":
            if u["role"] != "manager":
                abort(403)

            name = request.form.get("name", "").strip()

            if len(name) < 2:
                flash("نام مدرسه را درست وارد کن.")
                return redirect(url_for("school"))

            code = None

            with db_conn() as db:
                for _ in range(30):
                    candidate = f"{secrets.randbelow(100000):05d}"
                    exists = db.execute(
                        "SELECT id FROM schools WHERE code=?",
                        (candidate,)
                    ).fetchone()

                    if not exists:
                        code = candidate
                        break

                if code is None:
                    flash("ساخت کد مدرسه ناموفق بود؛ دوباره تلاش کن.")
                    return redirect(url_for("school"))

                db.execute(
                    """INSERT INTO schools
                       (name, code, manager_id, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (name, code, u["id"], datetime.now().isoformat())
                )

            flash(f"مدرسه ساخته شد. کد مدرسه: {code}")
            return redirect(url_for("school"))

        if action == "join":
            code = request.form.get("code", "").strip()

            if not re.fullmatch(r"\d{5}", code):
                flash("کد مدرسه باید دقیقاً ۵ رقم باشد.")
                return redirect(url_for("school"))

            with db_conn() as db:
                target = db.execute(
                    "SELECT * FROM schools WHERE code=?",
                    (code,)
                ).fetchone()

                if not target:
                    flash("مدرسه‌ای با این کد پیدا نشد.")
                    return redirect(url_for("school"))

                if u["role"] == "manager":
                    flash("مدیر نمی‌تواند با این روش عضو مدرسه دیگری شود.")
                    return redirect(url_for("school"))

                existing = db.execute(
                    """SELECT * FROM memberships
                       WHERE user_id=? AND school_id=?""",
                    (u["id"], target["id"])
                ).fetchone()

                if existing and existing["status"] == "approved":
                    flash("عضویت شما در این مدرسه تأیید شده است.")
                    return redirect(url_for("school"))

                if existing:
                    db.execute(
                        """UPDATE memberships
                           SET status='pending'
                           WHERE id=?""",
                        (existing["id"],)
                    )
                else:
                    db.execute(
                        """INSERT INTO memberships
                           (user_id, school_id, status, created_at)
                           VALUES (?, ?, 'pending', ?)""",
                        (
                            u["id"],
                            target["id"],
                            datetime.now().isoformat()
                        )
                    )

            flash("درخواست عضویت برای مدیر مدرسه ارسال شد.")
            return redirect(url_for("school"))

    school_data = school_for_user(u)
    memberships = []
    classes = []
    students = []
    requests = []

    with db_conn() as db:
        if u["role"] != "manager":
            memberships = db.execute(
                """SELECT m.*, s.name AS school_name, s.code AS school_code
                   FROM memberships m
                   JOIN schools s ON s.id=m.school_id
                   WHERE m.user_id=?
                   ORDER BY m.id DESC""",
                (u["id"],)
            ).fetchall()

        if school_data and u["role"] == "manager":
            classes = db.execute(
                """SELECT * FROM classes
                   WHERE school_id=?
                   ORDER BY name""",
                (school_data["id"],)
            ).fetchall()

            students = db.execute(
                """SELECT u.id, u.first_name, u.last_name, u.phone,
                          m.status, c.name AS class_name
                   FROM memberships m
                   JOIN users u ON u.id=m.user_id
                   LEFT JOIN classes c ON c.id=m.class_id
                   WHERE m.school_id=? AND u.role='student'
                   ORDER BY u.last_name, u.first_name""",
                (school_data["id"],)
            ).fetchall()

            requests = db.execute(
                """SELECT m.id, u.first_name, u.last_name, u.phone
                   FROM memberships m
                   JOIN users u ON u.id=m.user_id
                   WHERE m.school_id=? AND m.status='pending'
                   ORDER BY m.id""",
                (school_data["id"],)
            ).fetchall()

    body = """
    {% if u['role'] == 'manager' %}
      <h2>مدرسه من — مدیریت</h2>

      {% if not school_data %}
        <h3>ساخت مدرسه</h3>
        <form method="post">
          <input type="hidden" name="action" value="create">
          <label>نام مدرسه</label>
          <input name="name" required minlength="2">
          <button type="submit">ساخت مدرسه</button>
        </form>
      {% else %}
        <div class="card">
          <h3>{{ school_data['name'] }}</h3>
          <p>کد پنج‌رقمی: <b>{{ school_data['code'] }}</b></p>
        </div>

        <h3>ساخت کلاس</h3>
        <form method="post" action="{{ url_for('add_class') }}">
          <label>نام کلاس</label>
          <input name="name" required>
          <button type="submit">افزودن کلاس</button>
        </form>

        <p><a href="{{ url_for('manage_notice') }}">مدیریت تابلو اطلاعیه</a></p>
        <p><a href="{{ url_for('manage_members') }}">مدیریت اعضا و کلاس‌ها</a></p>
        <p><a href="{{ url_for('manage_homework') }}">مدیریت مشق</a></p>
        <p><a href="{{ url_for('manage_exams') }}">مدیریت امتحان‌ها</a></p>

        <h3>کلاس‌ها</h3>
        {% for c in classes %}
          <div class="card">{{ c['name'] }}</div>
        {% else %}
          <p>هنوز کلاسی ساخته نشده است.</p>
        {% endfor %}

        <h3>درخواست‌های عضویت</h3>
        {% for r in requests %}
          <div class="card">
            {{ r['first_name'] }} {{ r['last_name'] }}
            <form method="post"
                  action="{{ url_for('review_member', membership_id=r['id']) }}">
              <button name="decision" value="approve">تأیید</button>
              <button name="decision" value="reject">رد</button>
            </form>
          </div>
        {% else %}
          <p>درخواست جدیدی وجود ندارد.</p>
        {% endfor %}

        <h3>دانش‌آموزان</h3>
        {% for s in students %}
          <div class="card">
            {{ s['first_name'] }} {{ s['last_name'] }}
            — وضعیت: {{ s['status'] }}
            — کلاس: {{ s['class_name'] or 'تعیین‌نشده' }}
          </div>
        {% else %}
          <p>هنوز دانش‌آموزی ثبت نشده است.</p>
        {% endfor %}
      {% endif %}

    {% else %}
      <h2>مدرسه من</h2>
      <h3>درخواست عضویت با کد مدرسه</h3>
      <form method="post">
        <input type="hidden" name="action" value="join">
        <label>کد پنج‌رقمی مدرسه</label>
        <input name="code" inputmode="numeric"
               pattern="[0-9]{5}" maxlength="5" required>
        <button type="submit">درخواست عضویت</button>
      </form>

      <h3>وضعیت درخواست‌ها</h3>
      {% for m in memberships %}
        <div class="card">
          {{ m['school_name'] }}
          — کد: {{ m['school_code'] }}
          — وضعیت: {{ m['status'] }}
        </div>
      {% else %}
        <p>هنوز درخواستی ثبت نکرده‌ای.</p>
      {% endfor %}
    {% endif %}
    """

    return page(
        "مدرسه من",
        body,
        u=u,
        school_data=school_data,
        memberships=memberships,
        classes=classes,
        students=students,
        requests=requests
    )
    # ==============================
# مدیریت کلاس‌ها و اعضای مدرسه
# ==============================

@app.route("/class/add", methods=["POST"])
@role_required("manager")
def add_class():
    u = current_user()
    name = request.form.get("name", "").strip()

    if not name or len(name) > 80:
        flash("نام کلاس را درست وارد کن.")
        return redirect(url_for("school"))

    with db_conn() as db:
        school_data = db.execute(
            "SELECT * FROM schools WHERE manager_id=?",
            (u["id"],)
        ).fetchone()

        if not school_data:
            flash("ابتدا مدرسه خودت را بساز.")
            return redirect(url_for("school"))

        try:
            db.execute(
                "INSERT INTO classes (school_id, name) VALUES (?, ?)",
                (school_data["id"], name)
            )
            flash("کلاس با موفقیت اضافه شد.")
        except sqlite3.IntegrityError:
            flash("این کلاس قبلاً ثبت شده است.")

    return redirect(url_for("school"))


# ==============================
# تأیید یا رد درخواست عضویت
# ==============================

@app.route("/member/review/<int:membership_id>", methods=["POST"])
@role_required("manager")
def review_member(membership_id):
    u = current_user()
    decision = request.form.get("decision", "")

    if decision not in ("approve", "reject"):
        abort(400)

    with db_conn() as db:
        school_data = db.execute(
            "SELECT * FROM schools WHERE manager_id=?",
            (u["id"],)
        ).fetchone()

        if not school_data:
            abort(403)

        member = db.execute(
            """SELECT * FROM memberships
               WHERE id=? AND school_id=?""",
            (membership_id, school_data["id"])
        ).fetchone()

        if not member:
            abort(404)

        if member["status"] != "pending":
            flash("این درخواست قبلاً بررسی شده است.")
            return redirect(url_for("school"))

        new_status = (
            "approved" if decision == "approve" else "rejected"
        )

        db.execute(
            "UPDATE memberships SET status=? WHERE id=?",
            (new_status, membership_id)
        )

    if decision == "approve":
        flash("عضویت دانش‌آموز تأیید شد.")
    else:
        flash("درخواست عضویت رد شد.")

    return redirect(url_for("school"))


# ==============================
# مدیریت اعضا و اختصاص کلاس
# ==============================

@app.route("/members/manage", methods=["GET", "POST"])
@role_required("manager")
def manage_members():
    u = current_user()

    with db_conn() as db:
        school_data = db.execute(
            "SELECT * FROM schools WHERE manager_id=?",
            (u["id"],)
        ).fetchone()

        if not school_data:
            return redirect(url_for("school"))

        school_id = school_data["id"]

        if request.method == "POST":
            action = request.form.get("action", "")
            membership_id = request.form.get(
                "membership_id", type=int
            )

            member = None

            if membership_id:
                member = db.execute(
                    """SELECT * FROM memberships
                       WHERE id=? AND school_id=?""",
                    (membership_id, school_id)
                ).fetchone()

            if action == "assign":
                class_id = request.form.get("class_id", type=int)

                if not member or member["status"] != "approved":
                    flash("عضو تأییدشده‌ای برای این کار پیدا نشد.")
                else:
                    valid_class = db.execute(
                        """SELECT id FROM classes
                           WHERE id=? AND school_id=?""",
                        (class_id, school_id)
                    ).fetchone()

                    if not valid_class:
                        flash("کلاس انتخاب‌شده معتبر نیست.")
                    else:
                        db.execute(
                            """UPDATE memberships
                               SET class_id=?
                               WHERE id=? AND school_id=?""",
                            (class_id, membership_id, school_id)
                        )
                        flash("کلاس دانش‌آموز تغییر کرد.")

            elif action == "remove":
                if not member:
                    flash("عضو پیدا نشد.")
                else:
                    db.execute(
                        "DELETE FROM memberships WHERE id=?",
                        (membership_id,)
                    )
                    flash("عضویت از مدرسه حذف شد.")

            else:
                flash("عملیات انتخاب‌شده معتبر نیست.")

        classes = db.execute(
            """SELECT * FROM classes
               WHERE school_id=?
               ORDER BY name""",
            (school_id,)
        ).fetchall()

        members = db.execute(
            """SELECT m.id AS membership_id,
                      m.status,
                      m.class_id,
                      u.first_name,
                      u.last_name,
                      u.phone,
                      c.name AS class_name
               FROM memberships m
               JOIN users u ON u.id=m.user_id
               LEFT JOIN classes c ON c.id=m.class_id
               WHERE m.school_id=?
               ORDER BY u.last_name, u.first_name""",
            (school_id,)
        ).fetchall()

    body = """
    <h2>مدیریت اعضای مدرسه</h2>

    <h3>اعضا</h3>

    {% for m in members %}
      <div class="card">
        <b>{{ m['first_name'] }} {{ m['last_name'] }}</b>
        <p>شماره تلفن: {{ m['phone'] }}</p>
        <p>وضعیت عضویت: {{ m['status'] }}</p>
        <p>کلاس: {{ m['class_name'] or 'تعیین نشده' }}</p>

        {% if m['status'] == 'approved' %}
          {% if classes %}
            <form method="post">
              <input type="hidden"
                     name="membership_id"
                     value="{{ m['membership_id'] }}">

              <input type="hidden"
                     name="action"
                     value="assign">

              <label>انتخاب کلاس</label>
              <select name="class_id" required>
                {% for c in classes %}
                  <option value="{{ c['id'] }}"
                    {% if c['id'] == m['class_id'] %}
                      selected
                    {% endif %}>
                    {{ c['name'] }}
                  </option>
                {% endfor %}
              </select>

              <button type="submit">ثبت کلاس</button>
            </form>
          {% endif %}
        {% endif %}

        <form method="post"
              onsubmit="return confirm('از حذف عضویت مطمئنی؟')">
          <input type="hidden"
                 name="membership_id"
                 value="{{ m['membership_id'] }}">

          <input type="hidden"
                 name="action"
                 value="remove">

          <button type="submit">حذف عضویت</button>
        </form>
      </div>
    {% else %}
      <p>هنوز عضوی ثبت نشده است.</p>
    {% endfor %}

    <p><a href="{{ url_for('school') }}">بازگشت به مدرسه من</a></p>
    """

    return page(
        "مدیریت اعضا",
        body,
        members=members,
        classes=classes
    )


# ==============================
# تابلو اطلاعیه مدرسه
# ==============================

@app.route("/notice/manage", methods=["GET", "POST"])
@role_required("manager")
def manage_notice():
    u = current_user()

    with db_conn() as db:
        school_data = db.execute(
            "SELECT * FROM schools WHERE manager_id=?",
            (u["id"],)
        ).fetchone()

        if not school_data:
            return redirect(url_for("school"))

        school_id = school_data["id"]

        if request.method == "POST":
            title = request.form.get("title", "").strip()
            notice_body = request.form.get("body", "").strip()

            if not title or not notice_body:
                flash("عنوان و متن اطلاعیه را وارد کن.")
                return redirect(url_for("manage_notice"))

            if len(title) > 150 or len(notice_body) > 5000:
                flash("عنوان یا متن اطلاعیه بیش از حد طولانی است.")
                return redirect(url_for("manage_notice"))

            try:
                image_name = save_upload(
                    request.files.get("image")
                )
            except ValueError as exc:
                flash(str(exc))
                return redirect(url_for("manage_notice"))

            db.execute(
                """INSERT INTO notices
                   (school_id, author_id, title, body,
                    image_path, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    school_id,
                    u["id"],
                    title,
                    notice_body,
                    image_name,
                    datetime.now().isoformat()
                )
            )

            flash("اطلاعیه منتشر شد.")
            return redirect(url_for("manage_notice"))

        notices = db.execute(
            """SELECT * FROM notices
               WHERE school_id=?
               ORDER BY id DESC""",
            (school_id,)
        ).fetchall()

    body = """
    <h2>مدیریت تابلو اطلاعیه</h2>

    <form method="post" enctype="multipart/form-data">
      <label>عنوان اطلاعیه</label>
      <input name="title" maxlength="150" required>

      <label>متن اطلاعیه</label>
      <textarea name="body" maxlength="5000" required></textarea>

      <label>تصویر اطلاعیه (اختیاری)</label>
      <input type="file"
             name="image"
             accept="image/png,image/jpeg,image/webp,image/gif">

      <button type="submit">انتشار اطلاعیه</button>
    </form>

    <h3>اطلاعیه‌های منتشرشده</h3>

    {% for n in notices %}
      <div class="card">
        <b>{{ n['title'] }}</b>
        <p>{{ n['body'] }}</p>

        {% if n['image_path'] %}
          <img
            src="{{ url_for('uploaded_file', filename=n['image_path']) }}"
            alt="تصویر اطلاعیه"
            style="max-width:100%;height:auto">
        {% endif %}

        <form method="post"
              action="{{ url_for('delete_notice', notice_id=n['id']) }}">
          <button type="submit">حذف اطلاعیه</button>
        </form>
      </div>
    {% else %}
      <p>هنوز اطلاعیه‌ای منتشر نشده است.</p>
    {% endfor %}

    <p><a href="{{ url_for('school') }}">بازگشت</a></p>
    """

    return page(
        "مدیریت اطلاعیه",
        body,
        notices=notices
    )


# ==============================
# حذف اطلاعیه
# ==============================

@app.route("/notice/delete/<int:notice_id>", methods=["POST"])
@role_required("manager")
def delete_notice(notice_id):
    u = current_user()

    with db_conn() as db:
        school_data = db.execute(
            "SELECT id FROM schools WHERE manager_id=?",
            (u["id"],)
        ).fetchone()

        if not school_data:
            abort(403)

        notice = db.execute(
            """SELECT id FROM notices
               WHERE id=? AND school_id=?""",
            (notice_id, school_data["id"])
        ).fetchone()

        if not notice:
            abort(404)

        db.execute(
            "DELETE FROM notices WHERE id=?",
            (notice_id,)
        )

    flash("اطلاعیه حذف شد.")
    return redirect(url_for("manage_notice"))


# ==============================
# نمایش امن فایل‌های آپلودشده
# ==============================

@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    from flask import send_from_directory

    filename = os.path.basename(filename)

    if not filename:
        abort(404)

    return send_from_directory(
        str(UPLOAD_DIR),
        filename,
        as_attachment=False
        )
    # ==============================
# بخش مشق و تکالیف
# ==============================

@app.route("/homework", methods=["GET", "POST"])
@login_required
def manage_homework():
    u = current_user()
    school_data = school_for_user(u)

    if not school_data:
        flash("ابتدا باید وارد مدرسه شوی.")
        return redirect(url_for("school"))

    if u["role"] not in ("teacher", "student", "manager"):
        abort(403)

    if request.method == "POST":
        action = request.form.get("action", "").strip()

        # معلم مشق جدید ثبت می‌کند.
        if action == "create":
            if u["role"] != "teacher":
                abort(403)

            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            due_at = request.form.get("due_at", "").strip() or None

            if not title or not description:
                flash("عنوان و توضیحات مشق را وارد کن.")
                return redirect(url_for("manage_homework"))

            if len(title) > 150 or len(description) > 5000:
                flash("عنوان یا توضیحات بیش از حد طولانی است.")
                return redirect(url_for("manage_homework"))

            with db_conn() as db:
                db.execute(
                    """INSERT INTO homework
                       (school_id, teacher_id, title, description, due_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        school_data["id"],
                        u["id"],
                        title,
                        description,
                        due_at
                    )
                )

            flash("مشق با موفقیت ثبت شد.")
            return redirect(url_for("manage_homework"))

        # دانش‌آموز پاسخ مشق را ارسال می‌کند.
        elif action == "submit":
            if u["role"] != "student":
                abort(403)

            homework_id = request.form.get("homework_id", type=int)
            answer = request.form.get("answer", "").strip()

            try:
                attachment = save_upload(
                    request.files.get("attachment")
                )
            except ValueError as exc:
                flash(str(exc))
                return redirect(url_for("manage_homework"))

            if not homework_id:
                flash("مشق انتخاب‌شده معتبر نیست.")
                return redirect(url_for("manage_homework"))

            with db_conn() as db:
                membership = db.execute(
                    """SELECT id FROM memberships
                       WHERE user_id=? AND school_id=?
                       AND status='approved'""",
                    (u["id"], school_data["id"])
                ).fetchone()

                task = db.execute(
                    """SELECT id FROM homework
                       WHERE id=? AND school_id=?""",
                    (homework_id, school_data["id"])
                ).fetchone()

                if not membership:
                    flash("عضویت شما در مدرسه هنوز تأیید نشده است.")
                elif not task:
                    flash("این مشق در مدرسه شما وجود ندارد.")
                elif not answer and not attachment:
                    flash("پاسخ متنی یا فایل پیوست وارد کن.")
                else:
                    db.execute(
                        """INSERT INTO submissions
                           (homework_id, student_id, answer, file_path)
                           VALUES (?, ?, ?, ?)
                           ON CONFLICT(homework_id, student_id)
                           DO UPDATE SET
                               answer=excluded.answer,
                               file_path=COALESCE(
                                   excluded.file_path,
                                   submissions.file_path
                               ),
                               created_at=CURRENT_TIMESTAMP""",
                        (
                            homework_id,
                            u["id"],
                            answer,
                            attachment
                        )
                    )

                    flash("پاسخ مشق ارسال شد.")

            return redirect(url_for("manage_homework"))

    # دریافت مشق‌های مدرسه
    with db_conn() as db:
        tasks = db.execute(
            """SELECT h.*, u.first_name, u.last_name
               FROM homework h
               JOIN users u ON u.id=h.teacher_id
               WHERE h.school_id=?
               ORDER BY h.id DESC""",
            (school_data["id"],)
        ).fetchall()

        # پاسخ‌ها فقط برای معلم نمایش داده می‌شوند.
        if u["role"] == "teacher":
            submissions = db.execute(
                """SELECT s.*, u.first_name, u.last_name
                   FROM submissions s
                   JOIN users u ON u.id=s.student_id
                   JOIN homework h ON h.id=s.homework_id
                   WHERE h.school_id=?
                     AND h.teacher_id=?
                   ORDER BY s.id DESC""",
                (school_data["id"], u["id"])
            ).fetchall()
        else:
            submissions = []

        # پاسخ‌های قبلی دانش‌آموز
        if u["role"] == "student":
            mine = db.execute(
                """SELECT s.*
                   FROM submissions s
                   JOIN homework h ON h.id=s.homework_id
                   WHERE s.student_id=? AND h.school_id=?""",
                (u["id"], school_data["id"])
            ).fetchall()
        else:
            mine = []

    mine_map = {
        row["homework_id"]: row
        for row in mine
    }

    body = """
    <h2>مشق و تکالیف</h2>

    {% if u['role'] == 'teacher' %}
      <div class="card">
        <h3>ثبت مشق جدید</h3>

        <form method="post">
          <input type="hidden" name="action" value="create">

          <label>عنوان مشق</label>
          <input name="title" maxlength="150" required>

          <label>توضیحات مشق</label>
          <textarea name="description"
                    maxlength="5000"
                    required></textarea>

          <label>مهلت تحویل (اختیاری)</label>
          <input type="datetime-local" name="due_at">

          <button type="submit">ثبت مشق</button>
        </form>
      </div>
    {% endif %}

    <h3>فهرست مشق‌ها</h3>

    {% for t in tasks %}
      <div class="card">
        <h3>{{ t['title'] }}</h3>
        <p style="white-space:pre-wrap">{{ t['description'] }}</p>

        <small>
          معلم: {{ t['first_name'] }} {{ t['last_name'] }}
        </small>

        <p>
          مهلت تحویل:
          {{ t['due_at'] or 'تعیین نشده' }}
        </p>

        {% if u['role'] == 'student' %}
          <form method="post" enctype="multipart/form-data">
            <input type="hidden" name="action" value="submit">
            <input type="hidden"
                   name="homework_id"
                   value="{{ t['id'] }}">

            <label>پاسخ متنی</label>
            <textarea name="answer">{{ mine_map[t['id']]['answer'] if t['id'] in mine_map else '' }}</textarea>

            <label>پیوست عکس یا فایل صوتی (اختیاری)</label>
            <input type="file"
                   name="attachment"
                   accept="image/*,audio/*">

            <button type="submit">ارسال پاسخ</button>
          </form>

          {% if t['id'] in mine_map %}
            <p>برای این مشق قبلاً پاسخ ارسال کرده‌ای.</p>
          {% endif %}
        {% endif %}

        {% if u['role'] == 'teacher' %}
          <h4>پاسخ‌های دانش‌آموزان</h4>

          {% for s in submissions if s['homework_id'] == t['id'] %}
            <div class="card">
              <b>{{ s['first_name'] }} {{ s['last_name'] }}</b>
              <p style="white-space:pre-wrap">{{ s['answer'] or 'پاسخ متنی ندارد.' }}</p>

              {% if s['file_path'] %}
                <p>
                  <a href="{{ url_for('uploaded_file', filename=s['file_path']) }}">
                    مشاهده فایل پیوست
                  </a>
                </p>
              {% endif %}

              <small>زمان ارسال: {{ s['created_at'] }}</small>
            </div>
          {% else %}
            <p>هنوز پاسخی ارسال نشده است.</p>
          {% endfor %}
        {% endif %}
      </div>
    {% else %}
      <p>هنوز مشقی ثبت نشده است.</p>
    {% endfor %}

    <p><a href="{{ url_for('school') }}">بازگشت به مدرسه من</a></p>
    """

    return page(
        "مشق و تکالیف",
        body,
        u=u,
        tasks=tasks,
        submissions=submissions,
        mine_map=mine_map
                    )
