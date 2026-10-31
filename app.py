import os
import json
import time
import sys
import io

if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

from database import get_db, init_db

app = Flask(__name__)
CORS(app, origins=["http://localhost:5173", "http://localhost:3000"])

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'xlsx', 'csv', 'txt'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def row_to_dict(row):
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows):
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
#  HEALTH / SYSTEM
# ─────────────────────────────────────────────

@app.route('/api/health', methods=['GET'])
def health():
    from agents.gemini_client import is_demo_mode
    return jsonify({
        "status": "ok",
        "demo_mode": is_demo_mode(),
        "timestamp": datetime.now().isoformat()
    })


# ─────────────────────────────────────────────
#  USERS & AUTH
# ─────────────────────────────────────────────

@app.route('/api/users', methods=['GET'])
def get_users():
    conn = get_db()
    users = rows_to_list(conn.execute("SELECT * FROM users ORDER BY name").fetchall())
    conn.close()
    return jsonify(users)


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    user_id = data.get('user_id')

    conn = get_db()
    if user_id:
        user = row_to_dict(conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())
    elif email:
        user = row_to_dict(conn.execute("SELECT * FROM users WHERE LOWER(email)=?", (email,)).fetchone())
    else:
        conn.close()
        return jsonify({"error": "Email or user ID is required"}), 400

    if not user:
        conn.close()
        return jsonify({"error": "User not found. Please register or select an existing plant user."}), 404

    # Update audit log for sign-in
    c = conn.cursor()
    c.execute("INSERT INTO audit_logs (action, description, performed_by, performed_by_type) VALUES ('User Signed In', ?, ?, 'user')",
              (f"User {user['name']} ({user['role']} - {user['department']}) signed in", user['name']))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "user": user})


@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    role = data.get('role', 'operator').strip()
    department = data.get('department', 'Production').strip()

    if not name or not email:
        return jsonify({"error": "Name and email are required"}), 400

    conn = get_db()
    existing = conn.execute("SELECT id FROM users WHERE LOWER(email)=?", (email,)).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": "A user with this email already exists"}), 409

    c = conn.cursor()
    c.execute("INSERT INTO users (name, email, role, department) VALUES (?, ?, ?, ?)",
              (name, email, role, department))
    conn.commit()
    user_id = c.lastrowid

    c.execute("INSERT INTO audit_logs (action, description, performed_by, performed_by_type) VALUES ('User Registered', ?, ?, 'user')",
              (f"New user registered: {name} ({role} - {department})", name))
    conn.commit()

    user = row_to_dict(conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())
    conn.close()
    return jsonify({"success": True, "user": user}), 201


# ─────────────────────────────────────────────
#  AI COPILOT / Q&A ASSISTANT
# ─────────────────────────────────────────────

@app.route('/api/ai/ask', methods=['POST'])
def ask_ai():
    data = request.get_json() or {}
    question = data.get('question', '').strip()
    if not question:
        return jsonify({"error": "Question is required"}), 400

    user_info = {
        "id": data.get('user_id'),
        "name": data.get('user_name', 'Operator'),
        "role": data.get('user_role', 'operator'),
        "department": data.get('user_department', 'Production')
    }

    conn = get_db()
    # Gather live context from SQLite
    all_issues = rows_to_list(conn.execute("SELECT * FROM quality_issues ORDER BY created_at DESC LIMIT 30").fetchall())
    all_actions = rows_to_list(conn.execute("SELECT * FROM corrective_actions ORDER BY priority DESC LIMIT 25").fetchall())
    
    total_issues = conn.execute("SELECT COUNT(*) FROM quality_issues").fetchone()[0]
    open_issues = conn.execute("SELECT COUNT(*) FROM quality_issues WHERE status='Open'").fetchone()[0]
    critical_issues = conn.execute("SELECT COUNT(*) FROM quality_issues WHERE severity='Critical'").fetchone()[0]
    pending_actions = conn.execute("SELECT COUNT(*) FROM corrective_actions WHERE status IN ('Pending','Assigned','In Progress')").fetchone()[0]

    db_context = {
        "issues": all_issues,
        "actions": all_actions,
        "total_issues": total_issues,
        "open_issues": open_issues,
        "critical_issues": critical_issues,
        "pending_actions": pending_actions
    }

    from agents.qa_agent import answer_quality_question
    result = answer_quality_question(question, user_info, db_context)

    # Persist Q&A to history
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS qa_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_name TEXT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            related_issues TEXT,
            suggested_actions TEXT,
            source TEXT DEFAULT 'GEMINI_AI',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()

    c.execute("""
        INSERT INTO qa_history (user_id, user_name, question, answer, related_issues, suggested_actions, source)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user_info.get("id"),
        user_info.get("name"),
        question,
        result.get("answer", ""),
        json.dumps(result.get("related_issues", [])),
        json.dumps(result.get("suggested_actions", [])),
        result.get("source", "GEMINI_AI")
    ))
    conn.commit()
    qa_id = c.lastrowid

    # Log to audit trail
    c.execute("INSERT INTO audit_logs (action, description, performed_by, performed_by_type) VALUES ('Quality AI Query', ?, ?, 'user')",
              (f"Question asked: '{question[:80]}...'", user_info.get("name", "User")))
    conn.commit()
    conn.close()

    result['id'] = qa_id
    result['created_at'] = datetime.now().isoformat()
    return jsonify(result)


@app.route('/api/ai/qa-history', methods=['GET'])
def get_qa_history():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS qa_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_name TEXT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            related_issues TEXT,
            suggested_actions TEXT,
            source TEXT DEFAULT 'GEMINI_AI',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()

    user_id = request.args.get('user_id')
    q = "SELECT * FROM qa_history"
    params = []
    if user_id:
        q += " WHERE user_id=?"
        params.append(user_id)
    q += " ORDER BY created_at DESC LIMIT 50"

    rows = rows_to_list(conn.execute(q, params).fetchall())
    conn.close()

    # Parse JSON fields
    for r in rows:
        if r.get('related_issues') and isinstance(r['related_issues'], str):
            try: r['related_issues'] = json.loads(r['related_issues'])
            except Exception: r['related_issues'] = []
        if r.get('suggested_actions') and isinstance(r['suggested_actions'], str):
            try: r['suggested_actions'] = json.loads(r['suggested_actions'])
            except Exception: r['suggested_actions'] = []

    return jsonify(rows)


# ─────────────────────────────────────────────
#  QUALITY ISSUES
# ─────────────────────────────────────────────

@app.route('/api/issues', methods=['GET'])
def get_issues():
    conn = get_db()
    q = "SELECT * FROM quality_issues WHERE 1=1"
    params = []
    severity = request.args.get('severity')
    department = request.args.get('department')
    status = request.args.get('status')
    machine = request.args.get('machine')
    search = request.args.get('search')

    if severity:
        q += " AND severity=?"; params.append(severity)
    if department:
        q += " AND department=?"; params.append(department)
    if status:
        q += " AND status=?"; params.append(status)
    if machine:
        q += " AND machine LIKE ?"; params.append(f"%{machine}%")
    if search:
        q += " AND (title LIKE ? OR description LIKE ?)"; params += [f"%{search}%", f"%{search}%"]

    q += " ORDER BY created_at DESC"
    issues = rows_to_list(conn.execute(q, params).fetchall())
    conn.close()
    return jsonify(issues)


@app.route('/api/issues/<int:issue_id>', methods=['GET'])
def get_issue(issue_id):
    conn = get_db()
    issue = row_to_dict(conn.execute("SELECT * FROM quality_issues WHERE id=?", (issue_id,)).fetchone())
    if not issue:
        conn.close()
        return jsonify({"error": "Issue not found"}), 404

    issue['investigation'] = row_to_dict(conn.execute("SELECT * FROM investigations WHERE issue_id=?", (issue_id,)).fetchone())
    issue['corrective_actions'] = rows_to_list(conn.execute("SELECT * FROM corrective_actions WHERE issue_id=? ORDER BY priority DESC", (issue_id,)).fetchall())
    issue['evidence'] = rows_to_list(conn.execute("SELECT * FROM evidence WHERE issue_id=? ORDER BY created_at DESC", (issue_id,)).fetchall())
    issue['audit_logs'] = rows_to_list(conn.execute("SELECT * FROM audit_logs WHERE issue_id=? ORDER BY created_at DESC", (issue_id,)).fetchall())

    # Parse JSON fields in investigation
    if issue['investigation']:
        for field in ['five_whys', 'root_causes', 'contributing_factors', 'inspection_steps', 'similar_issues']:
            val = issue['investigation'].get(field)
            if val and isinstance(val, str):
                try:
                    issue['investigation'][field] = json.loads(val)
                except Exception:
                    pass

    conn.close()
    return jsonify(issue)


@app.route('/api/issues', methods=['POST'])
def create_issue():
    data = request.get_json()
    required = ['title', 'description', 'department']
    for f in required:
        if not data.get(f):
            return jsonify({"error": f"'{f}' is required"}), 400

    conn = get_db()
    c = conn.cursor()

    c.execute("""INSERT INTO quality_issues 
        (title, description, department, production_line, machine, defect_category, severity, reporter_name, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Open')""",
        (data['title'], data['description'], data['department'],
         data.get('production_line'), data.get('machine'), data.get('defect_category'),
         data.get('severity', 'Medium'), data.get('reporter_name', 'Unknown')))
    conn.commit()
    issue_id = c.lastrowid

    # Audit log
    c.execute("INSERT INTO audit_logs (issue_id, action, description, performed_by, performed_by_type) VALUES (?, 'Issue Created', ?, ?, 'user')",
              (issue_id, f"Quality issue reported: {data['title']}", data.get('reporter_name', 'Unknown')))
    conn.commit()

    issue = row_to_dict(conn.execute("SELECT * FROM quality_issues WHERE id=?", (issue_id,)).fetchone())
    conn.close()
    return jsonify(issue), 201


@app.route('/api/issues/<int:issue_id>', methods=['PATCH'])
def update_issue(issue_id):
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()

    issue = row_to_dict(conn.execute("SELECT * FROM quality_issues WHERE id=?", (issue_id,)).fetchone())
    if not issue:
        conn.close()
        return jsonify({"error": "Not found"}), 404

    allowed_fields = ['title', 'description', 'severity', 'status', 'assigned_to', 'defect_category', 'machine', 'production_line', 'department']
    updates = {k: v for k, v in data.items() if k in allowed_fields}

    if 'status' in updates and updates['status'] == 'Resolved':
        updates['closed_at'] = datetime.now().isoformat()

    if updates:
        set_clause = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [issue_id]
        c.execute(f"UPDATE quality_issues SET {set_clause}, updated_at=CURRENT_TIMESTAMP WHERE id=?", values)
        conn.commit()

        if 'status' in updates:
            c.execute("INSERT INTO audit_logs (issue_id, action, description, performed_by, performed_by_type) VALUES (?, 'Status Changed', ?, ?, 'user')",
                      (issue_id, f"Status changed to: {updates['status']}", data.get('updated_by', 'System')))
            conn.commit()

    issue = row_to_dict(conn.execute("SELECT * FROM quality_issues WHERE id=?", (issue_id,)).fetchone())
    conn.close()
    return jsonify(issue)


# ─────────────────────────────────────────────
#  AI WORKFLOW
# ─────────────────────────────────────────────

@app.route('/api/issues/<int:issue_id>/analyze', methods=['POST'])
def analyze_issue(issue_id):
    conn = get_db()
    issue = row_to_dict(conn.execute("SELECT * FROM quality_issues WHERE id=?", (issue_id,)).fetchone())
    if not issue:
        conn.close()
        return jsonify({"error": "Issue not found"}), 404

    historical = rows_to_list(conn.execute(
        "SELECT * FROM quality_issues WHERE id != ? ORDER BY created_at DESC LIMIT 50", (issue_id,)
    ).fetchall())

    from agents.orchestrator import run_full_workflow
    results = run_full_workflow(issue, historical, conn)
    conn.close()
    return jsonify({"success": True, "results": results})


# ─────────────────────────────────────────────
#  INVESTIGATIONS
# ─────────────────────────────────────────────

@app.route('/api/issues/<int:issue_id>/investigation', methods=['GET'])
def get_investigation(issue_id):
    conn = get_db()
    inv = row_to_dict(conn.execute("SELECT * FROM investigations WHERE issue_id=?", (issue_id,)).fetchone())
    if inv:
        for field in ['five_whys', 'root_causes', 'contributing_factors', 'inspection_steps', 'similar_issues']:
            val = inv.get(field)
            if val and isinstance(val, str):
                try:
                    inv[field] = json.loads(val)
                except Exception:
                    pass
    conn.close()
    return jsonify(inv or {})


@app.route('/api/issues/<int:issue_id>/investigation', methods=['PATCH'])
def update_investigation(issue_id):
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()
    inv = conn.execute("SELECT * FROM investigations WHERE issue_id=?", (issue_id,)).fetchone()
    if not inv:
        conn.close()
        return jsonify({"error": "No investigation found"}), 404

    allowed = ['status', 'verified_by', 'five_whys', 'root_causes', 'contributing_factors', 'inspection_steps']
    updates = {k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in data.items() if k in allowed}
    if 'verified_by' in updates:
        updates['verified_at'] = datetime.now().isoformat()

    if updates:
        set_clause = ", ".join(f"{k}=?" for k in updates)
        c.execute(f"UPDATE investigations SET {set_clause}, updated_at=CURRENT_TIMESTAMP WHERE issue_id=?",
                  list(updates.values()) + [issue_id])
        conn.commit()
        c.execute("INSERT INTO audit_logs (issue_id, action, description, performed_by, performed_by_type) VALUES (?, 'Investigation Updated', ?, ?, 'user')",
                  (issue_id, f"Investigation updated by {data.get('updated_by', 'Unknown')}", data.get('updated_by', 'Unknown')))
        conn.commit()

    inv = row_to_dict(conn.execute("SELECT * FROM investigations WHERE issue_id=?", (issue_id,)).fetchone())
    conn.close()
    return jsonify(inv)


# ─────────────────────────────────────────────
#  CORRECTIVE ACTIONS
# ─────────────────────────────────────────────

@app.route('/api/issues/<int:issue_id>/actions', methods=['GET'])
def get_actions(issue_id):
    conn = get_db()
    actions = rows_to_list(conn.execute("SELECT * FROM corrective_actions WHERE issue_id=? ORDER BY priority DESC, created_at ASC", (issue_id,)).fetchall())
    conn.close()
    return jsonify(actions)


@app.route('/api/issues/<int:issue_id>/actions', methods=['POST'])
def create_action(issue_id):
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT INTO corrective_actions 
        (issue_id, title, description, responsible_person, responsible_department, priority, due_date, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending')""",
        (issue_id, data.get('title'), data.get('description'), data.get('responsible_person'),
         data.get('responsible_department'), data.get('priority', 'Medium'), data.get('due_date')))
    conn.commit()
    action_id = c.lastrowid
    c.execute("INSERT INTO audit_logs (issue_id, action, description, performed_by, performed_by_type) VALUES (?, 'Action Created', ?, ?, 'user')",
              (issue_id, f"Corrective action created: {data.get('title')}", data.get('created_by', 'Unknown')))
    conn.commit()
    action = row_to_dict(conn.execute("SELECT * FROM corrective_actions WHERE id=?", (action_id,)).fetchone())
    conn.close()
    return jsonify(action), 201


@app.route('/api/actions/<int:action_id>', methods=['PATCH'])
def update_action(action_id):
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()
    action = row_to_dict(conn.execute("SELECT * FROM corrective_actions WHERE id=?", (action_id,)).fetchone())
    if not action:
        conn.close()
        return jsonify({"error": "Not found"}), 404

    allowed = ['title', 'description', 'responsible_person', 'responsible_department', 'priority', 'due_date', 'status', 'completion_notes']
    updates = {k: v for k, v in data.items() if k in allowed}
    if updates.get('status') == 'Completed':
        updates['completed_at'] = datetime.now().isoformat()

    if updates:
        set_clause = ", ".join(f"{k}=?" for k in updates)
        c.execute(f"UPDATE corrective_actions SET {set_clause}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                  list(updates.values()) + [action_id])
        conn.commit()
        c.execute("INSERT INTO audit_logs (issue_id, action, description, performed_by, performed_by_type) VALUES (?, 'Action Updated', ?, ?, 'user')",
                  (action['issue_id'], f"Action '{action['title']}' updated to {updates.get('status', 'updated')}", data.get('updated_by', 'Unknown')))
        conn.commit()

    action = row_to_dict(conn.execute("SELECT * FROM corrective_actions WHERE id=?", (action_id,)).fetchone())
    conn.close()
    return jsonify(action)


@app.route('/api/actions', methods=['GET'])
def get_all_actions():
    conn = get_db()
    actions = rows_to_list(conn.execute("""
        SELECT ca.*, qi.title as issue_title, qi.severity as issue_severity 
        FROM corrective_actions ca
        JOIN quality_issues qi ON ca.issue_id = qi.id
        ORDER BY ca.priority DESC, ca.due_date ASC
    """).fetchall())
    conn.close()
    return jsonify(actions)


# ─────────────────────────────────────────────
#  EVIDENCE
# ─────────────────────────────────────────────

@app.route('/api/issues/<int:issue_id>/evidence', methods=['GET'])
def get_evidence(issue_id):
    conn = get_db()
    evidence = rows_to_list(conn.execute("SELECT * FROM evidence WHERE issue_id=? ORDER BY created_at DESC", (issue_id,)).fetchall())
    conn.close()
    return jsonify(evidence)


@app.route('/api/issues/<int:issue_id>/evidence', methods=['POST'])
def upload_evidence(issue_id):
    conn = get_db()
    issue = conn.execute("SELECT id FROM quality_issues WHERE id=?", (issue_id,)).fetchone()
    if not issue:
        conn.close()
        return jsonify({"error": "Issue not found"}), 404

    if 'file' not in request.files:
        conn.close()
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        conn.close()
        return jsonify({"error": "Invalid file type"}), 400

    filename = secure_filename(file.filename)
    ts = int(time.time())
    save_name = f"{issue_id}_{ts}_{filename}"
    save_path = os.path.join(UPLOAD_FOLDER, save_name)
    file.save(save_path)

    file_size = os.path.getsize(save_path)
    ext = filename.rsplit('.', 1)[-1].lower()
    file_type = 'image' if ext in ('png', 'jpg', 'jpeg', 'gif') else 'pdf' if ext == 'pdf' else 'document'

    c = conn.cursor()
    c.execute("""INSERT INTO evidence (issue_id, action_id, file_name, file_path, file_type, file_size, description, uploaded_by, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Uploaded')""",
        (issue_id, request.form.get('action_id'), filename, save_name, file_type, file_size,
         request.form.get('description', ''), request.form.get('uploaded_by', 'Unknown')))
    conn.commit()
    ev_id = c.lastrowid

    c.execute("INSERT INTO audit_logs (issue_id, action, description, performed_by, performed_by_type) VALUES (?, 'Evidence Uploaded', ?, ?, 'user')",
              (issue_id, f"Evidence uploaded: {filename}", request.form.get('uploaded_by', 'Unknown')))
    conn.commit()

    ev = row_to_dict(conn.execute("SELECT * FROM evidence WHERE id=?", (ev_id,)).fetchone())
    conn.close()
    return jsonify(ev), 201


@app.route('/api/uploads/<path:filename>', methods=['GET'])
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route('/api/issues/<int:issue_id>/verify-evidence', methods=['POST'])
def verify_evidence(issue_id):
    conn = get_db()
    issue = row_to_dict(conn.execute("SELECT * FROM quality_issues WHERE id=?", (issue_id,)).fetchone())
    if not issue:
        conn.close()
        return jsonify({"error": "Not found"}), 404

    evidence = rows_to_list(conn.execute("SELECT * FROM evidence WHERE issue_id=?", (issue_id,)).fetchall())
    actions = rows_to_list(conn.execute("SELECT * FROM corrective_actions WHERE issue_id=?", (issue_id,)).fetchall())

    from agents.evidence_agent import verify_evidence as ev_verify
    result = ev_verify(issue, evidence, actions)

    c = conn.cursor()
    # Update evidence statuses
    status = 'Ready for Inspection' if result.get('ready_for_human_inspection') else 'Pending Verification'
    c.execute("UPDATE evidence SET status=? WHERE issue_id=?", (status, issue_id))
    conn.commit()

    c.execute("INSERT INTO audit_logs (issue_id, action, description, performed_by, performed_by_type) VALUES (?, 'Evidence Verified by AI', ?, 'Evidence Verification Agent', 'agent')",
              (issue_id, f"Evidence completeness score: {result.get('evidence_completeness_score')}%"))
    conn.commit()

    conn.close()
    return jsonify(result)


# ─────────────────────────────────────────────
#  RECURRENCE MONITORING
# ─────────────────────────────────────────────

@app.route('/api/recurrence', methods=['GET'])
def get_recurrence():
    conn = get_db()
    issues = rows_to_list(conn.execute("SELECT * FROM quality_issues ORDER BY created_at DESC").fetchall())
    conn.close()
    from agents.recurrence_agent import analyze_recurrence
    result = analyze_recurrence(issues)
    return jsonify(result)


# ─────────────────────────────────────────────
#  AUDIT LOGS
# ─────────────────────────────────────────────

@app.route('/api/audit-logs', methods=['GET'])
def get_audit_logs():
    conn = get_db()
    issue_id = request.args.get('issue_id')
    limit = int(request.args.get('limit', 100))
    q = "SELECT al.*, qi.title as issue_title FROM audit_logs al LEFT JOIN quality_issues qi ON al.issue_id=qi.id"
    params = []
    if issue_id:
        q += " WHERE al.issue_id=?"
        params.append(issue_id)
    q += " ORDER BY al.created_at DESC LIMIT ?"
    params.append(limit)
    logs = rows_to_list(conn.execute(q, params).fetchall())
    conn.close()
    return jsonify(logs)


# ─────────────────────────────────────────────
#  NOTIFICATIONS
# ─────────────────────────────────────────────

@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    conn = get_db()
    notifications = rows_to_list(conn.execute(
        "SELECT * FROM notifications ORDER BY created_at DESC LIMIT 50"
    ).fetchall())
    conn.close()
    return jsonify(notifications)


# ─────────────────────────────────────────────
#  DASHBOARD STATS
# ─────────────────────────────────────────────

@app.route('/api/dashboard/stats', methods=['GET'])
def get_dashboard_stats():
    conn = get_db()
    c = conn.cursor()

    stats = {}
    stats['total_issues'] = c.execute("SELECT COUNT(*) FROM quality_issues").fetchone()[0]
    stats['open_issues'] = c.execute("SELECT COUNT(*) FROM quality_issues WHERE status='Open'").fetchone()[0]
    stats['critical_issues'] = c.execute("SELECT COUNT(*) FROM quality_issues WHERE severity='Critical'").fetchone()[0]
    stats['under_investigation'] = c.execute("SELECT COUNT(*) FROM quality_issues WHERE status='Under Investigation'").fetchone()[0]
    stats['pending_actions'] = c.execute("SELECT COUNT(*) FROM corrective_actions WHERE status IN ('Pending','Assigned','In Progress')").fetchone()[0]
    stats['resolved_issues'] = c.execute("SELECT COUNT(*) FROM quality_issues WHERE status IN ('Resolved','Closed')").fetchone()[0]
    stats['in_progress_issues'] = c.execute("SELECT COUNT(*) FROM quality_issues WHERE status='In Progress'").fetchone()[0]

    # Severity distribution
    rows = c.execute("SELECT severity, COUNT(*) as count FROM quality_issues GROUP BY severity").fetchall()
    stats['severity_distribution'] = [{"severity": r[0], "count": r[1]} for r in rows]

    # Department distribution
    rows = c.execute("SELECT department, COUNT(*) as count FROM quality_issues GROUP BY department ORDER BY count DESC").fetchall()
    stats['department_distribution'] = [{"department": r[0], "count": r[1]} for r in rows]

    # Category distribution
    rows = c.execute("SELECT COALESCE(ai_category, defect_category, 'Unknown') as cat, COUNT(*) as count FROM quality_issues GROUP BY cat ORDER BY count DESC").fetchall()
    stats['category_distribution'] = [{"category": r[0], "count": r[1]} for r in rows]

    # Action completion
    rows = c.execute("SELECT status, COUNT(*) as count FROM corrective_actions GROUP BY status").fetchall()
    stats['action_status_distribution'] = [{"status": r[0], "count": r[1]} for r in rows]

    # Recent issues
    rows = c.execute("SELECT * FROM quality_issues ORDER BY created_at DESC LIMIT 6").fetchall()
    stats['recent_issues'] = rows_to_list(rows)

    # Trend (issues per day, last 14 days)
    rows = c.execute("""
        SELECT date(created_at) as day, COUNT(*) as count 
        FROM quality_issues 
        WHERE created_at >= date('now', '-14 days')
        GROUP BY day ORDER BY day
    """).fetchall()
    stats['trend'] = [{"date": r[0], "count": r[1]} for r in rows]

    # Recent agent activity
    rows = c.execute("SELECT * FROM agent_runs ORDER BY created_at DESC LIMIT 10").fetchall()
    stats['recent_agent_runs'] = rows_to_list(rows)

    conn.close()
    return jsonify(stats)


@app.route('/api/agent-runs', methods=['GET'])
def get_agent_runs():
    conn = get_db()
    issue_id = request.args.get('issue_id')
    q = "SELECT * FROM agent_runs"
    params = []
    if issue_id:
        q += " WHERE issue_id=?"
        params.append(issue_id)
    q += " ORDER BY created_at DESC LIMIT 50"
    runs = rows_to_list(conn.execute(q, params).fetchall())
    conn.close()
    return jsonify(runs)


if __name__ == '__main__':
    init_db()
    print("[*] Manufacturing Quality AI - Backend starting on http://localhost:5000...")
    print("[*] Database initialized")
    from agents.gemini_client import is_demo_mode
    if is_demo_mode():
        print("[!] Running in DEMO MODE (no Gemini API key found)")
    else:
        print("[+] Gemini AI connected")
    app.run(debug=True, port=5000)
