import datetime
import json
import os
import secrets
import time
from functools import wraps

import pymysql
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session
import requests
from werkzeug.security import check_password_hash

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me")
BOOT_ID = secrets.token_hex(8)  # new value every time the server starts, so old logins stop working
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")  # if set, OpenRouter is used instead of Gemini
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/auto")
OPENROUTER_FALLBACK = os.getenv("OPENROUTER_FALLBACK_MODEL")  # optional backup model id
GROQ_KEY = os.getenv("GROQ_API_KEY")  # keys starting with gsk_ ; highest priority if set
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_FALLBACK = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.3-70b-versatile")
_gemini = None


# ---------- database ----------
def connect():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"), port=int(os.getenv("DB_PORT", "3307")),
        user=os.getenv("DB_USER", "root"), password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "novaworks"), cursorclass=pymysql.cursors.DictCursor)


def query(sql, args=(), one=False):
    conn = connect()
    try:
        with conn.cursor() as c:
            c.execute(sql, args)
            return c.fetchone() if one else c.fetchall()
    finally:
        conn.close()


# ---------- auth ----------
def current_user():
    uid = session.get("uid")  # identity comes from the session only, never from the request
    if not uid or session.get("boot") != BOOT_ID:  # login from before this server start is ignored
        return None
    return query("SELECT id,name,email,role,specialization FROM users WHERE id=%s", (uid,), one=True)


def login_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        user = current_user()
        if not user:
            return jsonify(error="Please log in"), 401
        return f(user, *a, **k)
    return wrapper


@app.post("/api/login")
def login():
    d = request.get_json(silent=True) or {}
    u = query("SELECT * FROM users WHERE email=%s", (d.get("email", "").strip().lower(),), one=True)
    if not u or not check_password_hash(u["password_hash"], d.get("password", "")):
        return jsonify(error="Invalid email or password"), 401
    session["uid"] = u["id"]
    session["boot"] = BOOT_ID
    return jsonify(user={k: u[k] for k in ("id", "name", "email", "role", "specialization")})


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/me")
@login_required
def me(u):
    return jsonify(user=u)


# ---------- role-based data access (enforced here, in the backend) ----------
PROJECT_SQL = """SELECT p.id, p.name, p.client_name, p.description, CAST(p.deadline AS CHAR) AS deadline,
    p.manager_id, m.name AS manager_name,
    (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id {tf}) AS task_count
    FROM projects p JOIN users m ON m.id = p.manager_id
    WHERE {where} {extra} ORDER BY p.deadline"""


def projects_for(u, pid=None):
    if u["role"] == "ADMIN":
        tf, where, args = "", "1=1", []
    elif u["role"] == "MANAGER":
        tf, where, args = "", "p.manager_id=%s", [u["id"]]
    else:  # AGENT: only projects containing their tasks, counting only their tasks
        tf = "AND t.assignee_id=%s"
        where = "p.id IN (SELECT project_id FROM tasks WHERE assignee_id=%s)"
        args = [u["id"], u["id"]]
    extra = ""
    if pid is not None:
        extra, args = "AND p.id=%s", args + [pid]
    return query(PROJECT_SQL.format(tf=tf, where=where, extra=extra), args)


TASK_SQL = """SELECT t.id, t.project_id, p.name AS project_name, t.title, t.description,
    CAST(t.deadline AS CHAR) AS deadline, t.estimated_hours, t.assignee_id, a.name AS assignee_name
    FROM tasks t JOIN users a ON a.id = t.assignee_id JOIN projects p ON p.id = t.project_id"""


@app.get("/api/projects")
@login_required
def list_projects(u):
    return jsonify(projects=projects_for(u))


@app.get("/api/projects/<int:pid>")
@login_required
def project_detail(u, pid):
    rows = projects_for(u, pid)
    if not rows:  # not found, or outside this user's permitted projects
        return jsonify(error="Project not found or access denied"), 404
    sql, args = TASK_SQL + " WHERE t.project_id=%s", [pid]
    if u["role"] == "AGENT":  # never show other agents' tasks
        sql, args = sql + " AND t.assignee_id=%s", args + [u["id"]]
    tasks = query(sql + " ORDER BY t.deadline", args)
    return jsonify(project=rows[0], tasks=tasks)


@app.get("/api/my-tasks")
@login_required
def my_tasks(u):
    if u["role"] != "AGENT":
        return jsonify(tasks=[])
    return jsonify(tasks=query(TASK_SQL + " WHERE t.assignee_id=%s ORDER BY t.deadline", (u["id"],)))


@app.get("/api/team")
@login_required
def team(u):
    return jsonify(team=query("SELECT name, role, specialization FROM users ORDER BY FIELD(role,'ADMIN','MANAGER','AGENT'), name"))


# ---------- AI transcript conversion ----------
def ask_chat(url, key, prompt, model):
    """OpenAI-compatible chat call (works for Groq and OpenRouter)."""
    r = requests.post(
        url, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}],
              "response_format": {"type": "json_object"}, "temperature": 0},
        timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"AI provider error {r.status_code}: {r.text[:300]}")
    return r.json()["choices"][0]["message"]["content"]


def ask_gemini(prompt, model):
    global _gemini
    if _gemini is None:
        from google import genai
        _gemini = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    r = _gemini.models.generate_content(
        model=model, contents=prompt,
        config={"response_mime_type": "application/json", "temperature": 0})
    return r.text


def clean_json(text):
    t = (text or "").strip()
    if t.startswith("```"):  # some models wrap JSON in a code fence
        t = t.split("\n", 1)[-1].rsplit("```", 1)[0]
    return t


def extract(transcript, directory):
    prompt = f"""You convert a meeting transcript into projects and tasks for a CRM.

RULES:
- Use only the FINAL agreed decisions. When something is corrected later (deadline, hours, owner), use the latest value and ignore the earlier one.
- Ignore rejected or excluded features. Do not create tasks for them.
- Assign managers and task owners ONLY by "id" from the DIRECTORY. Never invent people. People who are not in the directory (e.g. client contacts) must never be used.
- One task per distinct piece of work. Do not merge tasks and do not split them, even if the same person owns several.
- estimatedHours is the developer effort in hours (a number), not calendar days.
- All dates are in 2026, formatted YYYY-MM-DD.
- Keep each project and task description to one or two clear sentences.

DIRECTORY (existing people):
{json.dumps(directory)}

TRANSCRIPT:
{transcript}

Return ONLY JSON in this shape:
{{"projects":[{{"name":"","clientName":"","description":"","managerId":"","deadline":"YYYY-MM-DD",
"tasks":[{{"title":"","description":"","assigneeId":"","deadline":"YYYY-MM-DD","estimatedHours":0}}]}}]}}"""
    if GROQ_KEY:
        provider, models = "groq", [GROQ_MODEL] + ([GROQ_FALLBACK] if GROQ_FALLBACK else [])
    elif OPENROUTER_KEY:
        provider, models = "openrouter", [OPENROUTER_MODEL] + ([OPENROUTER_FALLBACK] if OPENROUTER_FALLBACK else [])
    else:
        provider, models = "gemini", [MODEL, os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.7-flash")]
    last_error = None
    for model in models:
        for attempt in range(3):
            try:
                if provider == "groq":
                    text = ask_chat("https://api.groq.com/openai/v1/chat/completions", GROQ_KEY, prompt, model)
                elif provider == "openrouter":
                    text = ask_chat("https://openrouter.ai/api/v1/chat/completions", OPENROUTER_KEY, prompt, model)
                else:
                    text = ask_gemini(prompt, model)
                return json.loads(clean_json(text))
            except Exception as e:
                last_error = e
                if any(code in str(e) for code in ("429", "500", "502", "503", "504", "UNAVAILABLE")):
                    time.sleep(2 * 2 ** attempt)  # wait 2s, 4s, 8s, then try the next model
                    continue
                raise
    raise last_error


def parse_date(v):
    try:
        return datetime.date.fromisoformat(str(v))
    except ValueError:
        return None


def validate(draft, users):
    roles = {u["id"]: u["role"] for u in users}
    projects = draft.get("projects") if isinstance(draft, dict) else None
    if not projects:
        return ["The AI found no projects in this transcript."]
    errs = []
    for i, p in enumerate(projects, 1):
        n = p.get("name") or f"Project {i}"
        for f in ("name", "clientName"):
            if not p.get(f):
                errs.append(f"{n}: missing {f}")
        if roles.get(p.get("managerId")) != "MANAGER":
            errs.append(f"{n}: manager '{p.get('managerId')}' is not a valid manager")
        pdate = parse_date(p.get("deadline"))
        if not pdate:
            errs.append(f"{n}: invalid project deadline '{p.get('deadline')}'")
        for t in p.get("tasks") or []:
            tn = f"{n} / {t.get('title') or 'untitled task'}"
            if not t.get("title"):
                errs.append(f"{tn}: missing title")
            if roles.get(t.get("assigneeId")) != "AGENT":
                errs.append(f"{tn}: assignee '{t.get('assigneeId')}' is not a valid agent")
            try:
                if float(t.get("estimatedHours")) <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                errs.append(f"{tn}: estimated hours must be a positive number")
            tdate = parse_date(t.get("deadline"))
            if not tdate:
                errs.append(f"{tn}: invalid task deadline '{t.get('deadline')}'")
            elif pdate and tdate > pdate:
                errs.append(f"{tn}: task deadline is after the project deadline")
    return errs


@app.post("/api/create-from-transcript")
@login_required
def create_from_transcript(u):
    if u["role"] != "ADMIN":
        return jsonify(error="Only the administrator can create from a transcript"), 403
    transcript = ((request.get_json(silent=True) or {}).get("transcript") or "").strip()
    if not transcript:
        return jsonify(error="Paste a meeting transcript first"), 400

    directory = query("SELECT id, name, role, skills FROM users")  # no passwords sent to the AI
    try:
        draft = extract(transcript, directory)
    except Exception as e:
        return jsonify(error=f"The AI could not process the transcript: {e}"), 502

    problems = validate(draft, directory)
    if problems:
        return jsonify(error="The AI result needs correction. Nothing was saved.", problems=problems), 422

    conn, n_tasks = connect(), 0
    try:  # all-or-nothing save
        with conn.cursor() as c:
            for p in draft["projects"]:
                c.execute("INSERT INTO projects (name,client_name,description,manager_id,deadline) VALUES (%s,%s,%s,%s,%s)",
                          (p["name"], p["clientName"], p.get("description", ""), p["managerId"], p["deadline"]))
                pid = c.lastrowid
                for t in p.get("tasks") or []:
                    c.execute("INSERT INTO tasks (project_id,title,description,assignee_id,deadline,estimated_hours) VALUES (%s,%s,%s,%s,%s,%s)",
                              (pid, t["title"], t.get("description", ""), t["assigneeId"], t["deadline"], float(t["estimatedHours"])))
                    n_tasks += 1
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify(error=f"Saving failed, nothing was saved: {e}"), 500
    finally:
        conn.close()
    return jsonify(projects=len(draft["projects"]), tasks=n_tasks)


@app.post("/api/reset")
@login_required
def reset(u):  # demo helper: clear projects/tasks before testing a modified transcript
    if u["role"] != "ADMIN":
        return jsonify(error="Admin only"), 403
    conn = connect()
    try:
        with conn.cursor() as c:
            c.execute("DELETE FROM tasks")
            c.execute("DELETE FROM projects")
        conn.commit()
    finally:
        conn.close()
    return jsonify(ok=True)


@app.errorhandler(Exception)
def handle_error(e):  # always answer API errors as JSON so the page can show the real reason
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return jsonify(error=e.description), e.code
    app.logger.exception(e)
    return jsonify(error=f"Server error: {e}"), 500


@app.get("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)