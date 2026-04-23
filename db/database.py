"""
Dual-mode database: PostgreSQL (production) or SQLite (local fallback).
Set DATABASE_URL environment variable to use PostgreSQL.
"""
import os
from datetime import date, datetime

DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_PG = bool(DATABASE_URL)

if USE_PG:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    P = "%s"  # placeholder
    print("[DB] PostgreSQL", flush=True)
else:
    import sqlite3
    DB_PATH = os.path.join(os.path.dirname(__file__), "lvt.db")
    P = "?"
    print("[DB] SQLite (set DATABASE_URL for PostgreSQL)", flush=True)

RECIPE = {
    "ПВХ-Смола (6359)": 75.00,
    "Мел-100": 225.00,
    "Вторичное сырьё": 100.00,
    "DOTP": 28.00,
    "Стабилизатор CaZn Китай": 4.00,
    "Висковакс DL-60": 0.95,
    "Пластовакс 220": 1.10,
    "Краска": 0.01,
}


def get_conn():
    if USE_PG:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn


def sql(query):
    """Adapt SQL for SQLite if needed"""
    if not USE_PG:
        query = query.replace("%s", "?")
        query = query.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
        query = query.replace("BIGINT", "INTEGER")
        query = query.replace("DEFAULT NOW()", "DEFAULT (datetime('now','localtime'))")
        query = query.replace("NOW()", "datetime('now','localtime')")
        query = query.replace("TIMESTAMP", "TEXT")
        query = query.replace("ON CONFLICT DO NOTHING", "OR IGNORE INTO").replace("INSERT OR IGNORE INTO OR IGNORE INTO", "INSERT OR IGNORE INTO")
        query = query.replace("STRING_AGG(", "GROUP_CONCAT(")
        query = query.replace("::text", "").replace("::date", "")
        query = query.replace("NULLS LAST", "")
    return query


def row(r):
    return dict(r) if r else None


def rows(rs):
    return [dict(r) for r in rs]


def qmarks(n):
    return ",".join([P] * n)


def init_db():
    conn = get_conn(); c = conn.cursor()

    if USE_PG:
        c.execute("""
            CREATE TABLE IF NOT EXISTS authorized_users (
                id SERIAL PRIMARY KEY, tg_id BIGINT UNIQUE NOT NULL,
                name TEXT, username TEXT, role TEXT NOT NULL,
                authorized_at TIMESTAMP DEFAULT NOW())""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS access_codes (
                id SERIAL PRIMARY KEY, code TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL, created_at TIMESTAMP DEFAULT NOW())""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS mixer_shifts (
                id SERIAL PRIMARY KEY, date TEXT NOT NULL, shift TEXT NOT NULL,
                operator TEXT NOT NULL, batches INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT NOW())""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS extrusion_pallets (
                id SERIAL PRIMARY KEY, date TEXT NOT NULL, shift TEXT NOT NULL,
                operator TEXT NOT NULL, line INTEGER DEFAULT 1,
                decor TEXT NOT NULL, length INTEGER NOT NULL,
                thickness REAL NOT NULL, overlay REAL NOT NULL,
                pallet_num INTEGER NOT NULL, qty INTEGER NOT NULL,
                defect INTEGER DEFAULT 0, time_str TEXT,
                status TEXT DEFAULT 'transit', created_at TIMESTAMP DEFAULT NOW())""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS shift_remarks (
                id SERIAL PRIMARY KEY, date TEXT NOT NULL, shift TEXT NOT NULL,
                operator TEXT NOT NULL, remark_type TEXT NOT NULL,
                qty INTEGER DEFAULT 0, reason TEXT,
                created_at TIMESTAMP DEFAULT NOW())""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS lacquer_records (
                id SERIAL PRIMARY KEY,
                pallet_id INTEGER NOT NULL REFERENCES extrusion_pallets(id),
                operator TEXT NOT NULL, processed_at TIMESTAMP DEFAULT NOW())""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS weekly_tasks (
                id SERIAL PRIMARY KEY, week_start TEXT NOT NULL,
                decor TEXT NOT NULL, length INTEGER NOT NULL,
                thickness REAL NOT NULL, overlay REAL NOT NULL,
                plan_qty INTEGER NOT NULL, created_at TIMESTAMP DEFAULT NOW())""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS recipe (
                id SERIAL PRIMARY KEY, component TEXT NOT NULL,
                kg_per_batch REAL NOT NULL, updated_at TIMESTAMP DEFAULT NOW())""")
        for code, role in [("mix2026","mixer"),("ext2026","extruder"),
                           ("lac2026","lacquer"),("boss2026","boss")]:
            c.execute("INSERT INTO access_codes (code,role) VALUES (%s,%s) ON CONFLICT DO NOTHING", (code, role))
        c.execute("SELECT 1 FROM recipe LIMIT 1")
        if not c.fetchone():
            for comp, kg in RECIPE.items():
                c.execute("INSERT INTO recipe (component,kg_per_batch) VALUES (%s,%s)", (comp, kg))
    else:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS authorized_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER UNIQUE NOT NULL,
                name TEXT, username TEXT, role TEXT NOT NULL,
                authorized_at TEXT DEFAULT (datetime('now','localtime')));
            CREATE TABLE IF NOT EXISTS access_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL, created_at TEXT DEFAULT (datetime('now','localtime')));
            CREATE TABLE IF NOT EXISTS mixer_shifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, shift TEXT NOT NULL,
                operator TEXT NOT NULL, batches INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now','localtime')));
            CREATE TABLE IF NOT EXISTS extrusion_pallets (
                id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, shift TEXT NOT NULL,
                operator TEXT NOT NULL, line INTEGER DEFAULT 1,
                decor TEXT NOT NULL, length INTEGER NOT NULL,
                thickness REAL NOT NULL, overlay REAL NOT NULL,
                pallet_num INTEGER NOT NULL, qty INTEGER NOT NULL,
                defect INTEGER DEFAULT 0, time_str TEXT,
                status TEXT DEFAULT 'transit',
                created_at TEXT DEFAULT (datetime('now','localtime')));
            CREATE TABLE IF NOT EXISTS shift_remarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, shift TEXT NOT NULL,
                operator TEXT NOT NULL, remark_type TEXT NOT NULL,
                qty INTEGER DEFAULT 0, reason TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')));
            CREATE TABLE IF NOT EXISTS lacquer_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT, pallet_id INTEGER NOT NULL,
                operator TEXT NOT NULL,
                processed_at TEXT DEFAULT (datetime('now','localtime')));
            CREATE TABLE IF NOT EXISTS weekly_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT, week_start TEXT NOT NULL,
                decor TEXT NOT NULL, length INTEGER NOT NULL,
                thickness REAL NOT NULL, overlay REAL NOT NULL, plan_qty INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now','localtime')));
            CREATE TABLE IF NOT EXISTS recipe (
                id INTEGER PRIMARY KEY AUTOINCREMENT, component TEXT NOT NULL,
                kg_per_batch REAL NOT NULL,
                updated_at TEXT DEFAULT (datetime('now','localtime')));
        """)
        for code, role in [("mix2026","mixer"),("ext2026","extruder"),
                           ("lac2026","lacquer"),("boss2026","boss")]:
            c.execute("INSERT OR IGNORE INTO access_codes (code,role) VALUES (?,?)", (code, role))
        c.execute("SELECT 1 FROM recipe LIMIT 1")
        if not c.fetchone():
            for comp, kg in RECIPE.items():
                c.execute("INSERT INTO recipe (component,kg_per_batch) VALUES (?,?)", (comp, kg))

    conn.commit(); conn.close()


# ── АВТОРИЗАЦИЯ ───────────────────────────────────────────────────────────────

def check_code(code):
    conn = get_conn(); c = conn.cursor()
    c.execute(f"SELECT role FROM access_codes WHERE code={P}", (code.strip(),))
    r = c.fetchone(); conn.close()
    return r["role"] if r else None

def authorize_user(tg_id, name, username, role):
    conn = get_conn(); c = conn.cursor()
    if USE_PG:
        c.execute("""INSERT INTO authorized_users (tg_id,name,username,role) VALUES (%s,%s,%s,%s)
                     ON CONFLICT (tg_id) DO UPDATE SET name=%s,username=%s,role=%s""",
                  (tg_id,name,username,role,name,username,role))
    else:
        c.execute("INSERT OR REPLACE INTO authorized_users (tg_id,name,username,role) VALUES (?,?,?,?)",
                  (tg_id,name,username,role))
    conn.commit(); conn.close()

def get_user_role(tg_id):
    conn = get_conn(); c = conn.cursor()
    c.execute(f"SELECT role FROM authorized_users WHERE tg_id={P}", (tg_id,))
    r = c.fetchone(); conn.close()
    return r["role"] if r else None

def get_all_users():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM authorized_users ORDER BY role,name")
    rs = c.fetchall(); conn.close(); return rows(rs)

def revoke_user(tg_id):
    conn = get_conn(); c = conn.cursor()
    c.execute(f"DELETE FROM authorized_users WHERE tg_id={P}", (tg_id,))
    conn.commit(); conn.close()

def get_codes():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM access_codes ORDER BY role")
    rs = c.fetchall(); conn.close(); return rows(rs)

def update_code(role, new_code):
    conn = get_conn(); c = conn.cursor()
    c.execute(f"UPDATE access_codes SET code={P} WHERE role={P}", (new_code, role))
    conn.commit(); conn.close()


# ── МИКСЕР ────────────────────────────────────────────────────────────────────

def save_mixer_shift(d, shift, operator, batches):
    conn = get_conn(); c = conn.cursor()
    c.execute(f"INSERT INTO mixer_shifts (date,shift,operator,batches) VALUES ({P},{P},{P},{P})",
              (d, shift, operator, batches))
    conn.commit(); conn.close()

def get_mixer_shifts(d=None):
    conn = get_conn(); c = conn.cursor()
    if d:
        c.execute(f"SELECT * FROM mixer_shifts WHERE date={P} ORDER BY shift", (d,))
    else:
        c.execute("SELECT * FROM mixer_shifts ORDER BY created_at DESC LIMIT 50")
    rs = c.fetchall(); conn.close(); return rs


# ── ЭКСТРУЗИЯ ─────────────────────────────────────────────────────────────────

def save_pallet(d, shift, operator, decor, length, thickness, overlay,
                pallet_num, qty, defect, time_str):
    conn = get_conn(); c = conn.cursor()
    c.execute(f"""INSERT INTO extrusion_pallets
        (date,shift,operator,decor,length,thickness,overlay,pallet_num,qty,defect,time_str,status)
        VALUES ({P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},'transit')""",
              (d,shift,operator,decor,length,thickness,overlay,pallet_num,qty,defect,time_str))
    conn.commit(); conn.close()

def save_remark(d, shift, operator, remark_type, qty, reason):
    conn = get_conn(); c = conn.cursor()
    c.execute(f"INSERT INTO shift_remarks (date,shift,operator,remark_type,qty,reason) VALUES ({P},{P},{P},{P},{P},{P})",
              (d,shift,operator,remark_type,qty,reason))
    conn.commit(); conn.close()

def get_pallets(d=None, shift=None, status=None):
    conn = get_conn(); c = conn.cursor()
    q = "SELECT * FROM extrusion_pallets WHERE 1=1"; params = []
    if d:      q += f" AND date={P}";   params.append(d)
    if shift:  q += f" AND shift={P}";  params.append(shift)
    if status: q += f" AND status={P}"; params.append(status)
    q += " ORDER BY created_at DESC"
    c.execute(q, params); rs = c.fetchall(); conn.close(); return rs


# ── ТРАНЗИТ ───────────────────────────────────────────────────────────────────

def get_transit_pallets():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM extrusion_pallets WHERE status='transit' ORDER BY created_at ASC")
    rs = c.fetchall(); conn.close(); return rs

def get_transit_count():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM extrusion_pallets WHERE status='transit'")
    r = c.fetchone(); conn.close()
    return r["cnt"] if r else 0


# ── ЛАК ───────────────────────────────────────────────────────────────────────

def process_lacquer(pallet_id, operator):
    conn = get_conn(); c = conn.cursor()
    c.execute(f"UPDATE extrusion_pallets SET status='warehouse' WHERE id={P}", (pallet_id,))
    c.execute(f"INSERT INTO lacquer_records (pallet_id,operator) VALUES ({P},{P})", (pallet_id, operator))
    conn.commit(); conn.close()

def get_lacquer_records(limit=50):
    conn = get_conn(); c = conn.cursor()
    c.execute(f"""SELECT lr.*, ep.decor, ep.qty, ep.pallet_num, ep.date
                  FROM lacquer_records lr JOIN extrusion_pallets ep ON lr.pallet_id=ep.id
                  ORDER BY lr.processed_at DESC LIMIT {P}""", (limit,))
    rs = c.fetchall(); conn.close(); return rows(rs)


# ── СКЛАД ─────────────────────────────────────────────────────────────────────

def get_warehouse_pallets(decor=None, limit=200):
    conn = get_conn(); c = conn.cursor()
    q = """SELECT ep.*, lr.processed_at as lacquered_at, lr.operator as lac_operator
           FROM extrusion_pallets ep
           LEFT JOIN lacquer_records lr ON lr.pallet_id=ep.id
           WHERE ep.status='warehouse'"""
    params = []
    if decor: q += f" AND ep.decor={P}"; params.append(decor)
    q += f" ORDER BY lr.processed_at DESC LIMIT {P}"; params.append(limit)
    c.execute(q, params); rs = c.fetchall(); conn.close(); return rows(rs)

def get_warehouse_summary():
    conn = get_conn(); c = conn.cursor()
    c.execute("""SELECT decor, SUM(qty) as total_qty, COUNT(*) as pallets, MAX(created_at) as last_date
                 FROM extrusion_pallets WHERE status='warehouse' GROUP BY decor ORDER BY last_date DESC""")
    rs = c.fetchall(); conn.close(); return rows(rs)

def get_warehouse_total():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT SUM(qty) as total, COUNT(*) as pallets FROM extrusion_pallets WHERE status='warehouse'")
    r = c.fetchone(); conn.close()
    return row(r) or {"total": 0, "pallets": 0}


# ── ЗАДАНИЕ ───────────────────────────────────────────────────────────────────

def save_task(week_start, decor, length, thickness, overlay, plan_qty):
    conn = get_conn(); c = conn.cursor()
    c.execute(f"INSERT INTO weekly_tasks (week_start,decor,length,thickness,overlay,plan_qty) VALUES ({P},{P},{P},{P},{P},{P})",
              (week_start, decor, length, thickness, overlay, plan_qty))
    conn.commit(); conn.close()

def delete_task(task_id):
    conn = get_conn(); c = conn.cursor()
    c.execute(f"DELETE FROM weekly_tasks WHERE id={P}", (task_id,))
    conn.commit(); conn.close()

def get_tasks(week_start=None):
    conn = get_conn(); c = conn.cursor()
    if not week_start:
        c.execute("SELECT week_start FROM weekly_tasks ORDER BY id DESC LIMIT 1")
        r = c.fetchone()
        week_start = r["week_start"] if r else ""
    if not week_start:
        conn.close(); return []
    c.execute(f"SELECT * FROM weekly_tasks WHERE week_start={P} ORDER BY id", (week_start,))
    rs = c.fetchall(); conn.close(); return rs

def get_all_week_starts():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT DISTINCT week_start FROM weekly_tasks ORDER BY week_start DESC LIMIT 10")
    rs = c.fetchall(); conn.close()
    return [r["week_start"] for r in rs]


# ── ЗАДАНИЕ-ОРИЕНТИРОВАННАЯ ЭКСТРУЗИЯ ────────────────────────────────────────

def get_active_tasks():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT week_start FROM weekly_tasks ORDER BY id DESC LIMIT 1")
    latest = c.fetchone()
    if not latest:
        conn.close(); return []
    week = latest["week_start"]
    c.execute(f"SELECT * FROM weekly_tasks WHERE week_start={P} ORDER BY id", (week,))
    tasks = c.fetchall()
    result = []
    for t in tasks:
        c.execute(f"SELECT COUNT(*) as cnt, SUM(qty) as qty FROM extrusion_pallets WHERE decor={P}", (t["decor"],))
        done = c.fetchone()
        qty_done = done["qty"] or 0
        pallets_done = done["cnt"] or 0
        pallets_needed = -(-t["plan_qty"] // 150)
        result.append({
            "id": t["id"],
            "week_start": t["week_start"],
            "decor": t["decor"],
            "length": t["length"],
            "thickness": t["thickness"],
            "overlay": t["overlay"],
            "plan_qty": t["plan_qty"],
            "pallets_needed": pallets_needed,
            "done_cnt": pallets_done,
            "done_qty": qty_done,
            "pct": round(qty_done / t["plan_qty"] * 100) if t["plan_qty"] else 0,
            "done": qty_done >= t["plan_qty"],
        })
    conn.close(); return result

def complete_task_pallet(task_id, operator, qty=150):
    conn = get_conn(); c = conn.cursor()
    c.execute(f"SELECT * FROM weekly_tasks WHERE id={P}", (task_id,))
    t = c.fetchone()
    if not t:
        conn.close(); return None
    c.execute(f"SELECT COUNT(*) as cnt FROM extrusion_pallets WHERE decor={P}", (t["decor"],))
    ex = c.fetchone()
    pallet_num = (ex["cnt"] or 0) + 1
    today = date.today().strftime("%d.%m.%Y")
    time_str = datetime.now().strftime("%H:%M")
    c.execute(f"""INSERT INTO extrusion_pallets
        (date,shift,operator,decor,length,thickness,overlay,pallet_num,qty,defect,time_str,status)
        VALUES ({P},'день',{P},{P},{P},{P},{P},{P},{P},0,{P},'transit')""",
              (today,operator,t["decor"],t["length"],t["thickness"],t["overlay"],pallet_num,qty,time_str))
    c.execute(f"SELECT COUNT(*) as cnt, SUM(qty) as total FROM extrusion_pallets WHERE decor={P}", (t["decor"],))
    done = c.fetchone()
    conn.commit(); conn.close()
    return {
        "decor": t["decor"],
        "pallet_num": pallet_num,
        "done_qty": done["total"] or 0,
        "plan_qty": t["plan_qty"],
        "done_cnt": done["cnt"] or 0,
    }


# ── ОТЧЁТ ─────────────────────────────────────────────────────────────────────

def get_daily_report(date_str):
    conn = get_conn(); c = conn.cursor()

    if USE_PG:
        c.execute("SELECT SUM(batches) as total, STRING_AGG(operator||'('||shift||':'||batches::text||')',', ') as detail FROM mixer_shifts WHERE date=%s", (date_str,))
    else:
        c.execute("SELECT SUM(batches) as total, GROUP_CONCAT(operator||'('||shift||':'||batches||')') as detail FROM mixer_shifts WHERE date=?", (date_str,))
    mixer = c.fetchone()

    c.execute(f"SELECT SUM(qty) as total_qty, SUM(defect) as total_defect FROM extrusion_pallets WHERE date={P}", (date_str,))
    ext = c.fetchone()

    c.execute(f"SELECT decor, SUM(qty) as qty, SUM(defect) as defect FROM extrusion_pallets WHERE date={P} GROUP BY decor", (date_str,))
    by_decor = c.fetchall()

    c.execute(f"SELECT * FROM shift_remarks WHERE date={P}", (date_str,))
    remarks = c.fetchall()

    if USE_PG:
        c.execute("""SELECT COUNT(*) as cnt, SUM(ep.qty) as qty 
                     FROM lacquer_records lr JOIN extrusion_pallets ep ON lr.pallet_id=ep.id 
                     WHERE lr.operator IS NOT NULL AND ep.date=%s""", (date_str,))
    else:
        c.execute("SELECT COUNT(*) as cnt, SUM(ep.qty) as qty FROM lacquer_records lr JOIN extrusion_pallets ep ON lr.pallet_id=ep.id WHERE date(lr.processed_at)=?", (date_str,))
    lac = c.fetchone()

    c.execute("SELECT * FROM recipe ORDER BY id")
    recipe = c.fetchall()
    conn.close()

    total_batches = mixer["total"] or 0
    total_kg = sum(r["kg_per_batch"] * total_batches for r in recipe)
    return {
        "date": date_str, "batches": total_batches,
        "mixer_detail": mixer["detail"] or "",
        "total_qty": ext["total_qty"] or 0,
        "total_defect": ext["total_defect"] or 0,
        "by_decor": rows(by_decor),
        "remarks": rows(remarks),
        "total_kg": round(total_kg, 2),
        "recipe": rows(recipe),
        "lac_pallets": lac["cnt"] or 0,
        "lac_qty": lac["qty"] or 0,
    }


# ── РЕЦЕПТУРА ─────────────────────────────────────────────────────────────────

def get_recipe():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM recipe ORDER BY id")
    rs = c.fetchall(); conn.close(); return rows(rs)

def update_recipe(component, kg_per_batch):
    conn = get_conn(); c = conn.cursor()
    if USE_PG:
        c.execute("UPDATE recipe SET kg_per_batch=%s, updated_at=NOW() WHERE component=%s", (kg_per_batch, component))
    else:
        c.execute("UPDATE recipe SET kg_per_batch=?, updated_at=datetime('now','localtime') WHERE component=?", (kg_per_batch, component))
    conn.commit(); conn.close()


# ── EXCEL ЭКСПОРТ ─────────────────────────────────────────────────────────────

def get_full_export(date_from=None):
    conn = get_conn(); c = conn.cursor()
    q = """SELECT ep.date, ep.shift, ep.operator, ep.decor, ep.length, ep.thickness,
               ep.overlay, ep.pallet_num, ep.qty, ep.defect, ep.time_str, ep.status,
               ep.created_at, lr.operator as lac_operator, lr.processed_at as lac_date
           FROM extrusion_pallets ep
           LEFT JOIN lacquer_records lr ON lr.pallet_id=ep.id"""
    params = []
    if date_from:
        q += f" WHERE ep.date={P}"; params.append(date_from)
    q += " ORDER BY ep.created_at DESC"
    c.execute(q, params); pallets = c.fetchall()
    q2 = "SELECT * FROM mixer_shifts"
    if date_from:
        q2 += f" WHERE date={P}"; c.execute(q2, [date_from])
    else:
        c.execute(q2)
    mixer = c.fetchall()
    conn.close()
    return {"pallets": rows(pallets), "mixer": rows(mixer)}


init_db()
