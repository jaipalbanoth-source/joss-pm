"""Seeds masters, the employee directory, a mock Salesforce and sample SOWs (idempotent)."""
from __future__ import annotations
from . import db
from .db import jd
from .seed_sows import SOWS
from .clock import now

ASSOCIATES = [
    # id, name, email, status, location, title, allocation already committed on other projects (%)
    ("E1001", "Jaipal Banoth", "jaipal.banoth@jadeglobal.com", "active", "Pune", "Associate Consultant", 0),
    ("E1043", "Anita Rao", "anita.rao@jadeglobal.com", "active", "Pune", "Project Manager", 20),
    ("E1051", "Vikram Desai", "vikram.desai@jadeglobal.com", "active", "Pune", "Delivery Manager", 0),
    ("E2210", "Rahul Patil", "rahul.patil@jadeglobal.com", "active", "Pune", "Senior Consultant", 40),
    ("E2211", "Rahul Sharma", "rahul.sharma@jadeglobal.com", "active", "Bengaluru", "Consultant", 0),
    ("E2215", "Priya Nair", "priya.nair@jadeglobal.com", "active", "Pune", "Technical Lead", 30),
    ("E2301", "Amit Shah", "amit.shah@jadeglobal.com", "active", "Pune", "Technical Lead", 50),
    ("E2310", "Sneha Kulkarni", "sneha.kulkarni@jadeglobal.com", "active", "Pune", "Functional Consultant", 0),
    ("E2322", "Karan Mehta", "karan.mehta@jadeglobal.com", "active", "Hyderabad", "Developer", 60),
    ("E2330", "Neha Joshi", "neha.joshi@jadeglobal.com", "active", "Pune", "Functional Consultant", 25),
    ("E2341", "Rohan Gupta", "rohan.gupta@jadeglobal.com", "active", "Bengaluru", "Developer", 0),
    ("E2350", "Divya Menon", "divya.menon@jadeglobal.com", "active", "Pune", "QA Engineer", 10),
    ("E2360", "Arjun Iyer", "arjun.iyer@jadeglobal.com", "active", "Pune", "Developer", 0),
    ("E2370", "Meera Pillai", "meera.pillai@jadeglobal.com", "active", "Chennai", "QA Engineer", 0),
    ("E2380", "Sanjay Bhatt", "sanjay.bhatt@jadeglobal.com", "active", "Pune", "Solution Architect", 35),
    ("E9001", "Suresh Kumar", "suresh.kumar@jadeglobal.com", "inactive", "Pune", "Developer", 0),
]

CUSTOMERS = [("C001", "Acme Corp Ltd", "Acme Corp Ltd"), ("C002", "Globex Corporation", "Globex Corporation"),
             ("C003", "Initech Solutions", "Initech Solutions"), ("C004", "Kestrel Media Group", "Kestrel Media Group"),
             ("C005", "Umbrella Retail Inc", "Umbrella Retail Inc")]

# Policy table (margin target %, tolerance %, auto timesheet submit, timesheet approval) -- Retainer & non-billable rows are
# assumptions until decision D5 is confirmed.
EXEC_MODELS = [
    ("Fixed Price", {"billable_default": True, "margin_target": 30, "tolerance_pct": 10, "auto_timesheet_submit": "Y", "timesheet_approval": "Y"}),
    ("T&M", {"billable_default": True, "margin_target": 25, "tolerance_pct": 15, "auto_timesheet_submit": "N", "timesheet_approval": "Y"}),
    ("Milestone", {"billable_default": True, "margin_target": 28, "tolerance_pct": 10, "auto_timesheet_submit": "Y", "timesheet_approval": "Y"}),
    ("Retainer", {"billable_default": True, "margin_target": 22, "tolerance_pct": 10, "auto_timesheet_submit": "N", "timesheet_approval": "Y"}),
    ("Internal", {"billable_default": False, "margin_target": 0, "tolerance_pct": 10, "auto_timesheet_submit": "N", "timesheet_approval": "Y"}),
    ("Investment", {"billable_default": False, "margin_target": 0, "tolerance_pct": 10, "auto_timesheet_submit": "N", "timesheet_approval": "Y"}),
]
CONTACT_ROLES = [("Project Manager", True), ("Tech Lead", True), ("Delivery Manager", True),
                 ("Functional Consultant", False), ("Technical Consultant", False), ("QA Lead", True)]
PROCESS_STATUSES = ["Draft", "In Setup", "Ready to Submit", "Active", "On Hold", "Closed"]

# level|location -> (bill rate, cost rate) per hour; used when a resource line is added by chat without rates.
RATE_CARD = {"TE1|offshore": (24, 12), "TE2|offshore": (30, 16), "TE3|offshore": (40, 21), "TE4|offshore": (48, 26),
             "TE5|offshore": (55, 30), "TE1|onshore": (55, 34), "TE2|onshore": (65, 40), "TE3|onshore": (80, 48),
             "TE4|onshore": (95, 58), "TE5|onshore": (110, 68)}

QA_PLATFORMS = {"ERP Cloud": "QA-1", "CRM": "QA-2", "Data Platform": "QA-3", "HCM": "QA-4", "Healthcare Apps": "QA-5", "ServiceNow": "QA-6"}
_QA = [  # platform, type, delivery, commercial
    ("ERP Cloud", "Implementation", "Agile", "Fixed Price"), ("ERP Cloud", "Implementation", "Hybrid", "Fixed Price"),
    ("ERP Cloud", "Implementation", "Waterfall", "Milestone"), ("ERP Cloud", "Upgrade", "Waterfall", "T&M"),
    ("ERP Cloud", "Support", "Managed", "Retainer"), ("ERP Cloud", "Migration", "Hybrid", "Milestone"),
    ("ERP Cloud", "Integration", "Agile", "T&M"), ("ERP Cloud", "Testing", "Waterfall", "T&M"),
    ("CRM", "Implementation", "Hybrid", "Milestone"), ("CRM", "Implementation", "Agile", "Fixed Price"),
    ("CRM", "Support", "Managed", "Retainer"), ("CRM", "Upgrade", "Agile", "T&M"),
    ("CRM", "Migration", "Hybrid", "Fixed Price"), ("CRM", "Integration", "Agile", "Fixed Price"),
    ("Data Platform", "Implementation", "Agile", "Fixed Price"), ("Data Platform", "Implementation", "Agile", "T&M"),
    ("Data Platform", "Migration", "Hybrid", "Milestone"), ("Data Platform", "Support", "Managed", "Retainer"),
    ("Data Platform", "Integration", "Agile", "T&M"),
    ("HCM", "Implementation", "Agile", "T&M"), ("HCM", "Implementation", "Hybrid", "Fixed Price"),
    ("HCM", "Integration", "Agile", "Fixed Price"), ("HCM", "Support", "Managed", "Retainer"),
    ("HCM", "Upgrade", "Waterfall", "T&M"), ("HCM", "Testing", "Waterfall", "T&M"),
    ("Healthcare Apps", "Upgrade", "Waterfall", "T&M"), ("Healthcare Apps", "Implementation", "Waterfall", "Milestone"),
    ("Healthcare Apps", "Support", "Managed", "Retainer"), ("Healthcare Apps", "Testing", "Agile", "T&M"),
    ("ServiceNow", "Implementation", "Agile", "Fixed Price"), ("ServiceNow", "Implementation", "Agile", "T&M"),
    ("ServiceNow", "Support", "Managed", "Retainer"), ("ServiceNow", "Integration", "Agile", "T&M"),
    ("ServiceNow", "Upgrade", "Hybrid", "Milestone"),
]


def _lines(spec, start, end):
    out = []
    for i, (role, level, loc, tech, qty, bill, cost, hours) in enumerate(spec, 1):
        out.append({"line_id": f"L{i}", "role": role, "level": level, "tier": "Tier 1" if level in ("TE4", "TE5") else "Tier 2",
                    "location": loc, "technology": tech, "qty": qty, "bill_rate": bill, "cost_rate": cost, "hours": hours,
                    "start": start, "end": end})
    return out


OPPS = [
    ("006AC00000A1001", "Acme Oracle Fusion Financials Implementation", "Acme Corp Ltd", "2026-11-01", "2027-03-31", "SOW-ACME",
     _lines([("Project Manager", "TE5", "offshore", "Oracle Fusion", 1, 55, 30, 1000), ("Technical Lead", "TE4", "offshore", "Oracle Fusion", 1, 48, 26, 1200),
             ("Functional Consultant", "TE3", "offshore", "Oracle Fusion", 3, 40, 21, 1300), ("Developer", "TE3", "offshore", "Oracle Fusion", 2, 38, 20, 1250),
             ("QA Engineer", "TE2", "offshore", "Oracle Fusion", 2, 30, 16, 1000), ("Solution Architect", "TE4", "onshore", "Oracle Fusion", 1, 85, 52, 700)],
            "2026-11-01", "2027-03-31")),
    ("006AC00000A1002", "Globex Sales Cloud Optimisation", "Globex Corporation", "2026-11-15", "2027-02-28", "SOW-GLOBEX",
     _lines([("Project Manager", "TE4", "offshore", "Salesforce", 1, 46, 25, 480), ("Developer", "TE3", "offshore", "Salesforce", 2, 38, 20, 480),
             ("Functional Consultant", "TE3", "offshore", "Salesforce", 1, 40, 21, 480), ("QA Engineer", "TE2", "offshore", "Salesforce", 1, 30, 16, 400)],
            "2026-12-01", "2027-02-28")),
    ("006AC00000A1003", "Initech HCM Managed Support", "Initech Solutions", "2026-11-01", "2027-10-31", "SOW-INITECH",
     _lines([("Project Manager", "TE4", "offshore", "Oracle HCM", 1, 44, 26, 1900), ("Functional Consultant", "TE3", "offshore", "Oracle HCM", 2, 36, 21, 1900),
             ("Technical Consultant", "TE3", "offshore", "Oracle HCM", 1, 36, 21, 1900), ("QA Engineer", "TE2", "offshore", "Oracle HCM", 1, 28, 16, 900)],
            "2026-11-01", "2027-10-31")),
    ("006AC00000A1004", "Kestrel Media Data Platform", "Kestrel Media Group", "2026-12-01", "2027-05-31", "SOW-KESTREL",
     _lines([("Project Manager", "TE4", "offshore", "Data Platform", 1, 46, 25, 960), ("Technical Lead", "TE4", "offshore", "Data Platform", 1, 50, 27, 960),
             ("Developer", "TE3", "offshore", "Data Platform", 3, 40, 21, 960), ("QA Engineer", "TE2", "offshore", "Data Platform", 1, 30, 16, 800)],
            "2026-12-01", "2027-05-31")),
    ("006AC00000A1005", "Umbrella Retail CRM Upgrade", "Umbrella Retail Inc", "2027-01-11", "2027-04-30", None,
     _lines([("Project Manager", "TE4", "offshore", "Salesforce", 1, 46, 25, 600), ("Developer", "TE3", "offshore", "Salesforce", 2, 38, 20, 600)],
            "2027-01-11", "2027-04-30")),
]


def seed():
    db.init_db()
    with db.conn() as c:
        for a in ASSOCIATES:
            c.execute("INSERT OR IGNORE INTO associates VALUES(?,?,?,?,?,?,?)", a)
        for cu in CUSTOMERS:
            c.execute("INSERT OR IGNORE INTO customers VALUES(?,?,?)", cu)
        for code, meta in EXEC_MODELS:
            c.execute("INSERT OR IGNORE INTO masters VALUES('execution_model',?,?,?)", (code, code, jd(meta)))
        for role, single in CONTACT_ROLES:
            c.execute("INSERT OR IGNORE INTO masters VALUES('contact_role',?,?,?)", (role, role, jd({"single_holder": single})))
        for s in PROCESS_STATUSES:
            c.execute("INSERT OR IGNORE INTO masters VALUES('process_status',?,?,'{}')", (s, s))
        for k, (b, co) in RATE_CARD.items():
            c.execute("INSERT OR IGNORE INTO masters VALUES('rate_card',?,?,?)", (k, k, jd({"bill_rate": b, "cost_rate": co})))
        n = 100
        for plat, prefix in QA_PLATFORMS.items():
            pass
        counters = {}
        for plat, typ, dlv, com in _QA:
            base = QA_PLATFORMS[plat]
            counters[plat] = counters.get(plat, 0) + 1
            cid = f"QA-{base[-1]}{counters[plat]:02d}"
            label = f"{plat} {typ} - {dlv} - {com}"
            c.execute("INSERT OR IGNORE INTO qa_master VALUES(?,?,?,?,?,?)", (cid, plat, typ, dlv, com, label))
        for sid, (fn, text) in SOWS.items():
            c.execute("INSERT OR IGNORE INTO sows VALUES(?,?,?,?,?)", (sid, fn, text, "salesforce-attachment", now()))
        for o in OPPS:
            c.execute("INSERT OR IGNORE INTO sf_opportunities VALUES(?,?,?,?,?,?,?,?)",
                      (o[0], o[1], o[2], o[3], o[4], o[5], jd(o[6]), "Closed Won"))
