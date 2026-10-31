import sys
import json
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app import app
from database import init_db, get_db

init_db()

client = app.test_client()

print("--- 1. Testing /api/health ---")
r = client.get('/api/health')
print("Status:", r.status_code, r.get_json())
assert r.status_code == 200

print("\n--- 2. Testing /api/dashboard/stats ---")
r = client.get('/api/dashboard/stats')
print("Status:", r.status_code)
stats = r.get_json()
print(f"Total issues: {stats['total_issues']}, Open: {stats['open_issues']}, Critical: {stats['critical_issues']}")
assert r.status_code == 200

print("\n--- 3. Testing /api/issues ---")
r = client.get('/api/issues')
print("Status:", r.status_code)
issues = r.get_json()
print(f"Loaded {len(issues)} issues")
assert len(issues) > 0

print("\n--- 4. Testing Demonstration Scenario: Issue #1 (Machine Overheating) ---")
r = client.get('/api/issues/1')
issue1 = r.get_json()
print("Issue #1 Title:", issue1['title'])
print("Investigation present:", bool(issue1.get('investigation')))
print("Corrective actions count:", len(issue1.get('corrective_actions', [])))
print("Audit logs count:", len(issue1.get('audit_logs', [])))
assert issue1['title'] is not None

print("\n--- 5. Testing Multi-Agent Workflow on a new issue ---")
new_issue_data = {
    "title": "Cooling Fan Stoppage - Production Line 2",
    "description": "Cooling fan stopped rotating after high heat buildup during afternoon shift.",
    "department": "Production",
    "production_line": "Line 2",
    "machine": "CNC-204",
    "defect_category": "Machine Failure",
    "severity": "High",
    "reporter_name": "Sarah Chen"
}
r = client.post('/api/issues', json=new_issue_data)
print("Create status:", r.status_code)
created_issue = r.get_json()
new_id = created_issue['id']
print("Created issue ID:", new_id)

print(f"\n--- 6. Triggering AI Workflow on Issue #{new_id} ---")
r = client.post(f'/api/issues/{new_id}/analyze')
print("Analyze status:", r.status_code)
res = r.get_json()
print("Analysis results keys:", list(res['results'].keys()))
analysis = res['results']['analysis']
print(f"Agent 1 Classification: Category={analysis.get('issue_category')}, Severity={analysis.get('severity')}")
inv = res['results']['investigation']
print(f"Agent 2 5 Whys generated: {len(inv.get('five_whys', []))} steps")
print(f"Agent 2 Root Causes: {len(inv.get('root_causes', []))} hypotheses")
actions = res['results']['corrective_actions']
print(f"Agent 3 Actions: {len(actions.get('actions', []))} recommended tasks")

print("\n--- 7. Testing Evidence Verification Agent ---")
r = client.post(f'/api/issues/{new_id}/verify-evidence')
print("Verify evidence status:", r.status_code)
ev_res = r.get_json()
print("Completeness score:", ev_res.get('evidence_completeness_score'), "%")
print("Missing evidence:", ev_res.get('evidence_missing'))
print("Ready for human inspection:", ev_res.get('ready_for_human_inspection'))
print("Disclaimer:", ev_res.get('ai_disclaimer')[:60], "...")

print("\n--- 8. Testing Recurrence Monitoring Agent ---")
r = client.get('/api/recurrence')
print("Recurrence status:", r.status_code)
rec_res = r.get_json()
print(f"Recurring patterns detected: {len(rec_res.get('recurring_patterns', []))}")
print(f"Quality health: {rec_res.get('overall_quality_health')}")

print("\n--- 9. Testing Audit Trail ---")
r = client.get(f'/api/audit-logs?issue_id={new_id}')
logs = r.get_json()
print(f"Audit log entries for issue #{new_id}: {len(logs)}")
for log in logs[:3]:
    print(f"  - [{log['performed_by_type'].upper()}] {log['action']}: {log['description']}")

print("\n✅ ALL TESTS PASSED! End-to-end agentic workflow is functioning properly.")
