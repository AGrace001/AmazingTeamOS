#!/usr/bin/env python3
"""TheAmazingTeamOs - The Amazing Team office/team PWA (original implementation).
Stdlib only: http.server + sqlite3. Run: python3 app.py  (binds 0.0.0.0:8000)
Replace branding in config.json. Integrate Paystack/Flutterwave in billing stub.
"""
import hashlib, hmac, json, os, re, secrets, sqlite3, datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from urllib.parse import urlparse, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "data", "app.db")
CONFIG = json.load(open(os.path.join(BASE, "config.json")))
PORT = int(os.environ.get("PORT", "8000"))

def now(): return datetime.datetime.utcnow()
def iso(d=None): return (d or now()).isoformat() + "Z"
def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); return c

def init():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, pw TEXT, created TEXT);
    CREATE TABLE IF NOT EXISTS offices(id INTEGER PRIMARY KEY, name TEXT, slug TEXT UNIQUE, invite_code TEXT, plan TEXT DEFAULT 'trial', pro INTEGER DEFAULT 0, trial_ends TEXT, next_billing TEXT, created TEXT, owner_id INTEGER);
    CREATE TABLE IF NOT EXISTS memberships(user_id INTEGER, office_id INTEGER, role TEXT DEFAULT 'member', UNIQUE(user_id, office_id));
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER, created TEXT);
    CREATE TABLE IF NOT EXISTS prospects(id INTEGER PRIMARY KEY, office_id INTEGER, owner_id INTEGER, name TEXT, phone TEXT, stage TEXT DEFAULT 'New', notes TEXT, created TEXT, updated TEXT);
    CREATE TABLE IF NOT EXISTS attendance(id INTEGER PRIMARY KEY, office_id INTEGER, user_id INTEGER, date TEXT, status TEXT DEFAULT 'present', note TEXT, UNIQUE(office_id,user_id,date));
    CREATE TABLE IF NOT EXISTS earnings(id INTEGER PRIMARY KEY, office_id INTEGER, user_id INTEGER, amount REAL, description TEXT, date TEXT);
    CREATE TABLE IF NOT EXISTS trainings(id INTEGER PRIMARY KEY, office_id INTEGER, title TEXT, description TEXT, date TEXT, created_by INTEGER);
    CREATE TABLE IF NOT EXISTS completions(training_id INTEGER, user_id INTEGER, UNIQUE(training_id,user_id));
    CREATE TABLE IF NOT EXISTS goals(id INTEGER PRIMARY KEY, office_id INTEGER, user_id INTEGER, title TEXT, target REAL, current REAL DEFAULT 0, unit TEXT, deadline TEXT);
    CREATE TABLE IF NOT EXISTS office_links(office_id INTEGER, linked_office_id INTEGER, UNIQUE(office_id,linked_office_id));
    CREATE TABLE IF NOT EXISTS stepups(id INTEGER PRIMARY KEY, office_id INTEGER, user_id INTEGER, new_status TEXT, note TEXT, congrats INTEGER DEFAULT 0, date TEXT, recorded_by INTEGER);
    CREATE TABLE IF NOT EXISTS checklist(id INTEGER PRIMARY KEY, office_id INTEGER, user_id INTEGER, date TEXT, text TEXT, done INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS resources(id INTEGER PRIMARY KEY, office_id INTEGER, title TEXT, kind TEXT, link TEXT, created_by INTEGER);
    CREATE TABLE IF NOT EXISTS fund_entries(id INTEGER PRIMARY KEY, office_id INTEGER, user_id INTEGER, kind TEXT, amount REAL, description TEXT, date TEXT);
    CREATE TABLE IF NOT EXISTS profiles(user_id INTEGER PRIMARY KEY, phone TEXT, sponsor TEXT, status TEXT DEFAULT 'Member', why TEXT);
    CREATE TABLE IF NOT EXISTS office_settings(office_id INTEGER, key TEXT, value TEXT, UNIQUE(office_id,key));
    CREATE TABLE IF NOT EXISTS pending_invites(id INTEGER PRIMARY KEY, office_id INTEGER, name TEXT, email TEXT, phone TEXT, requested TEXT);
    CREATE TABLE IF NOT EXISTS external_people(id INTEGER PRIMARY KEY, office_id INTEGER, name TEXT, status TEXT, sponsor TEXT, location TEXT, on_app INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS membership_roles(user_id INTEGER, office_id INTEGER, role TEXT, UNIQUE(user_id, office_id, role));
    CREATE TABLE IF NOT EXISTS training_assignments(id INTEGER PRIMARY KEY, training_id INTEGER, user_id INTEGER, office_id INTEGER, kind TEXT, UNIQUE(training_id, user_id, kind));
    CREATE TABLE IF NOT EXISTS platform_admins(id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, pw TEXT, created TEXT);
    CREATE TABLE IF NOT EXISTS admin_sessions(token TEXT PRIMARY KEY, admin_id INTEGER, created TEXT);
    CREATE TABLE IF NOT EXISTS platform_settings(key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS audit_logs(id INTEGER PRIMARY KEY, admin_id INTEGER, action TEXT, details TEXT, created TEXT);
    """)
    for _col,_typ in [("session","TEXT DEFAULT 'Office hours'"),("check_in","TEXT"),("check_out","TEXT")]:
        try: c.execute(f"ALTER TABLE attendance ADD COLUMN {_col} {_typ}")
        except Exception: pass
    try: c.execute("ALTER TABLE stepups ADD COLUMN prev_status TEXT")
    except Exception: pass
    try: c.execute("ALTER TABLE external_people ADD COLUMN created TEXT")
    except Exception: pass
    try: c.execute("ALTER TABLE profiles ADD COLUMN photo TEXT")
    except Exception: pass
    for _tbl,_col in [("offices","suspended INTEGER DEFAULT 0"),("users","suspended INTEGER DEFAULT 0")]:
        try: c.execute(f"ALTER TABLE {_tbl} ADD COLUMN {_col}")
        except Exception: pass
    try: c.execute("UPDATE memberships SET role='super_admin' WHERE rowid IN (SELECT m.rowid FROM memberships m JOIN offices o ON o.id=m.office_id WHERE m.user_id=o.owner_id)")
    except Exception: pass
    try:
        c.execute("UPDATE memberships SET role='Tutor' WHERE role='trainer'")
        for _m in c.execute("SELECT user_id, office_id, role FROM memberships").fetchall():
            _r = "Tutor" if _m[2] == "trainer" else _m[2]
            if _r and _r != "member": c.execute("INSERT OR IGNORE INTO membership_roles VALUES(?,?,?)", (_m[0], _m[1], _r))
    except Exception: pass
    import os as _os
    if not c.execute("SELECT 1 FROM platform_admins LIMIT 1").fetchone():
        c.execute("INSERT INTO platform_admins(name,email,pw,created) VALUES(?,?,?,?)",("Platform Owner", _os.environ.get("ADMIN_EMAIL","admin@example.com"), hash_pw(_os.environ.get("ADMIN_PASSWORD","admin1234")), iso()))
    c.commit()
    c.execute("UPDATE offices SET plan='free', pro=1, next_billing=NULL, trial_ends=NULL")
    c.execute("UPDATE profiles SET sponsor='Adaeze@example.com' WHERE user_id IN (SELECT id FROM users WHERE email='Blessing@example.com')")
    c.execute("UPDATE profiles SET sponsor='Chidi@example.com' WHERE user_id IN (SELECT id FROM users WHERE email='Fatima@example.com')")
    c.commit()
    _d=c.execute("SELECT id FROM offices WHERE slug='demo'").fetchone()
    if _d and c.execute("SELECT COUNT(*) n FROM memberships WHERE office_id=?",(_d["id"],)).fetchone()["n"]<5:
        _oid=_d["id"]
        for nm,em,st,amt in [("Adaeze Okafor","Adaeze@example.com","Pro",120),("Blessing Bello","Blessing@example.com","Newbie",45),("Chidi Nwosu","Chidi@example.com","Director",80),("Fatima Bello","Fatima@example.com","Distributor",0)]:
            if not c.execute("SELECT 1 FROM users WHERE email=?",(em,)).fetchone():
                _u=c.execute("INSERT INTO users(name,email,pw,created) VALUES(?,?,?,?)",(nm,em,hash_pw("member1234"),iso())).lastrowid
                c.execute("INSERT INTO memberships VALUES(?,?, 'member')",(_u,_oid))
                c.execute("INSERT OR IGNORE INTO profiles VALUES(?,?,?,?,?)",(_u,"","demo@example.com",st,""))
                if amt: c.execute("INSERT INTO earnings(office_id,user_id,amount,description,date) VALUES(?,?,?,?,date('now'))",(_oid,_u,amt,"Sample earning"))
        c.commit()
    # seed demo
    if not c.execute("SELECT 1 FROM offices WHERE slug='demo'").fetchone():
        pw = hash_pw("demo1234")
        cur = c.execute("INSERT INTO users(name,email,pw,created) VALUES(?,?,?,?)", ("Demo Admin", "demo@example.com", pw, iso()))
        uid = cur.lastrowid
        trial = None
        cur = c.execute("INSERT INTO offices(name,slug,invite_code,plan,trial_ends,created,owner_id) VALUES(?,?,?,?,?,?,?)",
                        ("Demo Office", "demo", "DEMO2026", "free", trial, iso(), uid))
        oid = cur.lastrowid
        c.execute("INSERT INTO memberships VALUES(?,?, 'admin')", (uid, oid))
        for name, phone, stage in [("Adaeze Okafor", "0803 000 0001", "New"), ("Blessing Bello", "0803 000 0002", "Contacted"), ("Chidi Nwosu", "0803 000 0003", "Interested"), ("Fatima Bello", "0803 000 0004", "Presented")]:
            c.execute("INSERT INTO prospects(office_id,owner_id,name,phone,stage,notes,created,updated) VALUES(?,?,?,?,?,?,?,?)", (oid, uid, name, phone, stage, "", iso(), iso()))
        c.execute("INSERT INTO earnings(office_id,user_id,amount,description,date) VALUES(?,?,?,?,date('now'))", (oid, uid, 50000, "Starter pack commission"))
        for nm, em, st in [("Adaeze Okafor","Adaeze@example.com","Pro"),("Blessing Bello","Blessing@example.com","Newbie"),("Chidi Nwosu","Chidi@example.com","Director"),("Fatima Bello","Fatima@example.com","Distributor")]:
            cur2=c.execute("INSERT INTO users(name,email,pw,created) VALUES(?,?,?,?)",(nm,em,hash_pw("member1234"),iso())); mid=cur2.lastrowid
            c.execute("INSERT INTO memberships VALUES(?,?, 'member')",(mid,oid))
            c.execute("INSERT OR IGNORE INTO profiles VALUES(?,?,?,?,?)",(mid,"", "demo@example.com", st, ""))
            c.execute("INSERT INTO earnings(office_id,user_id,amount,description,date) VALUES(?,?,?,?,date('now'))",(oid,mid,120 if nm=="Adaeze Okafor" else 0,"Sample earning" if nm=="Adaeze Okafor" else ""))
        c.execute("INSERT INTO trainings(office_id,title,description,date,created_by) VALUES(?,?,?,?,?)", (oid, "Prospecting Basics", "How to build and work your list", "2026-11-10", uid))
        c.execute("INSERT INTO goals(office_id,user_id,title,target,current,unit,deadline) VALUES(?,?,?,?,?,?,?)", (oid, uid, "New prospects this month", 20, 4, "prospects", "2026-11-30"))
        c.commit()
    _pd=c.execute("SELECT id FROM offices WHERE slug='demo'").fetchone()
    if _pd and not c.execute("SELECT 1 FROM pending_invites WHERE office_id=?",(_pd["id"],)).fetchone():
        c.execute("INSERT INTO pending_invites(office_id,name,email,phone,requested) VALUES(?,?,?,?,date('now'))",(_pd["id"],"New Member Awaiting Approval","newmember@example.com","0803 000 0010"))
        c.commit()
    c.close()

def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()
    return f"{salt}${h}"
def check_pw(pw, stored):
    try:
        salt, h = stored.split("$"); return hmac.compare_digest(hash_pw(pw, salt).split("$")[1], h)
    except Exception: return False

AI_RULES = [
    (["price", "cost", "expensive", "how much", "money"], "price objection"),
    (["busy", "no time", "time"], "too busy"),
    (["scam", "pyramid", "ponzi", "legit", "real"], "trust / is it legit"),
    (["not interested", "no interest", "not for me"], "not interested"),
    (["husband", "wife", "spouse", "partner"], "needs to ask partner"),
    (["think", "later", "next month", "decide"], "needs time to think"),
]
def ai_replies(situation, name=""):
    n = name or "there"
    s = situation.lower(); kind = "general follow-up"
    for keys, label in AI_RULES:
        if any(k in s for k in keys): kind = label; break
    templates = {
        "price objection": [
            f"Hi {n}, I completely understand, I asked the same thing at first. That's exactly why most people here start small and let the training show them how to earn it back. Can I show you the smallest starter option and what people typically do in their first 2 weeks?",
            f"{n}, fair question. It's not really about the cost, it's about whether it can pay you back. Would it help if I shared a short breakdown of how 2 people I know recovered their start-up cost?",
            f"I hear you, {n}. No pressure at all. If I could show you a way to start without straining yourself, would you be open to a 10-minute look this evening?"],
        "too busy": [
            f"Hi {n}, I get it, most of us started while busy with work/family. This is built around 30-60 minutes a day, with recordings if you miss anything. Could I send you a 5-minute overview first?",
            f"That's exactly why I thought of you, {n}, busy people usually want an extra stream that doesn't need all day. Open to a quick look when you're free this week?",
            f"No wahala, {n}. I'll send a short summary and you can check it whenever. When is usually quieter for you, morning or evening?"],
        "trust / is it legit": [
            f"Hi {n}, it's a fair question and you're right to ask. This is a registered business, products are real, and earnings come from product sales + team building, no guarantees, it takes work. Can I send you the company info so you can verify yourself?",
            f"I asked the same, {n}. What convinced me was seeing the products, the office training, and people I know getting paid. Would you like to attend one free training (online) and judge for yourself?",
            f"Healthy scepticism is good, {n}. Let me share the official pages and a short video, then ask me anything, no pressure to join."],
        "not interested": [
            f"No problem at all, {n}, thanks for hearing me out. If it's okay, I'll keep you on my list for updates and check in in a few months. Wishing you well!",
            f"Totally fine, {n}. Just out of curiosity, is it the business itself, or the timing? Your answer helps me not bother you with the wrong thing again.",
            f"Understood, {n}. Before I close your file, would you know 1-2 people who are looking for extra income? I'd really appreciate a referral."],
        "needs to ask partner": [
            f"Of course, {n}, that's a good decision to make together. Would a short 10-minute call with both of you help, so they hear it directly and can ask questions?",
            f"Absolutely, {n}. I'll send a one-page summary you can share at home. When should I check back, tomorrow evening?",
            f"Makes sense, {n}. Most partners mainly ask about cost, time and whether it's legit, I can send answers to all three for you to share."],
        "needs time to think": [
            f"Of course, {n}, take your time. To help your thinking, what's your biggest question right now: the product, the pay, or the time? I'll answer just that one clearly.",
            f"No pressure, {n}. I'll check in on Thursday. In the meantime I'll send a 5-minute video that covers what most people ask.",
            f"Sure thing, {n}. Good decisions need clarity, not pressure. Can we do a quick 5-minute Q&A tomorrow so you have everything before you decide?"],
        "general follow-up": [
            f"Hi {n}, just checking in, did you get a chance to look at what I sent? I have 2 slots for a short presentation tomorrow. Would morning or evening suit you better?",
            f"Hello {n}, following up gently. No pressure at all, are you still open to hearing how it works, or should I check back later?",
            f"Hi {n}, quick one: on a scale of 1-10, how open are you to an extra income stream right now? Your answer tells me exactly what to send next."],
    }
    return {"category": kind, "replies": templates[kind]}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send_json(self, obj, code=200, cookie=None):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if cookie: self.send_header("Set-Cookie", cookie)
        self.end_headers(); self.wfile.write(body)
    def body(self):
        ln = int(self.headers.get("Content-Length") or 0)
        try: return json.loads(self.rfile.read(ln) or b"{}")
        except Exception: return {}
    def user(self):
        ck = SimpleCookie(self.headers.get("Cookie") or "")
        if "session" not in ck: return None
        c = db(); r = c.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?", (ck["session"].value,)).fetchone(); c.close()
        return dict(r) if r else None
    def office(self, c, u):
        oid = self.headers.get("X-Office-Id")
        if not oid: return None, None
        m = c.execute("SELECT * FROM memberships WHERE user_id=? AND office_id=?", (u["id"], oid)).fetchone()
        if not m: return None, None
        o = c.execute("SELECT * FROM offices WHERE id=?", (oid,)).fetchone()
        return dict(o), m["role"]
    def admin(self):
        ck = SimpleCookie(self.headers.get("Cookie") or "")
        if "admin_session" not in ck: return None
        c = db(); r = c.execute("SELECT a.* FROM admin_sessions s JOIN platform_admins a ON a.id=s.admin_id WHERE s.token=?", (ck["admin_session"].value,)).fetchone(); c.close()
        return dict(r) if r else None
    def audit(self, admin_id, action, details=""):
        c = db(); c.execute("INSERT INTO audit_logs(admin_id,action,details,created) VALUES(?,?,?,?)", (admin_id, action, details, iso())); c.commit(); c.close()
    OFFICE_ROLES = ("super_admin", "admin", "leader", "treasurer", "earnings_manager", "Tutor", "training_head", "member")
    ELEVATED_ROLES = ("admin", "leader", "treasurer", "earnings_manager", "Tutor", "training_head")
    ROLE_PRIORITY = ("super_admin", "admin", "leader", "training_head", "treasurer", "earnings_manager", "Tutor", "member")
    def role_set(self, c, user_id, office_id):
        rows = [r["role"] for r in c.execute("SELECT role FROM membership_roles WHERE user_id=? AND office_id=?", (user_id, office_id)).fetchall()]
        if not rows:
            m = c.execute("SELECT role FROM memberships WHERE user_id=? AND office_id=?", (user_id, office_id)).fetchone()
            if m and m["role"] and m["role"] != "member": rows = ["Tutor" if m["role"] == "trainer" else m["role"]]
        return rows
    def primary_role(self, roles):
        for r in self.ROLE_PRIORITY:
            if r in roles: return r
        return "member"
    def save_roles(self, c, user_id, office_id, roles):
        roles = [r for r in dict.fromkeys(roles or []) if r in self.ELEVATED_ROLES or r == "super_admin"]
        c.execute("DELETE FROM membership_roles WHERE user_id=? AND office_id=?", (user_id, office_id))
        for r in roles: c.execute("INSERT OR IGNORE INTO membership_roles VALUES(?,?,?)", (user_id, office_id, r))
        c.execute("UPDATE memberships SET role=? WHERE user_id=? AND office_id=?", (self.primary_role(roles), user_id, office_id))
        return roles
    MANAGERS = ("super_admin", "admin")
    PRIVILEGED = ("super_admin", "admin", "leader")
    def can(self, role, *allowed):
        return role in allowed
    def require(self):
        u = self.user()
        if not u: self.send_json({"error": "Sign in required"}, 401); return None
        if u.get("suspended"): self.send_json({"error": "This account has been suspended. Please contact your office leader."}, 403); return None
        return u

    def do_GET(self):
        p = urlparse(self.path).path
        if p.startswith("/api/"): return self.api_get(p)
        # static / SPA fallback
        fp = os.path.join(BASE, "static", "index.html" if p in ("/",) else p.lstrip("/"))
        if p == "/manifest.webmanifest": fp = os.path.join(BASE, "static", "manifest.webmanifest")
        if os.path.isfile(fp):
            ext = fp.rsplit(".", 1)[-1]
            ct = {"html": "text/html", "css": "text/css", "js": "application/javascript", "webmanifest": "application/manifest+json", "svg": "image/svg+xml", "json": "application/json"}.get(ext, "application/octet-stream")
            data = open(fp, "rb").read()
            self.send_response(200); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        else:
            data = open(os.path.join(BASE, "static", "index.html"), "rb").read()
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def api_get(self, p):
        if p.startswith("/api/admin/"): return self.admin_get(p)
        if p == "/api/config": return self.send_json({"config": CONFIG})
        u = self.require()
        if not u: return
        c = db()
        if p == "/api/me":
            ms = c.execute("SELECT o.id,o.name,o.slug,o.plan,m.role FROM memberships m JOIN offices o ON o.id=m.office_id WHERE m.user_id=?", (u["id"],)).fetchall()
            offices = []
            for x in ms:
                d0 = dict(x); rs = self.role_set(c, u["id"], d0["id"]); d0["roles"] = rs; d0["role"] = self.primary_role(rs); offices.append(d0)
            _ph = c.execute("SELECT photo FROM profiles WHERE user_id=?", (u["id"],)).fetchone()
            c.close(); return self.send_json({"user": {"id": u["id"], "name": u["name"], "email": u["email"], "photo": (_ph["photo"] if _ph and _ph["photo"] else "")}, "offices": offices})
        o, role = self.office(c, u)
        if not o: c.close(); return self.send_json({"error": "Select an office"}, 400)
        oid = o["id"]
        roles = self.role_set(c, u["id"], oid); R = set(roles); role = self.primary_role(roles)
        if p == "/api/roles":
            matrix = {
              "super_admin": ["Create the office", "Everything an Office Admin can do", "Give or change any role", "Transfer Super Admin", "Office settings and billing", "Delete and link offices"],
              "admin": ["Full office management", "Add and approve members", "Assign roles", "Mark attendance for others", "Team prospects, reports and step ups", "Training, goals and settings"],
              "leader": ["See team reports and prospects", "Mark attendance for others", "Record step ups", "Add people to the team structure", "Follow up the team"],
              "treasurer": ["See and record office funds", "Dues and spending records", "All normal member features"],
              "earnings_manager": ["Log earnings for other members", "See office earnings entries", "All normal member features"],
              "Tutor": ["Teaches a training class", "Assigned to specific classes", "Add learning material", "All normal member features"],
              "training_head": ["Leads a training class", "Add training classes", "Add learning material", "Assigned to specific classes they lead"],
              "member": ["No elevated role", "Own dashboard and My Day", "Mark own attendance", "Own prospects and earnings", "Learning, leaderboard and team structure view", "Own goals, checklist and profile"],
            }; c.close(); return self.send_json({"role": role, "myRoles": roles, "roles": matrix})
        _gate = {"/api/pending": ("super_admin", "admin"), "/api/reports": ("super_admin", "admin", "leader"), "/api/settings": ("super_admin", "admin", "treasurer"), "/api/funds": ("super_admin", "admin", "treasurer"), "/api/billing": ("super_admin", "admin")}
        if p in _gate and not (R & set(_gate[p])): c.close(); return self.send_json({"error": "Your role does not allow this. Ask your Super Admin if you need access."}, 403)
        if p == "/api/dashboard":
            today = datetime.date.today().isoformat()
            data = {
                "office": o, "role": role,
                "members": c.execute("SELECT COUNT(*) n FROM memberships WHERE office_id=?", (oid,)).fetchone()["n"],
                "attendanceToday": c.execute("SELECT COUNT(*) n FROM attendance WHERE office_id=? AND date=?", (oid, today)).fetchone()["n"],
                "prospects": {r["stage"]: r["n"] for r in c.execute("SELECT stage,COUNT(*) n FROM prospects WHERE office_id=? GROUP BY stage", (oid,))},
                "earningsMonth": c.execute("SELECT COALESCE(SUM(amount),0) s FROM earnings WHERE office_id=? AND substr(date,1,7)=substr(date('now'),1,7) AND (?=1 OR user_id=?)", (oid, 1 if (R & {"super_admin","admin","leader","earnings_manager"}) else 0, u["id"])).fetchone()["s"],
                "trainings": c.execute("SELECT COUNT(*) n FROM trainings WHERE office_id=?", (oid,)).fetchone()["n"],
            }; c.close(); return self.send_json(data)
        if p == "/api/prospects":
            if R & {"super_admin", "admin", "leader"}:
                rows = c.execute("SELECT p.*,u.name owner_name FROM prospects p LEFT JOIN users u ON u.id=p.owner_id WHERE p.office_id=? ORDER BY p.updated DESC", (oid,)).fetchall()
            else:
                rows = c.execute("SELECT p.*,u.name owner_name FROM prospects p LEFT JOIN users u ON u.id=p.owner_id WHERE p.office_id=? AND p.owner_id=? ORDER BY p.updated DESC", (oid, u["id"])).fetchall()
            c.close(); return self.send_json({"items": [dict(x) for x in rows]})
        if p == "/api/attendance":
            if R & {"super_admin", "admin", "leader"}:
                rows = c.execute("SELECT a.*,u.name FROM attendance a JOIN users u ON u.id=a.user_id WHERE a.office_id=? ORDER BY a.date DESC LIMIT 200", (oid,)).fetchall()
            else:
                rows = c.execute("SELECT a.*,u.name FROM attendance a JOIN users u ON u.id=a.user_id WHERE a.office_id=? AND a.user_id=? ORDER BY a.date DESC LIMIT 200", (oid, u["id"])).fetchall()
            c.close(); return self.send_json({"items": [dict(x) for x in rows]})
        if p == "/api/earnings":
            if R & {"super_admin", "admin", "leader", "earnings_manager"}:
                rows = c.execute("SELECT e.*,u.name,COALESCE(pr.photo,'') photo FROM earnings e JOIN users u ON u.id=e.user_id LEFT JOIN profiles pr ON pr.user_id=e.user_id WHERE e.office_id=? ORDER BY e.date DESC LIMIT 200", (oid,)).fetchall()
            else:
                rows = c.execute("SELECT e.*,u.name,COALESCE(pr.photo,'') photo FROM earnings e JOIN users u ON u.id=e.user_id LEFT JOIN profiles pr ON pr.user_id=e.user_id WHERE e.office_id=? AND e.user_id=? ORDER BY e.date DESC LIMIT 200", (oid, u["id"])).fetchall()
            c.close(); return self.send_json({"items": [dict(x) for x in rows]})
        if p == "/api/trainings":
            rows = c.execute("SELECT t.*,(SELECT COUNT(*) FROM completions WHERE training_id=t.id AND user_id=?) done FROM trainings t WHERE t.office_id=? ORDER BY t.date DESC", (u["id"], oid)).fetchall(); c.close(); return self.send_json({"items": [dict(x) for x in rows]})
        if p == "/api/goals":
            if R & {"super_admin", "admin", "leader"}:
                rows = c.execute("SELECT g.*,u.name FROM goals g JOIN users u ON u.id=g.user_id WHERE g.office_id=? ORDER BY g.id DESC", (oid,)).fetchall()
            else:
                rows = c.execute("SELECT g.*,u.name FROM goals g JOIN users u ON u.id=g.user_id WHERE g.office_id=? AND g.user_id=? ORDER BY g.id DESC", (oid, u["id"])).fetchall()
            c.close(); return self.send_json({"items": [dict(x) for x in rows]})
        if p == "/api/members":
            rows = c.execute("SELECT u.id,u.name,u.email,m.role,COALESCE(pr.status,'Member') status,COALESCE(pr.phone,'') phone,COALESCE(pr.sponsor,'') sponsor,COALESCE(pr.photo,'') photo FROM memberships m JOIN users u ON u.id=m.user_id LEFT JOIN profiles pr ON pr.user_id=u.id WHERE m.office_id=? ORDER BY u.name", (oid,)).fetchall()
            items = []
            for x in rows:
                d0 = dict(x); rs = self.role_set(c, d0["id"], oid); d0["roles"] = rs; d0["role"] = self.primary_role(rs)
                d0["tutor_classes"] = [r["training_id"] for r in c.execute("SELECT training_id FROM training_assignments WHERE user_id=? AND office_id=? AND kind='Tutor'", (d0["id"], oid))]
                d0["head_classes"] = [r["training_id"] for r in c.execute("SELECT training_id FROM training_assignments WHERE user_id=? AND office_id=? AND kind='training_head'", (d0["id"], oid))]
                items.append(d0)
            c.close(); return self.send_json({"items": items, "office": o})
        if p == "/api/leaderboard":
            rows = c.execute("""SELECT u.name,
              COALESCE((SELECT SUM(amount) FROM earnings WHERE office_id=? AND user_id=u.id),0) earnings,
              (SELECT COUNT(*) FROM attendance WHERE office_id=? AND user_id=u.id) checkins,
              (SELECT COUNT(*) FROM prospects WHERE office_id=? AND owner_id=u.id) prospects
              FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.office_id=? ORDER BY earnings DESC""", (oid, oid, oid, oid)).fetchall(); c.close(); return self.send_json({"items": [dict(x) for x in rows]})
        if p == "/api/reports":
            rows=c.execute("SELECT a.*,u.name,pr.status FROM attendance a JOIN users u ON u.id=a.user_id LEFT JOIN profiles pr ON pr.user_id=u.id WHERE a.office_id=? ORDER BY u.name",(oid,)).fetchall()
            members=c.execute("SELECT u.id,u.name,m.role,COALESCE(pr.status,'Member') status,COALESCE(pr.photo,'') photo FROM memberships m JOIN users u ON u.id=m.user_id LEFT JOIN profiles pr ON pr.user_id=u.id WHERE m.office_id=? ORDER BY u.name",(oid,)).fetchall()
            c.close(); return self.send_json({"attendance":[dict(x) for x in rows],"members":[dict(x) for x in members]})
        if p == "/api/stepups":
            rows=c.execute("SELECT s.*,u.name,COALESCE(pr.photo,'') photo FROM stepups s JOIN users u ON u.id=s.user_id LEFT JOIN profiles pr ON pr.user_id=u.id WHERE s.office_id=? ORDER BY s.id DESC",(oid,)).fetchall(); c.close(); return self.send_json({"items":[dict(x) for x in rows]})
        if p == "/api/checklist":
            rows=c.execute("SELECT * FROM checklist WHERE office_id=? AND user_id=? ORDER BY id",(oid,u["id"])).fetchall(); c.close(); return self.send_json({"items":[dict(x) for x in rows]})
        if p == "/api/resources":
            rows=c.execute("SELECT * FROM resources WHERE office_id=? ORDER BY id DESC",(oid,)).fetchall(); c.close(); return self.send_json({"items":[dict(x) for x in rows]})
        if p == "/api/funds":
            rows=c.execute("SELECT f.*,u.name FROM fund_entries f LEFT JOIN users u ON u.id=f.user_id WHERE f.office_id=? ORDER BY f.id DESC",(oid,)).fetchall()
            members=c.execute("SELECT u.id,u.name,COALESCE(pr.status,'Member') status FROM memberships m JOIN users u ON u.id=m.user_id LEFT JOIN profiles pr ON pr.user_id=u.id WHERE m.office_id=?",(oid,)).fetchall()
            c.close(); return self.send_json({"items":[dict(x) for x in rows],"members":[dict(x) for x in members]})
        if p == "/api/profile":
            r=c.execute("SELECT * FROM profiles WHERE user_id=?",(u["id"],)).fetchone(); c.close()
            return self.send_json({"user":{"id":u["id"],"name":u["name"],"email":u["email"]},"profile":dict(r) if r else {"phone":"","sponsor":"","status":"Member","why":"","photo":""}})
        if p == "/api/settings":
            rows=c.execute("SELECT key,value FROM office_settings WHERE office_id=?",(oid,)).fetchall(); c.close(); return self.send_json({"settings":{r["key"]:r["value"] for r in rows},"office":o})
        if p == "/api/structure":
            rows=c.execute("SELECT u.id,u.name,m.role,COALESCE(pr.status,'Member') status,COALESCE(pr.sponsor,'') sponsor,'' location,1 on_app,u.created joined,COALESCE(pr.photo,'') photo FROM memberships m JOIN users u ON u.id=m.user_id LEFT JOIN profiles pr ON pr.user_id=u.id WHERE m.office_id=? ORDER BY u.name",(oid,)).fetchall()
            ext=c.execute("SELECT id,name,'member' role,status,sponsor,location,on_app,created joined FROM external_people WHERE office_id=?",(oid,)).fetchall(); c.close(); return self.send_json({"items":[dict(x) for x in rows]+[dict(x) for x in ext]})
        if p == "/api/pending":
            rows=c.execute("SELECT * FROM pending_invites WHERE office_id=? ORDER BY id DESC",(oid,)).fetchall(); c.close(); return self.send_json({"items":[dict(x) for x in rows]})
        if p == "/api/billing":
            plan = next((x for x in CONFIG["plans"] if x["id"] == o["plan"]), None)
            count = c.execute("SELECT COUNT(*) n FROM memberships WHERE office_id=?", (oid,)).fetchone()["n"]; c.close()
            return self.send_json({"office": o, "plan": plan, "plans": CONFIG["plans"], "proAddon": CONFIG["proAddon"], "memberCount": count})
        c.close(); return self.send_json({"error": "Not found"}, 404)

    def do_POST(self): return self.api_write(urlparse(self.path).path)
    def do_PATCH(self): return self.api_write(urlparse(self.path).path)

    def api_write(self, p):
        b = self.body()
        if p.startswith("/api/admin/"): return self.admin_write(p, b)
        c = db()
        # auth routes
        if p == "/api/auth/signup-office":
            slug = re.sub(r"[^a-z0-9-]", "-", (b.get("slug") or b.get("office_name", "")).lower()).strip("-")
            if c.execute("SELECT 1 FROM offices WHERE slug=?", (slug,)).fetchone(): return self.send_json({"error": "Office address already taken"}, 400)
            if c.execute("SELECT 1 FROM users WHERE email=?", (b["email"].lower(),)).fetchone(): return self.send_json({"error": "Email already registered, sign in instead"}, 400)
            cur = c.execute("INSERT INTO users(name,email,pw,created) VALUES(?,?,?,?)", (b["name"], b["email"].lower(), hash_pw(b["password"]), iso())); uid = cur.lastrowid
            trial = None
            cur = c.execute("INSERT INTO offices(name,slug,invite_code,plan,trial_ends,created,owner_id) VALUES(?,?,?,?,?,?,?)", (b["office_name"], slug, secrets.token_hex(3).upper(), "free", trial, iso(), uid)); oid = cur.lastrowid
            c.execute("INSERT INTO memberships VALUES(?,?, 'super_admin')", (uid, oid)); c.execute("INSERT OR IGNORE INTO membership_roles VALUES(?,?, 'super_admin')", (uid, oid)); c.commit(); c.close(); return self.login_user(uid)
        if p == "/api/auth/join":
            o = c.execute("SELECT * FROM offices WHERE slug=? OR invite_code=?", ((b.get("slug") or "").lower(), (b.get("invite_code") or "").upper())).fetchone()
            if not o: c.close(); return self.send_json({"error": "Office not found, check the address/invite code"}, 404)
            if c.execute("SELECT 1 FROM users WHERE email=?", (b["email"].lower(),)).fetchone(): c.close(); return self.send_json({"error": "Email already registered, sign in, then join from inside"}, 400)
            cur = c.execute("INSERT INTO users(name,email,pw,created) VALUES(?,?,?,?)", (b["name"], b["email"].lower(), hash_pw(b["password"]), iso())); uid = cur.lastrowid
            c.execute("INSERT INTO memberships VALUES(?,?, 'member')", (uid, o["id"])); c.commit(); c.close(); return self.login_user(uid)
        if p == "/api/auth/login":
            r = c.execute("SELECT * FROM users WHERE email=?", (b.get("email", "").lower(),)).fetchone()
            if not r or not check_pw(b.get("password", ""), r["pw"]): c.close(); return self.send_json({"error": "Wrong email or password"}, 401)
            if r["suspended"]: c.close(); return self.send_json({"error": "This account has been suspended. Please contact your office leader."}, 403)
            uid = r["id"]; c.close(); return self.login_user(uid)
        if p == "/api/auth/logout":
            ck = SimpleCookie(self.headers.get("Cookie") or "")
            if "session" in ck: c.execute("DELETE FROM sessions WHERE token=?", (ck["session"].value,)); c.commit()
            c.close(); return self.send_json({"ok": True}, cookie="session=; Path=/; Max-Age=0")
        u = self.require()
        if not u: c.close(); return
        o, role = (None, None)
        if p not in ("/api/offices/link",):
            o, role = self.office(c, u)
            if not o: c.close(); return self.send_json({"error": "Select an office"}, 400)
        oid = o["id"] if o else None
        roles = self.role_set(c, u["id"], oid) if oid else []
        R = set(roles); role = self.primary_role(roles) if oid else role
        if p == "/api/checkin":
            c.execute("INSERT OR REPLACE INTO attendance(office_id,user_id,date,status,note) VALUES(?,?,?,?,?)", (oid, u["id"], b.get("date") or datetime.date.today().isoformat(), "present", b.get("note", "")))
        elif p == "/api/prospects":
            c.execute("INSERT INTO prospects(office_id,owner_id,name,phone,stage,notes,created,updated) VALUES(?,?,?,?,?,?,?,?)", (oid, u["id"], b["name"], b.get("phone", ""), b.get("stage", "New"), b.get("notes", ""), iso(), iso()))
        elif p.startswith("/api/prospects/"):
            pid = p.split("/")[-1]
            if R & {"super_admin", "admin", "leader"}: c.execute("UPDATE prospects SET stage=?, notes=COALESCE(?,notes), updated=? WHERE id=? AND office_id=?", (b.get("stage"), b.get("notes"), iso(), pid, oid))
            else: c.execute("UPDATE prospects SET stage=?, notes=COALESCE(?,notes), updated=? WHERE id=? AND office_id=? AND owner_id=?", (b.get("stage"), b.get("notes"), iso(), pid, oid, u["id"]))
        elif p == "/api/earnings":
            _earner = int(b["user_id"]) if (R & {"super_admin", "admin", "earnings_manager"} and b.get("user_id")) else u["id"]
            c.execute("INSERT INTO earnings(office_id,user_id,amount,description,date) VALUES(?,?,?,?,?)", (oid, _earner, float(b["amount"]), b.get("description", ""), b.get("date") or datetime.date.today().isoformat()))
        elif p == "/api/trainings":
            if not (R & {"super_admin", "admin", "training_head"}): c.close(); return self.send_json({"error": "Only Admins and Training Heads add training classes."}, 403)
            c.execute("INSERT INTO trainings(office_id,title,description,date,created_by) VALUES(?,?,?,?,?)", (oid, b["title"], b.get("description", ""), b.get("date", ""), u["id"]))
        elif p.startswith("/api/trainings/") and p.endswith("/complete"):
            tid = p.split("/")[-2]; c.execute("INSERT OR IGNORE INTO completions VALUES(?,?)", (tid, u["id"]))
        elif p == "/api/goals":
            c.execute("INSERT INTO goals(office_id,user_id,title,target,current,unit,deadline) VALUES(?,?,?,?,?,?,?)", (oid, u["id"], b["title"], float(b["target"]), float(b.get("current", 0)), b.get("unit", ""), b.get("deadline", "")))
        elif p.startswith("/api/goals/"):
            gid = p.split("/")[-1]
            if R & {"super_admin", "admin", "leader"}: c.execute("UPDATE goals SET current=? WHERE id=? AND office_id=?", (float(b["current"]), gid, oid))
            else: c.execute("UPDATE goals SET current=? WHERE id=? AND office_id=? AND user_id=?", (float(b["current"]), gid, oid, u["id"]))
        elif p == "/api/stepups":
            if not (R & {"super_admin", "admin", "leader"}): c.close(); return self.send_json({"error": "Only Super Admins, Admins and Team Leaders can record a Step Up."}, 403)
            c.execute("INSERT INTO stepups(office_id,user_id,new_status,prev_status,note,date,recorded_by) VALUES(?,?,?,?,?,?,?)",(oid,int(b["user_id"]),b.get("new_status",""),b.get("prev_status",""),b.get("note",""),b.get("date") or datetime.date.today().isoformat(),u["id"]))
            c.execute("INSERT INTO profiles(user_id,status) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET status=excluded.status",(int(b["user_id"]),b.get("new_status","")))
        elif p.startswith("/api/stepups/") and p.endswith("/congratulate"):
            sid=p.split("/")[-2]; c.execute("UPDATE stepups SET congrats=congrats+1 WHERE id=? AND office_id=?",(sid,oid))
        elif p.startswith("/api/stepups/") and p.endswith("/undo"):
            if not (R & {"super_admin", "admin", "leader"}): c.close(); return self.send_json({"error": "Your role does not allow undoing a Step Up."}, 403)
            sid=p.split("/")[-2]; c.execute("DELETE FROM stepups WHERE id=? AND office_id=?",(sid,oid))
        elif p == "/api/pending":
            if not (R & {"super_admin", "admin"}): c.close(); return self.send_json({"error": "Only Super Admins and Office Admins manage join requests."}, 403)
            c.execute("INSERT INTO pending_invites(office_id,name,email,phone,requested) VALUES(?,?,?,?,date('now'))",(oid,b.get("name",""),b.get("email",""),b.get("phone","")))
        elif p.startswith("/api/pending/") and p.endswith("/approve"):
            if not (R & {"super_admin", "admin"}): c.close(); return self.send_json({"error": "Only Super Admins and Office Admins approve members."}, 403)
            pid=p.split("/")[-2]; r=c.execute("SELECT * FROM pending_invites WHERE id=? AND office_id=?",(pid,oid)).fetchone()
            if r:
                _em=r["email"] or f"member{pid}@amazing.local"
                if not c.execute("SELECT 1 FROM users WHERE email=?",(_em,)).fetchone():
                    _nu=c.execute("INSERT INTO users(name,email,pw,created) VALUES(?,?,?,?)",(r["name"] or "New Member",_em,hash_pw("member1234"),iso())).lastrowid
                    c.execute("INSERT OR IGNORE INTO memberships VALUES(?,?, 'member')",(_nu,oid))
                c.execute("DELETE FROM pending_invites WHERE id=?",(pid,))
        elif p.startswith("/api/pending/") and p.endswith("/decline"):
            if not (R & {"super_admin", "admin"}): c.close(); return self.send_json({"error": "Only Super Admins and Office Admins manage join requests."}, 403)
            pid=p.split("/")[-2]; c.execute("DELETE FROM pending_invites WHERE id=? AND office_id=?",(pid,oid))
        elif p == "/api/structure/add":
            if not (R & {"super_admin", "admin", "leader"}): c.close(); return self.send_json({"error": "Only Super Admins, Admins and Team Leaders add people to the structure."}, 403)
            c.execute("INSERT INTO external_people(office_id,name,status,sponsor,location,on_app,created) VALUES(?,?,?,?,?,?,date('now'))",(oid,b.get("name",""),b.get("status","Newbie"),b.get("sponsor",""),b.get("location",""),1 if b.get("on_app") else 0))
        elif p == "/api/checklist":
            c.execute("INSERT INTO checklist(office_id,user_id,date,text,done) VALUES(?,?,?,?,0)",(oid,u["id"],b.get("date") or datetime.date.today().isoformat(),b["text"]))
        elif p.startswith("/api/checklist/"):
            cid=p.split("/")[-1]; c.execute("UPDATE checklist SET done=? WHERE id=? AND user_id=?",(1 if b.get("done") else 0,cid,u["id"]))
        elif p == "/api/resources":
            if not (R & {"super_admin", "admin", "training_head", "Tutor"}): c.close(); return self.send_json({"error": "Only Admins, Training Heads and Tutors add learning material."}, 403)
            c.execute("INSERT INTO resources(office_id,title,kind,link,created_by) VALUES(?,?,?,?,?)",(oid,b["title"],b.get("kind","Resource"),b.get("link",""),u["id"]))
        elif p == "/api/funds":
            if not (R & {"super_admin", "admin", "treasurer"}): c.close(); return self.send_json({"error": "Only Super Admins, Admins and the Treasurer record office money."}, 403)
            c.execute("INSERT INTO fund_entries(office_id,user_id,kind,amount,description,date) VALUES(?,?,?,?,?,?)",(oid,b.get("user_id") or u["id"],b.get("kind","collection"),float(b.get("amount",0)),b.get("description",""),b.get("date") or datetime.date.today().isoformat()))
        elif p == "/api/profile/photo":
            _photo = b.get("photo") or ""
            if _photo and (not _photo.startswith("data:image/") or len(_photo) > 900000): c.close(); return self.send_json({"error": "That picture is too large. Choose a smaller one."}, 400)
            c.execute("INSERT INTO profiles(user_id,phone,sponsor,status,why,photo) VALUES(?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET photo=excluded.photo", (u["id"], "", "", "Member", "", _photo))
        elif p == "/api/profile":
            c.execute("INSERT INTO profiles(user_id,phone,sponsor,status,why,photo) VALUES(?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET phone=excluded.phone,sponsor=excluded.sponsor,status=excluded.status,why=excluded.why,photo=COALESCE(excluded.photo, profiles.photo)",(u["id"],b.get("phone",""),b.get("sponsor",""),b.get("status","Member"),b.get("why",""),b.get("photo")))
            if b.get("name"): c.execute("UPDATE users SET name=? WHERE id=?",(b["name"],u["id"]))
        elif p == "/api/settings":
            if not (R & {"super_admin", "admin"}): c.close(); return self.send_json({"error": "Only Super Admins and Office Admins change office settings."}, 403)
            for k,v in (b.get("settings") or {}).items(): c.execute("INSERT INTO office_settings VALUES(?,?,?) ON CONFLICT(office_id,key) DO UPDATE SET value=excluded.value",(oid,k,str(v)))
            if b.get("office_name"): c.execute("UPDATE offices SET name=? WHERE id=?",(b["office_name"],oid))
        elif p == "/api/attendance/mark":
            if int(b.get("user_id") or u["id"]) != u["id"] and not (R & {"super_admin", "admin", "leader"}): c.close(); return self.send_json({"error": "You can only mark your own attendance. Leaders mark for others."}, 403)
            c.execute("INSERT OR REPLACE INTO attendance(office_id,user_id,date,status,note,session,check_in) VALUES(?,?,?,?,?,?,time('now'))",(oid,int(b["user_id"]),b.get("date") or datetime.date.today().isoformat(),b.get("status","present"),b.get("note","manual override"),b.get("session","Office hours")))
        elif p.startswith("/api/members/") and p.endswith("/status"):
            if not (R & {"super_admin", "admin"}): c.close(); return self.send_json({"error": "Only Super Admins and Office Admins change member roles."}, 403)
            mid=p.split("/")[-2]
            if b.get("status"): c.execute("INSERT INTO profiles(user_id,status) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET status=excluded.status",(mid,b["status"]))
            if isinstance(b.get("roles"), list):
                _roles = ["Tutor" if x == "trainer" else x for x in b["roles"]]
                if "super_admin" in _roles: c.close(); return self.send_json({"error": "Use Transfer Super Admin to hand over Super Admin."}, 403)
                _saved = self.save_roles(c, int(mid), oid, _roles)
                for _kind, _key in (("Tutor", "tutor_classes"), ("training_head", "head_classes")):
                    c.execute("DELETE FROM training_assignments WHERE user_id=? AND office_id=? AND kind=?", (int(mid), oid, _kind))
                    if _kind in _saved:
                        for _tid in (b.get(_key) or []):
                            if c.execute("SELECT 1 FROM trainings WHERE id=? AND office_id=?", (int(_tid), oid)).fetchone():
                                c.execute("INSERT OR IGNORE INTO training_assignments(training_id,user_id,office_id,kind) VALUES(?,?,?,?)", (int(_tid), int(mid), oid, _kind))
            elif b.get("role") in ("super_admin", "admin", "leader", "treasurer", "earnings_manager", "Tutor", "training_head", "trainer", "member"):
                _one = "Tutor" if b["role"] == "trainer" else b["role"]
                if _one == "super_admin" and "super_admin" not in R: c.close(); return self.send_json({"error": "Only the current Super Admin can hand over Super Admin."}, 403)
                if _one == "super_admin" and int(mid) != u["id"]:
                    self.save_roles(c, u["id"], oid, ["admin"])
                self.save_roles(c, int(mid), oid, [] if _one == "member" else [_one])
        elif p == "/api/ai/reply":
            c.close(); return self.send_json(ai_replies(b.get("situation", ""), b.get("name", "")))
        elif p == "/api/billing/select-plan":
            if "super_admin" not in R: c.close(); return self.send_json({"error": "Only the Super Admin manages the office plan."}, 403)
            c.execute("UPDATE offices SET plan='free', pro=1, next_billing=NULL WHERE id=?", (oid,))
            c.commit(); c.close(); return self.send_json({"ok": True, "message": "Free Forever is already active, unlimited members, no payment needed."})
        elif p == "/api/offices/link":
            _link_roles = self.role_set(c, u["id"], self.headers.get("X-Office-Id"))
            if not (set(_link_roles) & {"super_admin", "admin"}): c.close(); return self.send_json({"error": "Only Super Admins and Office Admins link offices."}, 403)
            target = c.execute("SELECT * FROM offices WHERE slug=?", ((b.get("slug") or "").lower(),)).fetchone()
            if not target: c.close(); return self.send_json({"error": "Office not found"}, 404)
            cur_off = self.headers.get("X-Office-Id"); c.execute("INSERT OR IGNORE INTO office_links VALUES(?,?)", (cur_off, target["id"]))
        else:
            c.close(); return self.send_json({"error": "Not found"}, 404)
        c.commit(); c.close(); return self.send_json({"ok": True})

    def login_user(self, uid):
        tok = secrets.token_urlsafe(32); c = db(); c.execute("INSERT INTO sessions VALUES(?,?,?)", (tok, uid, iso())); c.commit(); c.close()
        return self.send_json({"ok": True}, cookie=f"session={tok}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000")

    def admin_get(self, p):
        if p == "/api/admin/me":
            a = self.admin()
            if not a: return self.send_json({"error": "Admin sign in required"}, 401)
            return self.send_json({"admin": {"id": a["id"], "name": a["name"], "email": a["email"]}})
        a = self.admin()
        if not a: return self.send_json({"error": "Admin sign in required"}, 401)
        c = db()
        if p == "/api/admin/overview":
            data = {
              "offices": c.execute("SELECT COUNT(*) n FROM offices").fetchone()["n"],
              "suspendedOffices": c.execute("SELECT COUNT(*) n FROM offices WHERE COALESCE(suspended,0)=1").fetchone()["n"],
              "users": c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"],
              "memberships": c.execute("SELECT COUNT(*) n FROM memberships").fetchone()["n"],
              "prospects": c.execute("SELECT COUNT(*) n FROM prospects").fetchone()["n"],
              "attendanceToday": c.execute("SELECT COUNT(*) n FROM attendance WHERE date=date('now')").fetchone()["n"],
              "earningsTotal": c.execute("SELECT COALESCE(SUM(amount),0) s FROM earnings").fetchone()["s"],
              "stepups": c.execute("SELECT COUNT(*) n FROM stepups").fetchone()["n"],
              "pending": c.execute("SELECT COUNT(*) n FROM pending_invites").fetchone()["n"],
              "trainings": c.execute("SELECT COUNT(*) n FROM trainings").fetchone()["n"],
              "resources": c.execute("SELECT COUNT(*) n FROM resources").fetchone()["n"],
              "fundEntries": c.execute("SELECT COUNT(*) n FROM fund_entries").fetchone()["n"],
              "recentOffices": [dict(x) for x in c.execute("SELECT o.*, (SELECT COUNT(*) FROM memberships WHERE office_id=o.id) members FROM offices o ORDER BY o.id DESC LIMIT 6")],
              "recentUsers": [dict(x) for x in c.execute("SELECT id,name,email,created FROM users ORDER BY id DESC LIMIT 6")],
              "stageCounts": {r["stage"]: r["n"] for r in c.execute("SELECT stage, COUNT(*) n FROM prospects GROUP BY stage")},
            }; c.close(); return self.send_json(data)
        if p == "/api/admin/offices":
            rows = c.execute("""SELECT o.*, u.name owner_name, u.email owner_email,
              (SELECT COUNT(*) FROM memberships WHERE office_id=o.id) members,
              (SELECT COUNT(*) FROM prospects WHERE office_id=o.id) prospects,
              (SELECT COUNT(*) FROM attendance WHERE office_id=o.id) checkins,
              (SELECT COALESCE(SUM(amount),0) FROM earnings WHERE office_id=o.id) earnings
              FROM offices o LEFT JOIN users u ON u.id=o.owner_id ORDER BY o.id DESC""").fetchall(); c.close(); return self.send_json({"items": [dict(x) for x in rows]})
        if p == "/api/admin/users":
            rows = c.execute("""SELECT u.id,u.name,u.email,u.created,COALESCE(u.suspended,0) suspended,
              (SELECT COUNT(*) FROM memberships WHERE user_id=u.id) offices,
              (SELECT GROUP_CONCAT(o.name) FROM memberships m JOIN offices o ON o.id=m.office_id WHERE m.user_id=u.id) office_names,
              (SELECT m.role FROM memberships m WHERE m.user_id=u.id LIMIT 1) role
              FROM users u ORDER BY u.id DESC""").fetchall(); c.close(); return self.send_json({"items": [dict(x) for x in rows]})
        if p == "/api/admin/activity":
            ev = []
            for r in c.execute("SELECT p.name, p.stage, p.created, o.name office FROM prospects p JOIN offices o ON o.id=p.office_id ORDER BY p.id DESC LIMIT 10"): ev.append({"kind": "Prospect", "text": f"{r['name']} moved to {r['stage']}", "office": r["office"], "when": r["created"]})
            for r in c.execute("SELECT e.amount, e.date, u.name, o.name office FROM earnings e JOIN users u ON u.id=e.user_id JOIN offices o ON o.id=e.office_id ORDER BY e.id DESC LIMIT 10"): ev.append({"kind": "Earnings", "text": f"{r['name']} logged {r['amount']}", "office": r["office"], "when": r["date"]})
            for r in c.execute("SELECT s.new_status, s.date, u.name, o.name office FROM stepups s JOIN users u ON u.id=s.user_id JOIN offices o ON o.id=s.office_id ORDER BY s.id DESC LIMIT 10"): ev.append({"kind": "Step Up", "text": f"{r['name']} stepped up to {r['new_status']}", "office": r["office"], "when": r["date"]})
            for r in c.execute("SELECT a.date, u.name, o.name office FROM attendance a JOIN users u ON u.id=a.user_id JOIN offices o ON o.id=a.office_id ORDER BY a.id DESC LIMIT 10"): ev.append({"kind": "Attendance", "text": f"{r['name']} checked in", "office": r["office"], "when": r["date"]})
            c.close(); return self.send_json({"items": ev[:24]})

        if p == "/api/admin/attention":
            data = {
              "PendingApprovals": [dict(x) for x in c.execute("SELECT pi.*, o.name office FROM pending_invites pi JOIN offices o ON o.id=pi.office_id ORDER BY pi.id")],
              "notMarkedToday": [dict(x) for x in c.execute("""SELECT u.id,u.name,o.name office FROM memberships m JOIN users u ON u.id=m.user_id JOIN offices o ON o.id=m.office_id
                WHERE NOT EXISTS (SELECT 1 FROM attendance a WHERE a.office_id=m.office_id AND a.user_id=m.user_id AND a.date=date('now')) ORDER BY o.name,u.name LIMIT 40""")],
              "waitingProspects": [dict(x) for x in c.execute("""SELECT p.name,p.stage,p.phone,p.updated,p.created,o.name office,u.name owner FROM prospects p JOIN offices o ON o.id=p.office_id LEFT JOIN users u ON u.id=p.owner_id
                WHERE p.stage IN ('New','Following up') ORDER BY p.updated LIMIT 25""")],
              "idleOffices": [dict(x) for x in c.execute("SELECT o.name,o.slug FROM offices o WHERE NOT EXISTS (SELECT 1 FROM attendance a WHERE a.office_id=o.id) ORDER BY o.name")],
              "topEarners": [dict(x) for x in c.execute("""SELECT u.name,o.name office,SUM(e.amount) total,COUNT(*) entries FROM earnings e JOIN users u ON u.id=e.user_id JOIN offices o ON o.id=e.office_id
                WHERE e.date>=date('now','-6 days') GROUP BY e.user_id ORDER BY total DESC LIMIT 8""")],
              "rankCounts": {r["status"]: r["n"] for r in c.execute("SELECT COALESCE(NULLIF(p.status,''),'Not set') status, COUNT(*) n FROM profiles p GROUP BY status")},
            }; c.close(); return self.send_json(data)
        if p == "/api/admin/attendance":
            rows = [dict(x) for x in c.execute("""SELECT a.date,a.status,a.session,a.check_in,a.check_out,u.name,o.name office FROM attendance a JOIN users u ON u.id=a.user_id JOIN offices o ON o.id=a.office_id ORDER BY a.id DESC LIMIT 40""")]
            byoffice = [dict(x) for x in c.execute("""SELECT o.name office, SUM(a.status='present') present, SUM(a.status='absent') absent FROM offices o LEFT JOIN attendance a ON a.office_id=o.id AND a.date=date('now') GROUP BY o.id ORDER BY present DESC""")]
            members = c.execute("SELECT COUNT(*) n FROM memberships").fetchone()["n"]
            marked = c.execute("SELECT COUNT(DISTINCT user_id) n FROM attendance WHERE date=date('now')").fetchone()["n"]
            c.close(); return self.send_json({"items": rows, "byOffice": byoffice, "members": members, "markedToday": marked})
        if p == "/api/admin/pipeline":
            stages = {r["stage"]: r["n"] for r in c.execute("SELECT stage, COUNT(*) n FROM prospects GROUP BY stage")}
            byoffice = [dict(x) for x in c.execute("SELECT o.name office, COUNT(p.id) total FROM offices o LEFT JOIN prospects p ON p.office_id=o.id GROUP BY o.id ORDER BY total DESC")]
            recent = [dict(x) for x in c.execute("SELECT p.*, o.name office, u.name owner FROM prospects p JOIN offices o ON o.id=p.office_id LEFT JOIN users u ON u.id=p.owner_id ORDER BY p.id DESC LIMIT 25")]
            c.close(); return self.send_json({"stages": stages, "byOffice": byoffice, "items": recent})
        if p == "/api/admin/money":
            offices = [dict(x) for x in c.execute("""SELECT o.name office,
              (SELECT COALESCE(SUM(amount),0) FROM earnings e WHERE e.office_id=o.id) earnings,
              (SELECT COALESCE(SUM(amount),0) FROM fund_entries f WHERE f.office_id=o.id AND f.kind='collection') collected,
              (SELECT COALESCE(SUM(amount),0) FROM fund_entries f WHERE f.office_id=o.id AND f.kind='spending') spent
              FROM offices o ORDER BY earnings DESC""")]
            top = [dict(x) for x in c.execute("SELECT u.name,o.name office,SUM(e.amount) total FROM earnings e JOIN users u ON u.id=e.user_id JOIN offices o ON o.id=e.office_id GROUP BY e.user_id ORDER BY total DESC LIMIT 10")]
            recent = [dict(x) for x in c.execute("SELECT e.id,e.amount,e.description,e.date,u.name,o.name office FROM earnings e JOIN users u ON u.id=e.user_id JOIN offices o ON o.id=e.office_id ORDER BY e.id DESC LIMIT 25")]
            funds = [dict(x) for x in c.execute("SELECT f.*,u.name,o.name office FROM fund_entries f LEFT JOIN users u ON u.id=f.user_id JOIN offices o ON o.id=f.office_id ORDER BY f.id DESC LIMIT 25")]
            c.close(); return self.send_json({"offices": offices, "top": top, "items": recent, "funds": funds})
        if p == "/api/admin/stepups":
            rows = [dict(x) for x in c.execute("SELECT s.*,u.name,o.name office FROM stepups s JOIN users u ON u.id=s.user_id JOIN offices o ON o.id=s.office_id ORDER BY s.id DESC LIMIT 40")]
            c.close(); return self.send_json({"items": rows})
        if p == "/api/admin/learning":
            tr = [dict(x) for x in c.execute("""SELECT t.title,t.description,t.date,o.name office,(SELECT COUNT(*) FROM completions cp WHERE cp.training_id=t.id) done FROM trainings t JOIN offices o ON o.id=t.office_id ORDER BY t.id DESC LIMIT 40""")]
            rs = [dict(x) for x in c.execute("SELECT r.*,o.name office FROM resources r JOIN offices o ON o.id=r.office_id ORDER BY r.id DESC LIMIT 40")]
            c.close(); return self.send_json({"trainings": tr, "resources": rs})
        if p == "/api/admin/goals":
            goals = [dict(x) for x in c.execute("SELECT g.*,u.name,o.name office FROM goals g JOIN users u ON u.id=g.user_id JOIN offices o ON o.id=g.office_id ORDER BY g.id DESC LIMIT 40")]
            checks = [dict(x) for x in c.execute("SELECT ck.text,ck.done,ck.date,u.name,o.name office FROM checklist ck JOIN users u ON u.id=ck.user_id JOIN offices o ON o.id=ck.office_id ORDER BY ck.id DESC LIMIT 30")]
            ext = [dict(x) for x in c.execute("SELECT e.*,o.name office FROM external_people e JOIN offices o ON o.id=e.office_id ORDER BY e.id DESC LIMIT 30")]
            links = c.execute("SELECT COUNT(*) n FROM office_links").fetchone()["n"]
            c.close(); return self.send_json({"goals": goals, "checks": checks, "external": ext, "links": links})
        if p.startswith("/api/admin/offices/") and p.endswith("/detail"):
            oid = p.split("/")[-2]
            off = c.execute("SELECT o.*, u.name owner_name, u.email owner_email FROM offices o LEFT JOIN users u ON u.id=o.owner_id WHERE o.id=?", (oid,)).fetchone()
            if not off: c.close(); return self.send_json({"error": "Office not found"}, 404)
            _mrows = c.execute("""SELECT u.id,u.name,u.email,m.role,p.status,p.sponsor,p.phone,COALESCE(p.photo,'') photo FROM memberships m JOIN users u ON u.id=m.user_id LEFT JOIN profiles p ON p.user_id=u.id WHERE m.office_id=? ORDER BY u.name""", (oid,)).fetchall()
            members = []
            for _x in _mrows:
                _d = dict(_x); _rs = self.role_set(c, _d["id"], int(oid)); _d["roles"] = _rs; _d["role"] = self.primary_role(_rs); members.append(_d)
            settings = {r["key"]: r["value"] for r in c.execute("SELECT key,value FROM office_settings WHERE office_id=?", (oid,))}
            stats = {"prospects": c.execute("SELECT COUNT(*) n FROM prospects WHERE office_id=?", (oid,)).fetchone()["n"],
                     "checkins": c.execute("SELECT COUNT(*) n FROM attendance WHERE office_id=?", (oid,)).fetchone()["n"],
                     "earnings": c.execute("SELECT COALESCE(SUM(amount),0) s FROM earnings WHERE office_id=?", (oid,)).fetchone()["s"]}
            c.close(); return self.send_json({"office": dict(off), "members": members, "settings": settings, "stats": stats})
        if p == "/api/admin/system":
            import os as _os
            tables = {}
            for (name,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
                try: tables[name] = c.execute(f"SELECT COUNT(*) FROM \"{name}\"").fetchone()[0]
                except Exception: tables[name] = 0
            size = _os.path.getsize(DB) if _os.path.exists(DB) else 0
            admins = [dict(x) for x in c.execute("SELECT id,name,email,created FROM platform_admins ORDER BY id")]
            audit = [dict(x) for x in c.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 20")]
            settings = {r["key"]: r["value"] for r in c.execute("SELECT key,value FROM platform_settings")}
            c.close(); return self.send_json({"dbBytes": size, "tables": tables, "admins": admins, "audit": audit, "settings": settings, "app": CONFIG})
        if p == "/api/admin/export":
            out = {}
            for (name,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
                if name in ("sessions", "admin_sessions"): continue
                cols = [r[1] for r in c.execute(f"PRAGMA table_info(\"{name}\")") if r[1] != "pw"]
                if not cols: continue
                out[name] = [dict(zip(cols, row)) for row in c.execute(f"SELECT {','.join(cols)} FROM \"{name}\"")]
            c.close(); body = json.dumps({"exported": iso(), "data": out}, indent=1).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Disposition", "attachment; filename=theamazingteamos-backup.json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        c.close(); return self.send_json({"error": "Not found"}, 404)

    def admin_write(self, p, b):
        c = db()
        if p == "/api/admin/auth/login":
            r = c.execute("SELECT * FROM platform_admins WHERE email=?", (b.get("email", "").lower(),)).fetchone()
            if not r or not check_pw(b.get("password", ""), r["pw"]): c.close(); return self.send_json({"error": "Wrong admin email or password"}, 401)
            tok = secrets.token_urlsafe(32); c.execute("INSERT INTO admin_sessions VALUES(?,?,?)", (tok, r["id"], iso())); c.commit(); c.close(); self.audit(r["id"], "Admin sign in")
            body = json.dumps({"ok": True}).encode(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.send_header("Set-Cookie", f"admin_session={tok}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400"); self.end_headers(); self.wfile.write(body); return
        a = self.admin()
        if not a: c.close(); return self.send_json({"error": "Admin sign in required"}, 401)
        if p == "/api/admin/auth/logout":
            ck = SimpleCookie(self.headers.get("Cookie") or "")
            if "admin_session" in ck: c.execute("DELETE FROM admin_sessions WHERE token=?", (ck["admin_session"].value,)); c.commit()
            c.close(); return self.send_json({"ok": True}, cookie="admin_session=; Path=/; Max-Age=0")
        if p.startswith("/api/admin/offices/") and p.endswith("/suspend"):
            oid = p.split("/")[-2]; val = 1 if b.get("suspended") else 0
            c.execute("UPDATE offices SET suspended=? WHERE id=?", (val, oid)); c.commit(); c.close(); self.audit(a["id"], "Office suspended" if val else "Office reactivated", f"office {oid}"); return self.send_json({"ok": True})
        if p.startswith("/api/admin/offices/") and p.endswith("/delete"):
            oid = p.split("/")[-2]
            for tbl in ("prospects", "attendance", "earnings", "trainings", "goals", "stepups", "checklist", "resources", "fund_entries", "pending_invites", "external_people", "office_settings"):
                try: c.execute(f"DELETE FROM {tbl} WHERE office_id=?", (oid,))
                except Exception: pass
            c.execute("DELETE FROM memberships WHERE office_id=?", (oid,)); c.execute("DELETE FROM office_links WHERE office_id=? OR linked_office_id=?", (oid, oid)); c.execute("DELETE FROM offices WHERE id=?", (oid,)); c.commit(); c.close(); self.audit(a["id"], "Office deleted", f"office {oid}"); return self.send_json({"ok": True})
        if p.startswith("/api/admin/users/") and p.endswith("/suspend"):
            uid = p.split("/")[-2]; val = 1 if b.get("suspended") else 0
            c.execute("UPDATE users SET suspended=? WHERE id=?", (val, uid))
            if val: c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
            c.commit(); c.close(); self.audit(a["id"], "User suspended" if val else "User reactivated", f"user {uid}"); return self.send_json({"ok": True})
        if p.startswith("/api/admin/users/") and p.endswith("/reset-password"):
            uid = p.split("/")[-2]; temp = "Amazing" + secrets.token_hex(3) + "!"
            c.execute("UPDATE users SET pw=? WHERE id=?", (hash_pw(temp), uid)); c.execute("DELETE FROM sessions WHERE user_id=?", (uid,)); c.commit(); c.close(); self.audit(a["id"], "Password reset", f"user {uid}"); return self.send_json({"ok": True, "temporaryPassword": temp, "note": "Give this to the member once. They should change it after signing in."})

        if p.startswith("/api/admin/pending/") and (p.endswith("/approve") or p.endswith("/decline")):
            pid = p.split("/")[-2]; row = c.execute("SELECT * FROM pending_invites WHERE id=?", (pid,)).fetchone()
            if not row: c.close(); return self.send_json({"error": "Request not found"}, 404)
            if p.endswith("/decline"):
                c.execute("DELETE FROM pending_invites WHERE id=?", (pid,)); c.commit(); c.close(); self.audit(a["id"], "Join request declined", f"request {pid}"); return self.send_json({"ok": True})
            import re as _re
            if not _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", row["email"] or ""): c.close(); return self.send_json({"error": "That request has no proper email. Add the person from Members instead."}, 400)
            ex = c.execute("SELECT id FROM users WHERE email=?", (row["email"].lower(),)).fetchone()
            if ex: uid = ex["id"]
            else:
                temp = "Amazing" + secrets.token_hex(3) + "!"; c.execute("INSERT INTO users(name,email,pw,created) VALUES(?,?,?,?)", (row["name"], row["email"].lower(), hash_pw(temp), iso())); uid = c.execute("SELECT last_insert_rowid() x").fetchone()["x"]
            c.execute("INSERT OR IGNORE INTO memberships VALUES(?,?,?)", (uid, row["office_id"], "member"))
            c.execute("INSERT OR REPLACE INTO profiles(user_id,phone,sponsor,status,why) VALUES(?,?,?,?,?)", (uid, row["phone"] or "", "", "Newbie", ""))
            c.execute("DELETE FROM pending_invites WHERE id=?", (pid,)); c.commit(); c.close(); self.audit(a["id"], "Join request approved", f"request {pid}"); return self.send_json({"ok": True})
        if p.startswith("/api/admin/earnings/") and p.endswith("/delete"):
            eid = p.split("/")[-2]; c.execute("DELETE FROM earnings WHERE id=?", (eid,)); c.commit(); c.close(); self.audit(a["id"], "Earnings entry removed", f"entry {eid}"); return self.send_json({"ok": True})
        if p.startswith("/api/admin/stepups/") and p.endswith("/undo"):
            sid = p.split("/")[-2]; s = c.execute("SELECT * FROM stepups WHERE id=?", (sid,)).fetchone()
            if s and s["prev_status"]: c.execute("UPDATE profiles SET status=? WHERE user_id=?", (s["prev_status"], s["user_id"]))
            c.execute("DELETE FROM stepups WHERE id=?", (sid,)); c.commit(); c.close(); self.audit(a["id"], "Step Up undone", f"stepup {sid}"); return self.send_json({"ok": True})
        if p.startswith("/api/admin/members/") and p.endswith("/update"):
            parts = p.split("/"); oid, uid = parts[-3], parts[-2]
            if b.get("role") is not None and b["role"] in ("super_admin", "admin", "leader", "treasurer", "earnings_manager", "Tutor", "training_head", "trainer", "member"):
                _one = "Tutor" if b["role"] == "trainer" else b["role"]
                self.save_roles(c, int(uid), int(oid), [] if _one == "member" else [_one])
            if b.get("status") is not None:
                c.execute("INSERT INTO profiles(user_id,phone,sponsor,status,why) VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET status=excluded.status", (uid, "", "", b["status"], ""))
            c.commit(); c.close(); self.audit(a["id"], "Member updated", f"user {uid} in office {oid}"); return self.send_json({"ok": True})
        if p == "/api/admin/broadcast-resource":
            offs = c.execute("SELECT id FROM offices WHERE COALESCE(suspended,0)=0").fetchall()
            for o in offs: c.execute("INSERT INTO resources(office_id,title,kind,link,created_by) VALUES(?,?,?,?,?)", (o["id"], b["title"], b.get("kind", "Learning Resource"), b.get("link", ""), a["id"]))
            c.commit(); c.close(); self.audit(a["id"], "Resource sent to all offices", b.get("title", "")); return self.send_json({"ok": True, "offices": len(offs)})
        if p == "/api/admin/settings":
            for k, v in (b.get("settings") or {}).items(): c.execute("INSERT INTO platform_settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))
            c.commit(); c.close(); self.audit(a["id"], "Platform settings saved"); return self.send_json({"ok": True})
        if p == "/api/admin/admins":
            if c.execute("SELECT 1 FROM platform_admins WHERE email=?", (b["email"].lower(),)).fetchone(): c.close(); return self.send_json({"error": "That admin email already exists"}, 400)
            c.execute("INSERT INTO platform_admins(name,email,pw,created) VALUES(?,?,?,?)", (b["name"], b["email"].lower(), hash_pw(b["password"]), iso())); c.commit(); c.close(); self.audit(a["id"], "Admin created", b["email"]); return self.send_json({"ok": True})
        if p.startswith("/api/admin/admins/") and p.endswith("/password"):
            aid = p.split("/")[-2]; c.execute("UPDATE platform_admins SET pw=? WHERE id=?", (hash_pw(b["password"]), aid)); c.commit(); c.close(); self.audit(a["id"], "Admin password changed", f"admin {aid}"); return self.send_json({"ok": True})
        c.close(); return self.send_json({"error": "Not found"}, 404)

if __name__ == "__main__":
    init(); print(f"TheAmazingTeamOs running on 0.0.0.0:{PORT}"); ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
