import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'quality.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            role TEXT NOT NULL DEFAULT 'operator',
            department TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS quality_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            department TEXT NOT NULL,
            production_line TEXT,
            machine TEXT,
            defect_category TEXT,
            severity TEXT DEFAULT 'Medium',
            status TEXT DEFAULT 'Open',
            reporter_id INTEGER,
            reporter_name TEXT,
            assigned_to TEXT,
            ai_severity TEXT,
            ai_category TEXT,
            ai_summary TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            closed_at DATETIME,
            FOREIGN KEY (reporter_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS investigations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_id INTEGER NOT NULL,
            five_whys TEXT,
            root_causes TEXT,
            contributing_factors TEXT,
            inspection_steps TEXT,
            similar_issues TEXT,
            ai_summary TEXT,
            status TEXT DEFAULT 'In Progress',
            verified_by TEXT,
            verified_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (issue_id) REFERENCES quality_issues(id)
        );

        CREATE TABLE IF NOT EXISTS corrective_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            responsible_person TEXT,
            responsible_department TEXT,
            priority TEXT DEFAULT 'Medium',
            due_date DATE,
            status TEXT DEFAULT 'Pending',
            completion_notes TEXT,
            completed_at DATETIME,
            verified_by TEXT,
            verified_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (issue_id) REFERENCES quality_issues(id)
        );

        CREATE TABLE IF NOT EXISTS evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_id INTEGER NOT NULL,
            action_id INTEGER,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT,
            file_size INTEGER,
            description TEXT,
            uploaded_by TEXT,
            status TEXT DEFAULT 'Uploaded',
            ai_verification TEXT,
            verification_notes TEXT,
            verified_by TEXT,
            verified_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (issue_id) REFERENCES quality_issues(id),
            FOREIGN KEY (action_id) REFERENCES corrective_actions(id)
        );

        CREATE TABLE IF NOT EXISTS agent_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_id INTEGER,
            agent_name TEXT NOT NULL,
            input_data TEXT,
            output_data TEXT,
            status TEXT DEFAULT 'running',
            error_message TEXT,
            duration_ms INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (issue_id) REFERENCES quality_issues(id)
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_id INTEGER,
            action TEXT NOT NULL,
            description TEXT,
            performed_by TEXT,
            performed_by_type TEXT DEFAULT 'user',
            metadata TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (issue_id) REFERENCES quality_issues(id)
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            issue_id INTEGER,
            title TEXT NOT NULL,
            message TEXT,
            type TEXT DEFAULT 'info',
            is_read INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (issue_id) REFERENCES quality_issues(id)
        );

        CREATE TABLE IF NOT EXISTS qa_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_name TEXT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            related_issues TEXT,
            suggested_actions TEXT,
            source TEXT DEFAULT 'GEMINI_AI',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    ''')

    # Seed demo users
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        users = [
            ('John Mitchell', 'john.mitchell@factory.com', 'manager', 'Quality'),
            ('Sarah Chen', 'sarah.chen@factory.com', 'engineer', 'Production'),
            ('Mike Torres', 'mike.torres@factory.com', 'operator', 'Maintenance'),
            ('Lisa Patel', 'lisa.patel@factory.com', 'inspector', 'Quality'),
            ('David Kim', 'david.kim@factory.com', 'engineer', 'Engineering'),
        ]
        c.executemany("INSERT INTO users (name, email, role, department) VALUES (?, ?, ?, ?)", users)

    # Seed demo quality issues
    c.execute("SELECT COUNT(*) FROM quality_issues")
    if c.fetchone()[0] == 0:
        issues = [
            ('Machine Overheating - Production Line 2', 'After continuous operation, machine temperature exceeds normal range causing defective components.', 'Production', 'Line 2', 'CNC-204', 'Machine Failure', 'High', 'Under Investigation', 'Sarah Chen', 'High', 'Machine Failure', 'Machine on Production Line 2 experiencing thermal runaway after 4+ hours of operation.'),
            ('Surface Coating Defects - Batch #4421', 'Uneven coating application detected during QC inspection. Approximately 12% rejection rate on batch.', 'Quality Control', 'Line 1', 'Coater-101', 'Process Deviation', 'Medium', 'Open', 'Lisa Patel', 'Medium', 'Process Deviation', 'Coating viscosity inconsistency detected.'),
            ('Dimensional Variance in Shaft Components', 'Shaft diameters measuring 0.3mm outside tolerance on 8% of produced units.', 'Production', 'Line 3', 'Lathe-305', 'Dimensional Non-conformance', 'High', 'Open', 'Sarah Chen', 'High', 'Dimensional Non-conformance', 'Tool wear or calibration drift suspected.'),
            ('Coolant Contamination Alert', 'Coolant pH levels below acceptable range. Metal particle contamination detected.', 'Maintenance', 'Line 2', 'Coolant-System-A', 'Material Non-conformance', 'Critical', 'Open', 'Mike Torres', 'Critical', 'Material Non-conformance', 'Immediate coolant system inspection required.'),
            ('Assembly Line Stoppage - Conveyor Jam', 'Conveyor belt on Assembly Line 4 jamming intermittently causing production delays.', 'Production', 'Line 4', 'Conveyor-404', 'Equipment Failure', 'Medium', 'In Progress', 'Mike Torres', 'Medium', 'Equipment Failure', 'Mechanical obstruction in conveyor drive system.'),
            ('Weld Quality Failure - Structural Parts', 'Ultrasonic testing reveals internal voids in 15 weld joints of structural frame components.', 'Welding', 'Line 1', 'Welder-WS3', 'Process Deviation', 'Critical', 'Under Investigation', 'David Kim', 'Critical', 'Process Deviation', 'Weld parameter drift detected.'),
            ('Packaging Seal Integrity Issue', 'Vacuum seal failure rate of 6% detected during final packaging QC check.', 'Packaging', 'Line 5', 'Sealer-502', 'Process Deviation', 'Low', 'Resolved', 'Sarah Chen', 'Low', 'Process Deviation', 'Seal temperature calibration was off by 8 degrees.'),
            ('Raw Material Non-conformance - Steel Grade', 'Incoming steel batch hardness values 15% below specification. Certificate of conformance mismatch.', 'Incoming QC', 'Incoming', 'Incoming-Dock-A', 'Material Non-conformance', 'High', 'Open', 'Lisa Patel', 'High', 'Material Non-conformance', 'Supplier quality failure. Hold on incoming batch.'),
        ]
        for iss in issues:
            c.execute("""INSERT INTO quality_issues 
                (title, description, department, production_line, machine, defect_category, severity, status, reporter_name, ai_severity, ai_category, ai_summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", iss)

        conn.commit()

        # Seed investigations for first issue
        c.execute("SELECT id FROM quality_issues WHERE title LIKE 'Machine Overheating%' LIMIT 1")
        issue = c.fetchone()
        if issue:
            import json
            five_whys = json.dumps([
                {"why": "Why is the machine overheating?", "answer": "The machine temperature exceeds 85°C after 4 hours of continuous operation."},
                {"why": "Why does the temperature exceed limits?", "answer": "The cooling system is not maintaining adequate heat dissipation."},
                {"why": "Why is the cooling system inadequate?", "answer": "The coolant flow rate is reduced — possibly blocked filter or low coolant level."},
                {"why": "Why is the filter blocked?", "answer": "Preventive maintenance schedule may have been missed or the filter replacement interval is too long."},
                {"why": "Why was maintenance missed?", "answer": "No automated maintenance reminder system exists; reliance on manual logbook tracking."}
            ])
            root_causes = json.dumps([
                {"cause": "Blocked cooling filter", "confidence": "High", "type": "hypothesis"},
                {"cause": "Insufficient coolant level", "confidence": "Medium", "type": "hypothesis"},
                {"cause": "Cooling fan degradation", "confidence": "Medium", "type": "hypothesis"},
                {"cause": "Missed preventive maintenance", "confidence": "High", "type": "hypothesis"}
            ])
            inspection_steps = json.dumps([
                "Check coolant reservoir level immediately",
                "Inspect and replace cooling filter if clogged",
                "Test cooling fan operation at full speed",
                "Check temperature sensor calibration",
                "Review last 3 maintenance service records",
                "Run thermal imaging scan on machine housing"
            ])
            c.execute("""INSERT INTO investigations (issue_id, five_whys, root_causes, inspection_steps, status, ai_summary)
                VALUES (?, ?, ?, ?, 'In Progress', 'AI Investigation identified cooling system failure as primary hypothesis. Human verification required.')""",
                (issue[0], five_whys, root_causes, inspection_steps))
            conn.commit()

            inv_id = c.lastrowid
            actions = [
                (issue[0], 'Inspect cooling system and filter', 'Check coolant filter for blockage. Replace if clogged.', 'Mike Torres', 'Maintenance', 'Critical', '2026-11-05', 'In Progress'),
                (issue[0], 'Check and refill coolant levels', 'Verify coolant level meets minimum specification. Refill with approved coolant.', 'Mike Torres', 'Maintenance', 'High', '2026-11-04', 'Assigned'),
                (issue[0], 'Test cooling fan operation', 'Run cooling fan diagnostic. Check RPM against spec. Replace if below threshold.', 'David Kim', 'Engineering', 'High', '2026-11-06', 'Pending'),
                (issue[0], 'Calibrate temperature sensors', 'Verify accuracy of temperature sensors on machine. Replace if drift exceeds ±2°C.', 'David Kim', 'Engineering', 'Medium', '2026-11-07', 'Pending'),
                (issue[0], 'Run temperature stability test', 'After maintenance, run 6-hour thermal stability test with data logging.', 'Sarah Chen', 'Production', 'High', '2026-11-10', 'Pending'),
            ]
            c.executemany("""INSERT INTO corrective_actions 
                (issue_id, title, description, responsible_person, responsible_department, priority, due_date, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", actions)

        # Seed audit logs
        logs = [
            (1, 'Issue Created', 'Quality issue reported by Sarah Chen', 'Sarah Chen', 'user'),
            (1, 'AI Analysis Started', 'Issue Analysis Agent triggered automatically', 'Quality Issue Analysis Agent', 'agent'),
            (1, 'AI Classification Complete', 'Issue classified as Machine Failure, Severity: High', 'Quality Issue Analysis Agent', 'agent'),
            (1, 'Investigation Started', 'Root Cause Investigation Agent generated 5 Whys analysis', 'Root Cause Investigation Agent', 'agent'),
            (1, 'Corrective Actions Created', '5 corrective actions recommended by AI', 'Corrective Action Agent', 'agent'),
            (1, 'Action Assigned', 'Cooling system inspection assigned to Mike Torres', 'John Mitchell', 'user'),
        ]
        c.executemany("""INSERT INTO audit_logs (issue_id, action, description, performed_by, performed_by_type) 
            VALUES (?, ?, ?, ?, ?)""", logs)

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")
