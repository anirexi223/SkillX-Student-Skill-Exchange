from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash
import os, uuid, threading
from functools import wraps
from datetime import datetime
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE, ".env"))
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "skillx-dev-secret-change-me")
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
_schema_lock = threading.Lock()
_schema_ready = False

CATEGORIES = [
    ("Programming","💻"),("Design","🎨"),("Languages","🌐"),("Music","🎵"),
    ("Cooking","👨‍🍳"),("Photography","📷"),("Business","💼"),("Writing","✍️"),
    ("Mathematics","🧮"),("Science","🧪")
]

SCHEMA_SQL = r"""
CREATE TABLE IF NOT EXISTS profiles(
  id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, full_name TEXT NOT NULL DEFAULT '',
  email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user',
  bio TEXT NOT NULL DEFAULT '', avatar_url TEXT NOT NULL DEFAULT '',
  is_active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS categories(id TEXT PRIMARY KEY,name TEXT UNIQUE NOT NULL,icon TEXT NOT NULL DEFAULT '📚',created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS skills(
  id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  name TEXT NOT NULL,category_id TEXT REFERENCES categories(id) ON DELETE SET NULL,
  level TEXT NOT NULL DEFAULT 'Beginner',description TEXT NOT NULL DEFAULT '',created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS exchange_requests(
  id TEXT PRIMARY KEY,sender_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  receiver_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  skill_to_learn_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
  skill_offered_id TEXT REFERENCES skills(id) ON DELETE SET NULL,message TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending',created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS sessions(
  id TEXT PRIMARY KEY,request_id TEXT REFERENCES exchange_requests(id) ON DELETE SET NULL,
  requester_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  teacher_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  skill_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
  date TEXT NOT NULL,time TEXT NOT NULL,duration INTEGER NOT NULL DEFAULT 60,
  mode TEXT NOT NULL DEFAULT 'Online',notes TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'upcoming',created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS messages(
  id TEXT PRIMARY KEY,sender_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  receiver_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,content TEXT NOT NULL,
  read BOOLEAN NOT NULL DEFAULT FALSE,created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS reviews(
  id TEXT PRIMARY KEY,reviewer_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  reviewed_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
  skill_id TEXT REFERENCES skills(id) ON DELETE SET NULL,rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
  review TEXT NOT NULL DEFAULT '',created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS notifications(
  id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,type TEXT NOT NULL DEFAULT 'general',
  title TEXT NOT NULL DEFAULT '',message TEXT NOT NULL DEFAULT '',is_read BOOLEAN NOT NULL DEFAULT FALSE,
  related_id TEXT,created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS ai_history(
  id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  feature TEXT NOT NULL,input_text TEXT NOT NULL DEFAULT '',output_text TEXT NOT NULL DEFAULT '',created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP);
"""

def uid(): return str(uuid.uuid4())

def _create_pool():
    if not psycopg or not dict_row:
        raise RuntimeError("psycopg is not installed. Run: pip install -r requirements.txt")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is missing. Add your Supabase PostgreSQL connection string to .env")
    return ConnectionPool(
        conninfo=DATABASE_URL,
        min_size=0,
        max_size=5,
        timeout=10,
        kwargs={"row_factory": dict_row},
        open=True,
    )


DB_POOL = _create_pool()


def q(sql, args=(), one=False):
    with DB_POOL.connection() as db:
        with db.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchone() if one else cur.fetchall()


def execsql(sql, args=()):
    with DB_POOL.connection() as db:
        with db.cursor() as cur:
            cur.execute(sql, args)
            row = cur.fetchone() if cur.description else None
        db.commit()
        return row


def init_db():
    global _schema_ready
    if _schema_ready:
        return

    with _schema_lock:
        if _schema_ready:
            return

        with DB_POOL.connection() as db:
            with db.cursor() as cur:
                cur.execute(SCHEMA_SQL)

                for name, icon in CATEGORIES:
                    cur.execute(
                        "INSERT INTO categories(id,name,icon) VALUES(%s,%s,%s) "
                        "ON CONFLICT(name) DO NOTHING",
                        (uid(), name, icon),
                    )

                users = [
                    ("a0000000-0000-0000-0000-000000000001","Admin","System Administrator","admin@skillx.edu","Admin@1234","admin","Platform administrator with full access to manage the Skill Exchange Platform."),
                    ("a0000000-0000-0000-0000-000000000010","sarah_chen","Sarah Chen","sarah@skillx.edu","password123","user","Computer Science major passionate about web development and teaching others."),
                    ("a0000000-0000-0000-0000-000000000011","marcus_j","Marcus Johnson","marcus@skillx.edu","password123","user","Graphic designer and digital artist. Love sharing creative skills with fellow students."),
                    ("a0000000-0000-0000-0000-000000000012","aria_patel","Aria Patel","aria@skillx.edu","password123","user","Music and language enthusiast. Fluent in 3 languages and counting!"),
                    ("a0000000-0000-0000-0000-000000000013","diego_r","Diego Ramirez","diego@skillx.edu","password123","user","Business student and amateur photographer. Always learning new things."),
                    ("a0000000-0000-0000-0000-000000000014","emma_w","Emma Wilson","emma@skillx.edu","password123","user","Mathematics and physics tutor. Love making complex topics simple."),
                    ("a0000000-0000-0000-0000-000000000015","liam_k","Liam Kim","liam@skillx.edu","password123","user","Writer and cooking enthusiast. Believes good food brings people together."),
                ]

                for u in users:
                    cur.execute(
                        """INSERT INTO profiles
                           (id,username,full_name,email,password_hash,role,bio)
                           VALUES(%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT(username) DO NOTHING""",
                        (u[0], u[1], u[2], u[3], generate_password_hash(u[4]), u[5], u[6]),
                    )

                skill_data = [
                    ("sarah_chen","React Development","Programming","Advanced","Learn modern React with hooks, context, and state management."),
                    ("sarah_chen","Python Programming","Programming","Intermediate","Python fundamentals including data structures, OOP, and pandas."),
                    ("sarah_chen","Git & Version Control","Programming","Beginner","Master Git workflows, branching, merging, and collaboration."),
                    ("marcus_j","UI/UX Design","Design","Advanced","User-centered design, wireframing, prototyping, and Figma."),
                    ("marcus_j","Photoshop Basics","Design","Intermediate","Photo editing, digital art creation, and design fundamentals."),
                    ("marcus_j","Logo Design","Design","Intermediate","Create memorable logos from concept to final vector design."),
                    ("aria_patel","Spanish Language","Languages","Advanced","Conversational Spanish, grammar, vocabulary, and culture."),
                    ("aria_patel","Piano Lessons","Music","Intermediate","Learn piano basics, sheet music, and favorite songs."),
                    ("aria_patel","French Language","Languages","Intermediate","French conversation, grammar, and pronunciation."),
                    ("diego_r","Photography Fundamentals","Photography","Intermediate","Composition, lighting, and camera settings."),
                    ("diego_r","Digital Marketing","Business","Beginner","Social media marketing, SEO basics, and content strategy."),
                    ("emma_w","Calculus","Mathematics","Advanced","Limits, derivatives, and integrals with real-world examples."),
                    ("emma_w","Linear Algebra","Mathematics","Intermediate","Vectors, matrices, eigenvalues, and data science applications."),
                    ("emma_w","Physics Mechanics","Science","Intermediate","Motion, forces, energy, and momentum."),
                    ("liam_k","Creative Writing","Writing","Intermediate","Storytelling, character development, and finding your voice."),
                    ("liam_k","Italian Cooking","Cooking","Beginner","Authentic pasta, risotto, and Italian dishes from scratch."),
                ]

                for username, name, cat, level, desc in skill_data:
                    cur.execute("SELECT id FROM profiles WHERE username=%s", (username,))
                    user = cur.fetchone()
                    cur.execute("SELECT id FROM categories WHERE name=%s", (cat,))
                    category = cur.fetchone()

                    if user and category:
                        cur.execute(
                            "SELECT 1 FROM skills WHERE user_id=%s AND name=%s",
                            (user["id"], name),
                        )
                        if not cur.fetchone():
                            cur.execute(
                                """INSERT INTO skills
                                   (id,user_id,name,category_id,level,description)
                                   VALUES(%s,%s,%s,%s,%s,%s)""",
                                (uid(), user["id"], name, category["id"], level, desc),
                            )

            db.commit()

        _schema_ready = True


@app.before_request
def load_current_user():
    g.current_user = None
    g.unread = 0

    uid_ = session.get("uid")
    if not uid_:
        return

    row = q(
        """SELECT p.*,
                  (SELECT COUNT(*)
                   FROM notifications n
                   WHERE n.user_id = p.id
                     AND n.is_read = FALSE) AS unread_count
           FROM profiles p
           WHERE p.id = %s""",
        (uid_,),
        one=True,
    )

    if row:
        g.current_user = row
        g.unread = row["unread_count"]


@app.context_processor
def inject():
    return {
        "current_user": g.current_user,
        "unread": g.unread,
    }


def login_required(f):
    @wraps(f)
    def w(*a, **kw):
        if not session.get("uid"):
            return redirect(url_for("login", next=request.path))

        u = g.current_user
        if not u or not u["is_active"]:
            session.clear()
            return redirect(url_for("login"))

        return f(*a, **kw)

    return w


def admin_required(f):
    @wraps(f)
    def w(*a, **kw):
        if not session.get("uid"):
            return redirect(url_for("admin_login"))

        u = g.current_user
        if not u or u["role"] != "admin":
            abort(403)

        return f(*a, **kw)

    return w


def notify(user_id,title,message,typ="general",related=None):
    execsql("INSERT INTO notifications(id,user_id,type,title,message,related_id) VALUES(%s,%s,%s,%s,%s,%s)",(uid(),user_id,typ,title,message,related))

def ai_save(feature,input_text,output_text):
    try:
        execsql("INSERT INTO ai_history(id,user_id,feature,input_text,output_text) VALUES(%s,%s,%s,%s,%s)",(uid(),session.get('uid'),feature,input_text[:4000],output_text[:8000]))
    except Exception:
        pass

@app.route("/")
def splash(): return render_template("splash.html")

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        ident=request.form.get("email","").strip()
        pw=request.form.get("password","")
        u=q("SELECT * FROM profiles WHERE email=%s OR username=%s",(ident,ident),one=True)
        if u and u["role"]=="user" and u["is_active"] and check_password_hash(u["password_hash"],pw):
            session["uid"]=u["id"]; return redirect(request.form.get("next") or url_for("dashboard"))
        flash("Invalid credentials or inactive account.","error")
    return render_template("auth.html",mode="login")

@app.route("/register",methods=["GET","POST"])
def register():
    if request.method=="POST":
        username=request.form["username"].strip(); name=request.form["full_name"].strip(); email=request.form["email"].strip().lower(); pw=request.form["password"]
        if len(pw)<6: flash("Password must be at least 6 characters.","error")
        elif q("SELECT 1 FROM profiles WHERE username=%s OR email=%s",(username,email),one=True): flash("Username or email already exists.","error")
        else:
            id=uid(); execsql("INSERT INTO profiles(id,username,full_name,email,password_hash) VALUES(%s,%s,%s,%s,%s)",(id,username,name,email,generate_password_hash(pw)))
            session["uid"]=id; flash("Account created successfully.","success"); return redirect(url_for("dashboard"))
    return render_template("auth.html",mode="register")

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("splash"))

@app.route("/admin/login",methods=["GET","POST"])
def admin_login():
    if request.method=="POST":
        u=q("SELECT * FROM profiles WHERE email=%s AND role='admin'",(request.form["email"].strip(),),one=True)
        if u and check_password_hash(u["password_hash"],request.form["password"]):
            session["uid"]=u["id"]; return redirect(url_for("admin_dashboard"))
        flash("Invalid admin credentials.","error")
    return render_template("auth.html",mode="admin")

@app.route("/dashboard")
@login_required
def dashboard():
    uid_=session["uid"]
    skills=q("SELECT s.*,c.name category FROM skills s LEFT JOIN categories c ON c.id=s.category_id WHERE s.user_id=%s ORDER BY s.created_at DESC",(uid_,))
    sessions=q("""SELECT se.*,sk.name skill,p.full_name teacher_name FROM sessions se JOIN skills sk ON sk.id=se.skill_id
                  JOIN profiles p ON p.id=se.teacher_id WHERE se.requester_id=%s OR se.teacher_id=%s ORDER BY se.date,se.time""",(uid_,uid_))
    reviews=q("""SELECT r.*,p.full_name reviewer_name,sk.name skill FROM reviews r JOIN profiles p ON p.id=r.reviewer_id
                 LEFT JOIN skills sk ON sk.id=r.skill_id WHERE r.reviewed_id=%s ORDER BY r.created_at DESC""",(uid_,))
    avg=round(sum(r["rating"] for r in reviews)/len(reviews),1) if reviews else 0
    return render_template("dashboard.html",skills=skills,sessions=sessions,reviews=reviews,avg=avg)

@app.route("/explore")
@login_required
def explore():
    search=request.args.get("q","").strip(); cat=request.args.get("category","")
    sql="""SELECT s.*,p.username,p.full_name,p.bio,c.name category,c.icon FROM skills s
           JOIN profiles p ON p.id=s.user_id LEFT JOIN categories c ON c.id=s.category_id WHERE p.is_active=TRUE"""
    args=[]
    if search: sql+=" AND (s.name LIKE %s OR p.full_name LIKE %s OR s.description LIKE %s)"; args += [f"%{search}%"]*3
    if cat: sql+=" AND c.name=%s"; args.append(cat)
    sql+=" ORDER BY s.created_at DESC"
    skills=q(sql,args); cats=q("SELECT * FROM categories ORDER BY name")
    return render_template("explore.html",skills=skills,categories=cats,search=search,cat=cat)

@app.route("/skills/add",methods=["POST"])
@login_required
def add_skill():
    cat=q("SELECT id FROM categories WHERE id=%s",(request.form["category_id"],),one=True)
    if not cat: flash("Invalid category.","error")
    else:
        execsql("INSERT INTO skills(id,user_id,name,category_id,level,description) VALUES(%s,%s,%s,%s,%s,%s)",(uid(),session["uid"],request.form["name"].strip(),cat["id"],request.form["level"],request.form.get("description","").strip()))
        flash("Skill added.","success")
    return redirect(request.referrer or url_for("my_skills"))

@app.post("/skills/<id>/delete")
@login_required
def delete_skill(id):
    s=q("SELECT * FROM skills WHERE id=%s AND user_id=%s",(id,session["uid"]),one=True)
    if not s: abort(404)
    execsql("DELETE FROM skills WHERE id=%s",(id,)); flash("Skill deleted.","success")
    return redirect(url_for("my_skills"))

@app.post("/skills/<id>/edit")
@login_required
def edit_skill(id):
    s=q("SELECT * FROM skills WHERE id=%s AND user_id=%s",(id,session["uid"]),one=True)
    if not s: abort(404)
    execsql("UPDATE skills SET name=%s,category_id=%s,level=%s,description=%s WHERE id=%s",
            (request.form["name"].strip(),request.form.get("category_id") or None,request.form["level"],request.form.get("description","").strip(),id))
    flash("Skill updated.","success"); return redirect(url_for("my_skills"))

@app.route("/my-skills")
@login_required
def my_skills():
    skills=q("SELECT s.*,c.name category,c.icon FROM skills s LEFT JOIN categories c ON c.id=s.category_id WHERE s.user_id=%s ORDER BY s.created_at DESC",(session["uid"],))
    return render_template("my_skills.html",skills=skills,categories=q("SELECT * FROM categories ORDER BY name"))

@app.route("/skills/<id>")
@login_required
def skill_details(id):
    s=q("""SELECT s.*,p.full_name,p.username,p.bio,p.avatar_url,c.name category,c.icon FROM skills s JOIN profiles p ON p.id=s.user_id
           LEFT JOIN categories c ON c.id=s.category_id WHERE s.id=%s""",(id,),one=True)
    if not s: abort(404)
    own=q("SELECT * FROM skills WHERE user_id=%s AND id!=%s",(session["uid"],id))
    return render_template("skill_details.html",skill=s,my_skills=own)

@app.route("/requests",methods=["GET","POST"])
@login_required
def requests_page():
    uid_=session["uid"]
    if request.method=="POST":
        skill=q("SELECT * FROM skills WHERE id=%s",(request.form["skill_to_learn_id"],),one=True)
        if skill and skill["user_id"]!=uid_:
            rid=uid(); execsql("""INSERT INTO exchange_requests(id,sender_id,receiver_id,skill_to_learn_id,skill_offered_id,message)
                 VALUES(%s,%s,%s,%s,%s,%s)""",(rid,uid_,skill["user_id"],skill["id"],request.form.get("skill_offered_id") or None,request.form.get("message","")))
            notify(skill["user_id"],"New exchange request",f"{current_name()} wants to learn {skill['name']}.","request",rid)
            flash("Exchange request sent.","success")
        else: flash("Invalid skill selection.","error")
        return redirect(url_for("requests_page"))
    sent=q("""SELECT r.*,p.full_name receiver_name,st.name learn_skill,so.name offered_skill FROM exchange_requests r
              JOIN profiles p ON p.id=r.receiver_id JOIN skills st ON st.id=r.skill_to_learn_id
              LEFT JOIN skills so ON so.id=r.skill_offered_id WHERE r.sender_id=%s ORDER BY r.created_at DESC""",(uid_,))
    received=q("""SELECT r.*,p.full_name sender_name,st.name learn_skill,so.name offered_skill FROM exchange_requests r
              JOIN profiles p ON p.id=r.sender_id JOIN skills st ON st.id=r.skill_to_learn_id
              LEFT JOIN skills so ON so.id=r.skill_offered_id WHERE r.receiver_id=%s ORDER BY r.created_at DESC""",(uid_,))
    mine=q("SELECT * FROM skills WHERE user_id=%s",(uid_,))
    return render_template("requests.html",sent=sent,received=received,my_skills=mine)

def current_name():
    u = g.current_user
    return u["full_name"] if u else "A user"

@app.post("/requests/<id>/<action>")
@login_required
def request_action(id,action):
    r=q("SELECT * FROM exchange_requests WHERE id=%s",(id,),one=True)
    if not r or (session["uid"] not in (r["sender_id"],r["receiver_id"])): abort(403)
    if action not in ("accepted","rejected","completed"): abort(400)
    execsql("UPDATE exchange_requests SET status=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s",(action,id))
    other=r["sender_id"] if session["uid"]==r["receiver_id"] else r["receiver_id"]
    notify(other,f"Request {action}",f"Your exchange request is now {action}.","request",id)
    flash(f"Request {action}.","success"); return redirect(url_for("requests_page"))

@app.route("/schedule/<request_id>",methods=["GET","POST"])
@login_required
def schedule(request_id):
    r=q("SELECT * FROM exchange_requests WHERE id=%s AND (sender_id=%s OR receiver_id=%s)",(request_id,session["uid"],session["uid"]),one=True)
    if not r: abort(404)
    skill=q("SELECT * FROM skills WHERE id=%s",(r["skill_to_learn_id"],),one=True)
    if request.method=="POST":
        sid=uid(); execsql("""INSERT INTO sessions(id,request_id,requester_id,teacher_id,skill_id,date,time,duration,mode,notes)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",(sid,request_id,r["sender_id"],r["receiver_id"],skill["id"],request.form["date"],request.form["time"],int(request.form["duration"]),request.form["mode"],request.form.get("notes","")))
        notify(r["receiver_id"],"Session scheduled",f"A session for {skill['name']} was scheduled.","session",sid)
        flash("Session scheduled.","success"); return redirect(url_for("sessions"))
    return render_template("schedule.html",req=r,skill=skill)

@app.route("/sessions")
@login_required
def sessions():
    rows=q("""SELECT se.*,sk.name skill,p1.full_name requester_name,p2.full_name teacher_name FROM sessions se
              JOIN skills sk ON sk.id=se.skill_id JOIN profiles p1 ON p1.id=se.requester_id JOIN profiles p2 ON p2.id=se.teacher_id
              WHERE se.requester_id=%s OR se.teacher_id=%s ORDER BY se.date,se.time""",(session["uid"],session["uid"]))
    return render_template("sessions.html",sessions=rows)

@app.post("/sessions/<id>/status/<status>")
@login_required
def session_status(id,status):
    se=q("SELECT * FROM sessions WHERE id=%s AND (requester_id=%s OR teacher_id=%s)",(id,session["uid"],session["uid"]),one=True)
    if not se: abort(404)
    if status not in ("ongoing","completed","cancelled"): abort(400)
    execsql("UPDATE sessions SET status=%s WHERE id=%s",(status,id)); flash("Session updated.","success")
    return redirect(request.referrer or url_for("sessions"))

@app.route("/sessions/<id>")
@login_required
def ongoing(id):
    se=q("""SELECT se.*,sk.name skill,p1.full_name requester_name,p2.full_name teacher_name FROM sessions se
            JOIN skills sk ON sk.id=se.skill_id JOIN profiles p1 ON p1.id=se.requester_id JOIN profiles p2 ON p2.id=se.teacher_id
            WHERE se.id=%s AND (se.requester_id=%s OR se.teacher_id=%s)""",(id,session["uid"],session["uid"]),one=True)
    if not se: abort(404)
    return render_template("ongoing.html",item=se)

@app.route("/review/<id>",methods=["GET","POST"])
@login_required
def review(id):
    se=q("SELECT * FROM sessions WHERE id=%s AND (requester_id=%s OR teacher_id=%s)",(id,session["uid"],session["uid"]),one=True)
    if not se: abort(404)
    reviewed=se["teacher_id"] if session["uid"]==se["requester_id"] else se["requester_id"]
    if request.method=="POST":
        execsql("INSERT INTO reviews(id,reviewer_id,reviewed_id,session_id,skill_id,rating,review) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (uid(),session["uid"],reviewed,id,se["skill_id"],int(request.form["rating"]),request.form.get("review","")))
        notify(reviewed,"New review","You received a new session review.","review",id)
        flash("Review submitted.","success"); return redirect(url_for("sessions"))
    return render_template("review.html",item=se)

@app.route("/messages",methods=["GET","POST"])
@login_required
def messages():
    uid_=session["uid"]; to=request.args.get("to","")
    if request.method=="POST":
        receiver=request.form["receiver_id"]; content=request.form["content"].strip()
        if content: execsql("INSERT INTO messages(id,sender_id,receiver_id,content) VALUES(%s,%s,%s,%s)",(uid(),receiver,content)); notify(receiver,"New message",f"{current_name()} sent you a message.","message")
        return redirect(url_for("messages",to=receiver))
    users=q("SELECT * FROM profiles WHERE id!=%s AND is_active=TRUE ORDER BY full_name",(uid_,))
    if not to and users: to=users[0]["id"]
    thread=q("""SELECT m.*,p.full_name sender_name FROM messages m JOIN profiles p ON p.id=m.sender_id
                WHERE (m.sender_id=%s AND m.receiver_id=%s) OR (m.sender_id=%s AND m.receiver_id=%s) ORDER BY m.created_at""",(uid_,to,to,uid_)) if to else []
    if to: execsql("UPDATE messages SET read=TRUE WHERE receiver_id=%s AND sender_id=%s",(uid_,to))
    return render_template("messages.html",users=users,thread=thread,to=to)

@app.route("/profile")
@app.route("/users/<id>")
@login_required
def profile(id=None):
    id=id or session["uid"]; u=q("SELECT * FROM profiles WHERE id=%s",(id,),one=True)
    if not u: abort(404)
    skills=q("SELECT s.*,c.name category FROM skills s LEFT JOIN categories c ON c.id=s.category_id WHERE s.user_id=%s",(id,))
    reviews=q("""SELECT r.*,p.full_name reviewer_name FROM reviews r JOIN profiles p ON p.id=r.reviewer_id WHERE r.reviewed_id=%s ORDER BY r.created_at DESC""",(id,))
    return render_template("profile.html",profile=u,skills=skills,reviews=reviews,own=(id==session["uid"]))

@app.post("/profile/update")
@login_required
def profile_update():
    execsql("UPDATE profiles SET full_name=%s,bio=%s,avatar_url=%s WHERE id=%s",(request.form["full_name"],request.form.get("bio",""),request.form.get("avatar_url",""),session["uid"]))
    flash("Profile updated.","success"); return redirect(url_for("profile"))

@app.route("/settings",methods=["GET","POST"])
@login_required
def settings():
    if request.method=="POST":
        old=request.form["old_password"]; new=request.form["new_password"]; u=q("SELECT * FROM profiles WHERE id=%s",(session["uid"],),one=True)
        if not check_password_hash(u["password_hash"],old): flash("Current password is incorrect.","error")
        elif len(new)<6: flash("New password must be at least 6 characters.","error")
        else: execsql("UPDATE profiles SET password_hash=%s WHERE id=%s",(generate_password_hash(new),session["uid"])); flash("Password changed.","success")
    return render_template("settings.html")

@app.route("/notifications")
@login_required
def notifications():
    rows=q("SELECT * FROM notifications WHERE user_id=%s ORDER BY created_at DESC",(session["uid"],))
    execsql("UPDATE notifications SET is_read=TRUE WHERE user_id=%s",(session["uid"],))
    return render_template("notifications.html",notifications=rows)

# Admin
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    stats={
      "users":q("SELECT COUNT(*) c FROM profiles WHERE role='user'",one=True)["c"],
      "skills":q("SELECT COUNT(*) c FROM skills",one=True)["c"],
      "requests":q("SELECT COUNT(*) c FROM exchange_requests",one=True)["c"],
      "sessions":q("SELECT COUNT(*) c FROM sessions",one=True)["c"],
      "activeUsers":q("SELECT COUNT(*) c FROM profiles WHERE role='user' AND is_active=TRUE",one=True)["c"],
      "pending":q("SELECT COUNT(*) c FROM exchange_requests WHERE status='pending'",one=True)["c"],
    }
    cats=q("""SELECT c.name,COUNT(s.id) value FROM categories c LEFT JOIN skills s ON s.category_id=c.id GROUP BY c.id ORDER BY value DESC""")
    statuses=q("SELECT status,COUNT(*) value FROM sessions GROUP BY status")
    return render_template("admin/dashboard.html",stats=stats,cats=cats,statuses=statuses)

@app.route("/admin/users",methods=["GET","POST"])
@admin_required
def admin_users():
    if request.method=="POST":
        id=request.form["id"]; action=request.form["action"]
        if id==session["uid"]: flash("You cannot deactivate the current admin.","error")
        else:
            execsql("UPDATE profiles SET is_active=%s WHERE id=%s",(True if action=="activate" else False,id)); flash("User status updated.","success")
        return redirect(url_for("admin_users"))
    search=request.args.get("q","")
    users=q("SELECT * FROM profiles WHERE role='user' AND (full_name LIKE %s OR username LIKE %s OR email LIKE %s) ORDER BY created_at DESC",(f"%{search}%",)*3)
    return render_template("admin/users.html",users=users,search=search)

@app.route("/admin/skills",methods=["GET","POST"])
@admin_required
def admin_skills():
    if request.method=="POST":
        execsql("DELETE FROM skills WHERE id=%s",(request.form["id"],)); flash("Skill deleted.","success"); return redirect(url_for("admin_skills"))
    skills=q("""SELECT s.*,p.full_name owner,c.name category FROM skills s JOIN profiles p ON p.id=s.user_id LEFT JOIN categories c ON c.id=s.category_id ORDER BY s.created_at DESC""")
    return render_template("admin/skills.html",skills=skills)

@app.route("/admin/requests",methods=["GET","POST"])
@admin_required
def admin_requests():
    if request.method=="POST":
        execsql("DELETE FROM exchange_requests WHERE id=%s",(request.form["id"],)); flash("Request deleted.","success"); return redirect(url_for("admin_requests"))
    rows=q("""SELECT r.*,p1.full_name sender_name,p2.full_name receiver_name,st.name learn_skill,so.name offered_skill
              FROM exchange_requests r JOIN profiles p1 ON p1.id=r.sender_id JOIN profiles p2 ON p2.id=r.receiver_id
              JOIN skills st ON st.id=r.skill_to_learn_id LEFT JOIN skills so ON so.id=r.skill_offered_id ORDER BY r.created_at DESC""")
    return render_template("admin/requests.html",rows=rows)

@app.route("/admin/sessions",methods=["GET","POST"])
@admin_required
def admin_sessions():
    if request.method=="POST":
        execsql("UPDATE sessions SET status=%s WHERE id=%s",(request.form["status"],request.form["id"])); flash("Session updated.","success"); return redirect(url_for("admin_sessions"))
    rows=q("""SELECT se.*,sk.name skill,p1.full_name requester_name,p2.full_name teacher_name FROM sessions se
              JOIN skills sk ON sk.id=se.skill_id JOIN profiles p1 ON p1.id=se.requester_id JOIN profiles p2 ON p2.id=se.teacher_id ORDER BY se.date,se.time""")
    return render_template("admin/sessions.html",rows=rows)

@app.route("/admin/reviews",methods=["GET","POST"])
@admin_required
def admin_reviews():
    if request.method=="POST":
        execsql("DELETE FROM reviews WHERE id=%s",(request.form["id"],)); flash("Review deleted.","success"); return redirect(url_for("admin_reviews"))
    rows=q("""SELECT r.*,p1.full_name reviewer_name,p2.full_name reviewed_name,sk.name skill FROM reviews r
              JOIN profiles p1 ON p1.id=r.reviewer_id JOIN profiles p2 ON p2.id=r.reviewed_id LEFT JOIN skills sk ON sk.id=r.skill_id ORDER BY r.created_at DESC""")
    return render_template("admin/reviews.html",rows=rows)

@app.route("/admin/reports")
@admin_required
def admin_reports():
    rows=q("""SELECT p.full_name,p.username,COUNT(DISTINCT s.id) skills,COUNT(DISTINCT se.id) sessions,COUNT(DISTINCT r.id) reviews
              FROM profiles p LEFT JOIN skills s ON s.user_id=p.id LEFT JOIN sessions se ON se.requester_id=p.id OR se.teacher_id=p.id
              LEFT JOIN reviews r ON r.reviewed_id=p.id WHERE p.role='user' GROUP BY p.id ORDER BY sessions DESC""")
    return render_template("admin/reports.html",rows=rows)


@app.route("/ai")
@login_required
def ai_home():
    return render_template("ai_home.html")

@app.route("/ai/roadmap", methods=["GET","POST"])
@login_required
def ai_roadmap():
    result=None; goal=""
    if request.method=="POST":
        goal=request.form.get("goal","").strip()
        if goal:
            g=goal.lower()
            if "data" in g:
                steps=["Python + NumPy + Pandas","SQL + PostgreSQL","Statistics + Probability","Machine Learning + Scikit-learn","Model evaluation + Feature engineering","Portfolio: 3 end-to-end projects","Interview + deployment"]
            elif "full" in g or "web" in g:
                steps=["HTML + CSS + JavaScript","Python + Flask/FastAPI","SQL + PostgreSQL","REST APIs + Authentication","Git + GitHub","React or modern frontend","Deploy with Vercel + cloud database"]
            elif "ai" in g or "machine" in g:
                steps=["Python fundamentals","Linear algebra + statistics","NumPy + Pandas","Machine Learning","Deep Learning basics","LLM APIs + prompt engineering","Build and deploy AI projects"]
            else:
                steps=["Fundamentals and terminology","Core tools and workflows","Guided practice projects","Intermediate concepts","Portfolio project","Peer feedback and review","Interview / real-world practice"]
            result={"goal":goal,"steps":steps}
            ai_save("roadmap",goal,"\n".join(steps))
    return render_template("ai_roadmap.html",result=result,goal=goal)

@app.route("/ai/analyzer", methods=["GET","POST"])
@login_required
def ai_analyzer():
    skills=q("SELECT s.*,c.name category FROM skills s LEFT JOIN categories c ON c.id=s.category_id WHERE s.user_id=%s ORDER BY s.created_at DESC",(session["uid"],))
    result=None
    if request.method=="POST":
        names=[s["name"] for s in skills]
        result={"count":len(names),"strengths":names[:5],"gaps":["Communication","System design","Testing","Deployment"] if len(names)<6 else ["Advanced project depth","Production monitoring"],"advice":"Build one measurable project around your strongest skill and document the outcome."}
        ai_save("analyzer",", ".join(names),str(result))
    return render_template("ai_analyzer.html",skills=skills,result=result)

@app.route("/ai/interview", methods=["GET","POST"])
@login_required
def ai_interview():
    topic="Python"; questions=None
    if request.method=="POST":
        topic=request.form.get("topic","Python").strip() or "Python"
        questions=[
            f"Explain the core concepts of {topic} as if you were teaching a junior student.",
            f"Describe a project where you used {topic}. What problem did it solve?",
            f"What is one common mistake beginners make with {topic}, and how would you avoid it?",
            f"How would you test a {topic}-based feature before releasing it?",
            f"What would you learn next after becoming comfortable with {topic}?"
        ]
        ai_save("interview",topic,"\n".join(questions))
    return render_template("ai_interview.html",topic=topic,questions=questions)

@app.route("/ai/quiz", methods=["GET","POST"])
@login_required
def ai_quiz():
    topic="Python"; questions=None
    if request.method=="POST":
        topic=request.form.get("topic","Python").strip() or "Python"
        questions=[
            (f"Which is most important when learning {topic}?",["Consistent practice","Skipping fundamentals","Only watching videos","Avoiding projects"],0),
            (f"A strong {topic} portfolio should include:",["Only certificates","At least one real project","No documentation","Only copied code"],1),
            (f"When debugging {topic}, the best first step is:",["Guess randomly","Read the error and reproduce it","Delete the project","Ignore the output"],1),
            (f"For production {topic} work, version control is useful because:",["It removes all bugs","It tracks changes and collaboration","It replaces testing","It prevents deployment"],1),
            (f"The best way to improve in {topic} is:",["Build, review, and iterate","Never practice","Only memorize syntax","Avoid feedback"],0)]
        ai_save("quiz",topic,str(questions))
    return render_template("ai_quiz.html",topic=topic,questions=questions)

@app.route("/ai/resume", methods=["GET","POST"])
@login_required
def ai_resume():
    profile=q("SELECT * FROM profiles WHERE id=%s",(session["uid"],),one=True)
    skills=q("SELECT name,level FROM skills WHERE user_id=%s ORDER BY created_at DESC",(session["uid"],))
    resume=None
    if request.method=="POST":
        target=request.form.get("target","Software Developer").strip() or "Software Developer"
        summary=f"Motivated student and aspiring {target} with hands-on experience in {', '.join(s['name'] for s in skills[:6]) or 'technology and problem solving'}."
        resume={"target":target,"summary":summary,"skills":skills,"projects":["SkillX AI — Student Skill Exchange Platform","Academic / Personal Project — describe measurable outcome"],"sections":["Problem solving","Database design","Responsive web development","Testing and deployment"]}
        ai_save("resume",target,str(resume))
    return render_template("ai_resume.html",profile=profile,skills=skills,resume=resume)

@app.route("/ai/chat", methods=["GET","POST"])
@login_required
def ai_chat():
    answer=None; question=""
    if request.method=="POST":
        question=request.form.get("question","").strip()
        if question:
            low=question.lower()
            if "python" in low: answer="Python tip: break the problem into small functions, validate inputs, and test each function with a small example."
            elif "sql" in low or "database" in low: answer="SQL tip: start with the required rows, then joins, then filters, and finally aggregation. Always test the query on a small sample first."
            elif "resume" in low: answer="Resume tip: quantify project outcomes, list the technologies you actually used, and keep each project focused on problem → solution → result."
            elif "interview" in low: answer="Interview tip: answer with a short definition, a concrete example, your trade-off, and what you learned."
            else: answer="SkillX AI Coach: turn your question into a concrete task, build a small example, test it, and document what you learned. Ask me about Python, SQL, projects, resumes, or interviews."
            ai_save("chat",question,answer)
    return render_template("ai_chat.html",question=question,answer=answer)

@app.errorhandler(403)
def forbidden(e): return render_template("error.html",code=403,message="You do not have permission to access this page."),403
@app.errorhandler(404)
def not_found(e): return render_template("error.html",code=404,message="The page you requested was not found."),404

def close_pool():
    try:
        DB_POOL.close()
    except Exception:
        pass



if __name__=="__main__":
    init_db()
    app.run(host="127.0.0.1",port=int(os.environ.get("PORT",5000)),debug=os.environ.get("DEBUG","1")=="1")
