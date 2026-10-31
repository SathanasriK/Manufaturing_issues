# Manufacturing Quality AI — Agentic QMS

An enterprise-grade Agentic AI application for manufacturing quality issue management, built with React + Vite + Tailwind CSS (frontend) and Python Flask + SQLite (backend), powered by Google Gemini multi-agent AI.

---

## 🏗 Architecture

```
manufacturing-quality-ai/
├── backend/
│   ├── app.py              # Flask REST API
│   ├── database.py         # SQLite schema + demo seeding
│   ├── requirements.txt
│   ├── .env.example
│   └── agents/
│       ├── orchestrator.py          # Agent coordinator
│       ├── issue_analysis_agent.py  # Agent 1: Classification
│       ├── investigation_agent.py   # Agent 2: 5 Whys / Root Cause
│       ├── corrective_action_agent.py # Agent 3: Action generation
│       ├── evidence_agent.py        # Agent 4: Evidence verification
│       ├── recurrence_agent.py      # Agent 5: Pattern detection
│       └── gemini_client.py         # Gemini API wrapper
└── frontend/
    ├── src/
    │   ├── App.jsx
    │   ├── api/index.js
    │   ├── components/
    │   │   ├── Sidebar.jsx
    │   │   └── shared.jsx
    │   └── pages/
    │       ├── Dashboard.jsx
    │       ├── QualityIssues.jsx
    │       ├── IssueDetail.jsx
    │       ├── AIInvestigation.jsx
    │       ├── CorrectiveActions.jsx
    │       ├── EvidenceCenter.jsx
    │       ├── RecurrenceMonitoring.jsx
    │       ├── AuditTrail.jsx
    │       └── Settings.jsx
    └── tailwind.config.js
```

---

## ⚡ Quick Start (Windows PowerShell)

### 1 — Clone / Navigate to Project

```powershell
cd "C:\Users\kasab\Downloads\manufacturing-quality-ai"
```

### 2 — Backend Setup

```powershell
cd backend

# Create virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Configure environment
Copy-Item .env.example .env
# Optional: open .env and add your GEMINI_API_KEY

# Start backend
python app.py
```

Backend runs at: **http://localhost:5000**

### 3 — Frontend Setup (new terminal)

```powershell
cd "C:\Users\kasab\Downloads\manufacturing-quality-ai\frontend"

# Install dependencies (already done during setup)
npm install

# Start dev server
npm run dev
```

Frontend runs at: **http://localhost:5173**

---

## 🤖 AI Configuration

The system works in two modes:

| Mode | Behavior |
|------|----------|
| **Demo Mode** (default) | Realistic pre-built AI responses. No API key needed. |
| **Gemini AI Mode** | Real multi-agent workflow via Gemini 1.5 Flash. |

To enable real AI:
1. Get a key from [Google AI Studio](https://aistudio.google.com)
2. Edit `backend/.env`:
   ```
   GEMINI_API_KEY=your_actual_key_here
   ```
3. Restart the Flask backend

---

## 🎭 Demo Scenario — Machine Overheating

The pre-loaded demo data includes a complete workflow for:

**Issue**: Machine overheating on Production Line 2 causing defective components.

- ✅ AI Classification: Machine Failure, High severity
- ✅ 5 Whys Investigation: Cooling system failure chain
- ✅ 4 Root Cause Hypotheses (labeled as unverified)
- ✅ 5 Corrective Actions generated
- ✅ Audit trail from creation to investigation
- ✅ Evidence verification workflow ready

---

## 🧩 Multi-Agent Workflow

```
Employee submits issue
        ↓
[Agent 1] Issue Analysis Agent — Classifies, assesses severity
        ↓
[Agent 5] Recurrence Monitoring Agent — Checks historical patterns
        ↓
[Agent 2] Root Cause Investigation Agent — 5 Whys + hypotheses
        ↓
[Agent 3] Corrective Action Agent — Generates action tasks
        ↓
Human Manager reviews & assigns tasks
        ↓
Employees complete assigned tasks + upload evidence
        ↓
[Agent 4] Evidence Verification Agent — Checks completeness
        ↓
Human Inspector verifies → Manager approves closure
```

---

## 🔒 Safety Rules (Enforced)

- AI cannot independently close or approve issues
- All AI root causes labeled as hypotheses until human-verified
- Critical issues trigger mandatory escalation alerts
- Evidence AI checks file presence only — human must verify content
- Complete audit trail maintained for all operations

---

## 📊 Database Tables

| Table | Purpose |
|-------|---------|
| `users` | System users with roles |
| `quality_issues` | All reported issues |
| `investigations` | 5 Whys + root causes |
| `corrective_actions` | Action tasks |
| `evidence` | Uploaded files |
| `agent_runs` | AI execution history |
| `audit_logs` | Full event timeline |
| `notifications` | In-app alerts |

---

## 🛠 Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite |
| Styling | Tailwind CSS |
| Icons | Lucide React |
| Charts | Recharts |
| Backend | Python Flask |
| Database | SQLite |
| AI | Google Gemini 1.5 Flash |
| HTTP | Axios |
| File Upload | Flask / Werkzeug |
