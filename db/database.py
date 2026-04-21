import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "lvt.db")

RECIPE = {
    "ПВХ-Смола (6359)": 75.00,
    "Мел-100": 225.00,
    "Вторичное сырьё": 100.00,   # изм. 150 → 100
    "DOTP": 28.00,
    "Стабилизатор CaZn Китай": 4.00,
    "Висковакс DL-60": 0.95,
    "Пластовакс 220": 1.10,
    "Краска": 0.01,               # изм. 0.30 → 0.01
    # Дробленка — убрана
}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    # ── АВТОРИЗАЦИЯ ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS authorized_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER UNIQUE NOT NULL,
            name TEXT,
            username TEXT,
            role TEXT NOT NULL,
            authorized_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS access_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # Дефолтные коды — поменяй после деплоя через бота
    default_codes = [
        ("mix2026", "mixer"),
        ("ext2026", "extruder"),
        ("boss2026", "boss"),
    ]
    for code, role in default_codes:
        c.execute("INSERT OR IGNORE INTO access_codes (code, role) VALUES (?,?)",
                  (code, role))

    # ── ДАННЫЕ ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS mixer_shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            shift TEXT NOT NULL,
            operator TEXT NOT NULL,
            batches INTEGER NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS extrusion_pallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            shift TEXT NOT NULL,
            operator TEXT NOT NULL,
            line INTEGER DEFAULT 1,
            decor TEXT NOT NULL,
            length INTEGER NOT NULL,
            thickness REAL NOT NULL,
            overlay REAL NOT NULL,
            pallet_num INTEGER NOT NULL,
            qty INTEGER NOT NULL,
            defect INTEGER DEFAULT 0,
            time_str TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS shift_remarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            shift TEXT NOT NULL,
            operator TEXT NOT NULL,
            remark_type TEXT NOT NULL,
            qty INTEGER DEFAULT 0,
            reason TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS weekly_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start TEXT NOT NULL,
            decor TEXT NOT NULL,
            length INTEGER NOT NULL,
            thickness REAL NOT NULL,
            overlay REAL NOT NULL,
            plan_qty INTEGER NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS recipe (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            component TEXT NOT NULL,
            kg_per_batch REAL NOT NULL,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    if not c.execute("SELECT 1 FROM recipe LIMIT 1").fetchone():
        for comp, kg in RECIPE.items():
            c.execute("INSERT INTO recipe (component, kg_per_batch) VALUES (?,?)", (comp, kg))

    conn.commit()
    conn.close()


# ── АВТОРИЗАЦИЯ ──────────────────────────────────────────────────────────────

def check_code(code):
    conn = get_conn()
    row = conn.execute("SELECT role FROM access_codes WHERE code=?", (code.strip(),)).fetchone()
    conn.close()
    return row["role"] if row else None


def authorize_user(tg_id, name, username, role):
    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO authorized_users (tg_id, name, username, role)
        VALUES (?,?,?,?)
    """, (tg_id, name, username, role))
    conn.commit()
    conn.close()


def get_user_role(tg_id):
    conn = get_conn()
    row = conn.execute("SELECT role FROM authorized_users WHERE tg_id=?", (tg_id,)).fetchone()
    conn.close()
    return row["role"] if row else None


def get_all_users():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM authorized_users ORDER BY role, name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def revoke_user(tg_id):
    conn = get_conn()
    conn.execute("DELETE FROM authorized_users WHERE tg_id=?", (tg_id,))
    conn.commit()
    conn.close()


def get_codes():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM access_codes ORDER BY role").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_code(role, new_code):
    conn = get_conn()
    conn.execute("UPDATE access_codes SET code=? WHERE role=?", (new_code, role))
    conn.commit()
    conn.close()


# ── МИКСЕР ──────────────────────────────────────────────────────────────────

def save_mixer_shift(date, shift, operator, batches):
    conn = get_conn()
    conn.execute(
        "INSERT INTO mixer_shifts (date, shift, operator, batches) VALUES (?,?,?,?)",
        (date, shift, operator, batches)
    )
    conn.commit()
    conn.close()


def get_mixer_shifts(date=None):
    conn = get_conn()
    if date:
        rows = conn.execute(
            "SELECT * FROM mixer_shifts WHERE date=? ORDER BY shift", (date,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM mixer_shifts ORDER BY date DESC, shift LIMIT 50"
        ).fetchall()
    conn.close()
    return rows


# ── ЭКСТРУЗИЯ ────────────────────────────────────────────────────────────────

def save_pallet(date, shift, operator, decor, length, thickness, overlay,
                pallet_num, qty, defect, time_str):
    conn = get_conn()
    conn.execute("""
        INSERT INTO extrusion_pallets
        (date, shift, operator, decor, length, thickness, overlay,
         pallet_num, qty, defect, time_str)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (date, shift, operator, decor, length, thickness, overlay,
          pallet_num, qty, defect, time_str))
    conn.commit()
    conn.close()


def save_remark(date, shift, operator, remark_type, qty, reason):
    conn = get_conn()
    conn.execute("""
        INSERT INTO shift_remarks (date, shift, operator, remark_type, qty, reason)
        VALUES (?,?,?,?,?,?)
    """, (date, shift, operator, remark_type, qty, reason))
    conn.commit()
    conn.close()


def get_pallets(date=None, shift=None):
    conn = get_conn()
    q = "SELECT * FROM extrusion_pallets WHERE 1=1"
    params = []
    if date:
        q += " AND date=?"; params.append(date)
    if shift:
        q += " AND shift=?"; params.append(shift)
    q += " ORDER BY date DESC, pallet_num"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return rows


# ── ЗАДАНИЕ ──────────────────────────────────────────────────────────────────

def save_task(week_start, decor, length, thickness, overlay, plan_qty):
    conn = get_conn()
    conn.execute("""
        INSERT INTO weekly_tasks (week_start, decor, length, thickness, overlay, plan_qty)
        VALUES (?,?,?,?,?,?)
    """, (week_start, decor, length, thickness, overlay, plan_qty))
    conn.commit()
    conn.close()


def get_tasks(week_start):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM weekly_tasks WHERE week_start=? ORDER BY id", (week_start,)
    ).fetchall()
    conn.close()
    return rows


# ── ОТЧЁТ ────────────────────────────────────────────────────────────────────

def get_daily_report(date):
    conn = get_conn()

    mixer = conn.execute(
        "SELECT SUM(batches) as total, GROUP_CONCAT(operator||'('||shift||':'||batches||')') as detail "
        "FROM mixer_shifts WHERE date=?", (date,)
    ).fetchone()

    ext = conn.execute(
        "SELECT SUM(qty) as total_qty, SUM(defect) as total_defect "
        "FROM extrusion_pallets WHERE date=?", (date,)
    ).fetchone()

    by_decor = conn.execute(
        "SELECT decor, SUM(qty) as qty, SUM(defect) as defect "
        "FROM extrusion_pallets WHERE date=? GROUP BY decor", (date,)
    ).fetchall()

    remarks = conn.execute(
        "SELECT * FROM shift_remarks WHERE date=?", (date,)
    ).fetchall()

    recipe = conn.execute("SELECT * FROM recipe ORDER BY id").fetchall()

    conn.close()

    total_batches = mixer["total"] or 0
    total_kg = sum(r["kg_per_batch"] * total_batches for r in recipe)

    return {
        "date": date,
        "batches": total_batches,
        "mixer_detail": mixer["detail"] or "",
        "total_qty": ext["total_qty"] or 0,
        "total_defect": ext["total_defect"] or 0,
        "by_decor": [dict(r) for r in by_decor],
        "remarks": [dict(r) for r in remarks],
        "total_kg": round(total_kg, 2),
        "recipe": [dict(r) for r in recipe],
    }


def get_recipe():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM recipe ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_recipe(component, kg_per_batch):
    conn = get_conn()
    conn.execute(
        "UPDATE recipe SET kg_per_batch=?, updated_at=datetime('now','localtime') WHERE component=?",
        (kg_per_batch, component)
    )
    conn.commit()
    conn.close()


init_db()
