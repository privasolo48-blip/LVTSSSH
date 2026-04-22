import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "lvt.db")

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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    # ── АВТОРИЗАЦИЯ ──────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS authorized_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER UNIQUE NOT NULL,
            name TEXT, username TEXT,
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
    for code, role in [("mix2026","mixer"),("ext2026","extruder"),
                       ("lac2026","lacquer"),("boss2026","boss")]:
        c.execute("INSERT OR IGNORE INTO access_codes (code,role) VALUES (?,?)",(code,role))

    # ── МИКСЕР ───────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS mixer_shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL, shift TEXT NOT NULL,
            operator TEXT NOT NULL, batches INTEGER NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # ── ЭКСТРУЗИЯ ────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS extrusion_pallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL, shift TEXT NOT NULL,
            operator TEXT NOT NULL, line INTEGER DEFAULT 1,
            decor TEXT NOT NULL, length INTEGER NOT NULL,
            thickness REAL NOT NULL, overlay REAL NOT NULL,
            pallet_num INTEGER NOT NULL,
            qty INTEGER NOT NULL, defect INTEGER DEFAULT 0,
            time_str TEXT,
            status TEXT DEFAULT 'transit',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    # Добавить колонку status если её нет (миграция)
    try:
        c.execute("ALTER TABLE extrusion_pallets ADD COLUMN status TEXT DEFAULT 'transit'")
    except Exception:
        pass

    c.execute("""
        CREATE TABLE IF NOT EXISTS shift_remarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL, shift TEXT NOT NULL,
            operator TEXT NOT NULL, remark_type TEXT NOT NULL,
            qty INTEGER DEFAULT 0, reason TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # ── ЛАК ──────────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS lacquer_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pallet_id INTEGER NOT NULL,
            operator TEXT NOT NULL,
            processed_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (pallet_id) REFERENCES extrusion_pallets(id)
        )
    """)

    # ── СКЛАД (статус меняется в extrusion_pallets: transit→lacquer→warehouse)
    # status: transit | lacquered | warehouse

    # ── ЗАДАНИЕ ──────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS weekly_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start TEXT NOT NULL, decor TEXT NOT NULL,
            length INTEGER NOT NULL, thickness REAL NOT NULL,
            overlay REAL NOT NULL, plan_qty INTEGER NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # ── РЕЦЕПТУРА ────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS recipe (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            component TEXT NOT NULL, kg_per_batch REAL NOT NULL,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    if not c.execute("SELECT 1 FROM recipe LIMIT 1").fetchone():
        for comp, kg in RECIPE.items():
            c.execute("INSERT INTO recipe (component,kg_per_batch) VALUES (?,?)",(comp,kg))

    conn.commit()
    conn.close()


# ── АВТОРИЗАЦИЯ ───────────────────────────────────────────────────────────────

def check_code(code):
    conn = get_conn()
    row = conn.execute("SELECT role FROM access_codes WHERE code=?", (code.strip(),)).fetchone()
    conn.close()
    return row["role"] if row else None

def authorize_user(tg_id, name, username, role):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO authorized_users (tg_id,name,username,role) VALUES (?,?,?,?)",
                 (tg_id, name, username, role))
    conn.commit(); conn.close()

def get_user_role(tg_id):
    conn = get_conn()
    row = conn.execute("SELECT role FROM authorized_users WHERE tg_id=?", (tg_id,)).fetchone()
    conn.close()
    return row["role"] if row else None

def get_all_users():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM authorized_users ORDER BY role,name").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def revoke_user(tg_id):
    conn = get_conn()
    conn.execute("DELETE FROM authorized_users WHERE tg_id=?", (tg_id,))
    conn.commit(); conn.close()

def get_codes():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM access_codes ORDER BY role").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_code(role, new_code):
    conn = get_conn()
    conn.execute("UPDATE access_codes SET code=? WHERE role=?", (new_code, role))
    conn.commit(); conn.close()


# ── МИКСЕР ────────────────────────────────────────────────────────────────────

def save_mixer_shift(date, shift, operator, batches):
    conn = get_conn()
    conn.execute("INSERT INTO mixer_shifts (date,shift,operator,batches) VALUES (?,?,?,?)",
                 (date, shift, operator, batches))
    conn.commit(); conn.close()

def get_mixer_shifts(date=None):
    conn = get_conn()
    if date:
        rows = conn.execute("SELECT * FROM mixer_shifts WHERE date=? ORDER BY shift",(date,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM mixer_shifts ORDER BY date DESC,shift LIMIT 50").fetchall()
    conn.close()
    return rows


# ── ЭКСТРУЗИЯ ─────────────────────────────────────────────────────────────────

def save_pallet(date, shift, operator, decor, length, thickness, overlay,
                pallet_num, qty, defect, time_str):
    # Паллета ≥150 плит → сразу в transit (транзитная зона для лака)
    status = 'transit' if qty >= 150 else 'transit'
    conn = get_conn()
    conn.execute("""
        INSERT INTO extrusion_pallets
        (date,shift,operator,decor,length,thickness,overlay,
         pallet_num,qty,defect,time_str,status)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (date,shift,operator,decor,length,thickness,overlay,
          pallet_num,qty,defect,time_str,status))
    conn.commit(); conn.close()

def save_remark(date, shift, operator, remark_type, qty, reason):
    conn = get_conn()
    conn.execute("INSERT INTO shift_remarks (date,shift,operator,remark_type,qty,reason) VALUES (?,?,?,?,?,?)",
                 (date,shift,operator,remark_type,qty,reason))
    conn.commit(); conn.close()

def get_pallets(date=None, shift=None, status=None):
    conn = get_conn()
    q = "SELECT * FROM extrusion_pallets WHERE 1=1"
    params = []
    if date:   q += " AND date=?";   params.append(date)
    if shift:  q += " AND shift=?";  params.append(shift)
    if status: q += " AND status=?"; params.append(status)
    q += " ORDER BY created_at DESC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return rows


# ── ТРАНЗИТНАЯ ЗОНА ───────────────────────────────────────────────────────────

def get_transit_pallets():
    """Все паллеты ожидающие обработки лаком"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM extrusion_pallets
        WHERE status='transit'
        ORDER BY created_at ASC
    """).fetchall()
    conn.close()
    return rows

def get_transit_count():
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) as cnt FROM extrusion_pallets WHERE status='transit'").fetchone()
    conn.close()
    return row["cnt"]


# ── ЛАК ───────────────────────────────────────────────────────────────────────

def process_lacquer(pallet_id, operator):
    """Оператор лака обработал паллету → статус warehouse"""
    conn = get_conn()
    conn.execute("UPDATE extrusion_pallets SET status='warehouse' WHERE id=?", (pallet_id,))
    conn.execute("INSERT INTO lacquer_records (pallet_id,operator) VALUES (?,?)",
                 (pallet_id, operator))
    conn.commit(); conn.close()

def get_lacquer_records(limit=50):
    conn = get_conn()
    rows = conn.execute("""
        SELECT lr.*, ep.decor, ep.qty, ep.pallet_num, ep.date
        FROM lacquer_records lr
        JOIN extrusion_pallets ep ON lr.pallet_id = ep.id
        ORDER BY lr.processed_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── СКЛАД ─────────────────────────────────────────────────────────────────────

def get_warehouse_pallets(decor=None, limit=200):
    """Все паллеты на складе (обработанные лаком)"""
    conn = get_conn()
    q = """
        SELECT ep.*, lr.processed_at as lacquered_at, lr.operator as lac_operator
        FROM extrusion_pallets ep
        LEFT JOIN lacquer_records lr ON lr.pallet_id = ep.id
        WHERE ep.status='warehouse'
    """
    params = []
    if decor:
        q += " AND ep.decor=?"; params.append(decor)
    q += " ORDER BY lr.processed_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_warehouse_summary():
    """Сводка по складу: декор → количество"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT decor, SUM(qty) as total_qty, SUM(defect) as total_defect,
               COUNT(*) as pallets, MAX(created_at) as last_date
        FROM extrusion_pallets
        WHERE status='warehouse'
        GROUP BY decor
        ORDER BY last_date DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_warehouse_total():
    conn = get_conn()
    row = conn.execute("""
        SELECT SUM(qty) as total, COUNT(*) as pallets
        FROM extrusion_pallets WHERE status='warehouse'
    """).fetchone()
    conn.close()
    return dict(row) if row else {"total": 0, "pallets": 0}


# ── ЗАДАНИЕ ───────────────────────────────────────────────────────────────────

def save_task(week_start, decor, length, thickness, overlay, plan_qty):
    conn = get_conn()
    conn.execute("INSERT INTO weekly_tasks (week_start,decor,length,thickness,overlay,plan_qty) VALUES (?,?,?,?,?,?)",
                 (week_start,decor,length,thickness,overlay,plan_qty))
    conn.commit(); conn.close()

def get_tasks(week_start=None):
    conn = get_conn()
    if not week_start:
        latest = conn.execute(
            "SELECT week_start FROM weekly_tasks ORDER BY id DESC LIMIT 1"
        ).fetchone()
        week_start = latest["week_start"] if latest else ""
    rows = conn.execute("SELECT * FROM weekly_tasks WHERE week_start=? ORDER BY id",(week_start,)).fetchall()
    conn.close()
    return rows


# ── ОТЧЁТ ─────────────────────────────────────────────────────────────────────

def get_daily_report(date):
    conn = get_conn()
    mixer = conn.execute(
        "SELECT SUM(batches) as total, GROUP_CONCAT(operator||'('||shift||':'||batches||')') as detail "
        "FROM mixer_shifts WHERE date=?", (date,)
    ).fetchone()
    ext = conn.execute(
        "SELECT SUM(qty) as total_qty, SUM(defect) as total_defect FROM extrusion_pallets WHERE date=?", (date,)
    ).fetchone()
    by_decor = conn.execute(
        "SELECT decor, SUM(qty) as qty, SUM(defect) as defect FROM extrusion_pallets WHERE date=? GROUP BY decor", (date,)
    ).fetchall()
    remarks = conn.execute("SELECT * FROM shift_remarks WHERE date=?", (date,)).fetchall()
    lac = conn.execute(
        "SELECT COUNT(*) as cnt, SUM(ep.qty) as qty FROM lacquer_records lr "
        "JOIN extrusion_pallets ep ON lr.pallet_id=ep.id "
        "WHERE DATE(lr.processed_at)=?", (date,)
    ).fetchone()
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
        "lac_pallets": lac["cnt"] or 0,
        "lac_qty": lac["qty"] or 0,
    }


# ── РЕЦЕПТУРА ─────────────────────────────────────────────────────────────────

def get_recipe():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM recipe ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_recipe(component, kg_per_batch):
    conn = get_conn()
    conn.execute("UPDATE recipe SET kg_per_batch=?,updated_at=datetime('now','localtime') WHERE component=?",
                 (kg_per_batch, component))
    conn.commit(); conn.close()


# ── EXCEL ЭКСПОРТ ─────────────────────────────────────────────────────────────

def get_full_export(date=None):
    """Все данные для выгрузки в Excel"""
    conn = get_conn()
    q_pallets = """
        SELECT ep.date, ep.shift, ep.operator, ep.decor, ep.length, ep.thickness,
               ep.overlay, ep.pallet_num, ep.qty, ep.defect, ep.time_str,
               ep.status, ep.created_at,
               lr.operator as lac_operator, lr.processed_at as lac_date
        FROM extrusion_pallets ep
        LEFT JOIN lacquer_records lr ON lr.pallet_id=ep.id
    """
    params = []
    if date:
        q_pallets += " WHERE ep.date=?"; params.append(date)
    q_pallets += " ORDER BY ep.created_at DESC"
    pallets = conn.execute(q_pallets, params).fetchall()

    q_mixer = "SELECT * FROM mixer_shifts"
    if date:
        q_mixer += " WHERE date=?"
    mixer = conn.execute(q_mixer, params[:1] if date else []).fetchall()

    conn.close()
    return {
        "pallets": [dict(r) for r in pallets],
        "mixer": [dict(r) for r in mixer],
    }



# ── ЗАДАНИЕ-ОРИЕНТИРОВАННАЯ ЭКСТРУЗИЯ ────────────────────────────────────────

def get_current_week_start():
    """Понедельник текущей недели"""
    from datetime import date, timedelta
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%d.%m.%Y")

def get_active_tasks():
    """Активные задания — берём самую свежую неделю где есть задания"""
    conn = get_conn()
    # Ищем последнюю неделю с заданиями (не фиксируем дату жёстко)
    latest = conn.execute(
        "SELECT week_start FROM weekly_tasks ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not latest:
        conn.close()
        return []
    week = latest["week_start"]
    tasks = conn.execute(
        "SELECT * FROM weekly_tasks WHERE week_start=? ORDER BY id", (week,)
    ).fetchall()
    result = []
    for t in tasks:
        done = conn.execute(
            "SELECT COUNT(*) as cnt, SUM(qty) as qty FROM extrusion_pallets WHERE decor=?",
            (t["decor"],)
        ).fetchone()
        pallets_done = done["cnt"] or 0
        qty_done = done["qty"] or 0
        # Сколько паллет нужно (план / 150 плит на паллету)
        pallets_needed = -(-t["plan_qty"] // 150)  # ceiling division
        result.append({
            "id": t["id"],
            "week_start": t["week_start"],
            "decor": t["decor"],
            "length": t["length"],
            "thickness": t["thickness"],
            "overlay": t["overlay"],
            "plan_qty": t["plan_qty"],
            "pallets_needed": pallets_needed,
            "pallets_done": pallets_done,
            "qty_done": qty_done,
            "pct": round(qty_done / t["plan_qty"] * 100) if t["plan_qty"] else 0,
            "done": qty_done >= t["plan_qty"],
        })
    conn.close()
    return result

def complete_task_pallet(task_id, operator, qty=150):
    """Оператор нажал Сделано на паллете задания"""
    from datetime import date as dt_date
    conn = get_conn()
    task = conn.execute("SELECT * FROM weekly_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return None
    # Считаем следующий номер паллеты для этого декора
    existing = conn.execute(
        "SELECT COUNT(*) as cnt FROM extrusion_pallets WHERE decor=?", (task["decor"],)
    ).fetchone()
    pallet_num = (existing["cnt"] or 0) + 1
    today = dt_date.today().strftime("%d.%m.%Y")
    from datetime import datetime
    time_str = datetime.now().strftime("%H:%M")
    conn.execute("""
        INSERT INTO extrusion_pallets
        (date, shift, operator, decor, length, thickness, overlay,
         pallet_num, qty, defect, time_str, status)
        VALUES (?,?,?,?,?,?,?,?,?,0,?,'transit')
    """, (today, "день", operator, task["decor"], task["length"],
          task["thickness"], task["overlay"], pallet_num, qty, time_str))
    conn.commit()
    # Возвращаем прогресс
    done = conn.execute(
        "SELECT COUNT(*) as cnt, SUM(qty) as total FROM extrusion_pallets WHERE decor=?",
        (task["decor"],)
    ).fetchone()
    conn.close()
    return {
        "decor": task["decor"],
        "pallet_num": pallet_num,
        "qty_done": done["total"] or 0,
        "plan_qty": task["plan_qty"],
        "pallets_done": done["cnt"] or 0,
    }

init_db()
