import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, render_template_string, request, jsonify, redirect, url_for, Markup
from datetime import date, timedelta
from db.database import (
    get_daily_report, get_mixer_shifts, get_pallets,
    get_tasks, get_recipe, save_task, update_recipe, init_db,
    get_all_users, revoke_user, get_codes, update_code
)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "lvt-secret-2026")

TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ЛВТ Производство — Панель управления</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #f5f5f0; --surface: #fff; --border: #e0ddd5;
    --text: #1a1a18; --muted: #6b6b66; --accent: #185FA5;
    --green: #3B6D11; --green-bg: #EAF3DE;
    --amber: #854F0B; --amber-bg: #FAEEDA;
    --red: #A32D2D; --red-bg: #FCEBEB;
  }
  body { font-family: system-ui, -apple-system, sans-serif; background: var(--bg);
    color: var(--text); font-size: 14px; line-height: 1.5; }
  .topbar { background: var(--surface); border-bottom: 1px solid var(--border);
    padding: 12px 24px; display: flex; align-items: center; justify-content: space-between; }
  .topbar h1 { font-size: 16px; font-weight: 600; color: var(--accent); }
  .topbar .nav { display: flex; gap: 8px; flex-wrap: wrap; }
  .topbar .nav a { padding: 6px 14px; border-radius: 8px; text-decoration: none;
    font-size: 13px; color: var(--muted); border: 1px solid var(--border); }
  .topbar .nav a.active, .topbar .nav a:hover { background: var(--accent); color: #fff; border-color: var(--accent); }
  .container { max-width: 1100px; margin: 0 auto; padding: 24px 16px; }
  .grid-4 { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 24px; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 16px 20px; }
  .card .label { font-size: 12px; color: var(--muted); margin-bottom: 4px; }
  .card .value { font-size: 28px; font-weight: 600; }
  .card .sub { font-size: 12px; color: var(--muted); margin-top: 2px; }
  .card.red .value { color: var(--red); }
  .card.green .value { color: var(--green); }
  .card.accent .value { color: var(--accent); }
  .section { background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 20px; margin-bottom: 20px; }
  .section h2 { font-size: 14px; font-weight: 600; margin-bottom: 16px;
    padding-bottom: 10px; border-bottom: 1px solid var(--border); }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; padding: 8px 10px; font-size: 11px; font-weight: 500;
    color: var(--muted); border-bottom: 1px solid var(--border); text-transform: uppercase; letter-spacing: 0.5px; }
  td { padding: 8px 10px; border-bottom: 1px solid var(--border); }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: var(--bg); }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 500; }
  .badge-ok { background: var(--green-bg); color: var(--green); }
  .badge-warn { background: var(--amber-bg); color: var(--amber); }
  .badge-err { background: var(--red-bg); color: var(--red); }
  .progress-wrap { margin-bottom: 12px; }
  .progress-label { display: flex; justify-content: space-between; font-size: 12px;
    color: var(--muted); margin-bottom: 4px; }
  .progress-bar { height: 8px; background: var(--bg); border-radius: 4px; overflow: hidden; }
  .progress-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
  .date-bar { display: flex; gap: 8px; align-items: center; margin-bottom: 20px; flex-wrap: wrap; }
  .date-bar input[type=date] { padding: 7px 12px; border: 1px solid var(--border);
    border-radius: 8px; font-size: 13px; background: var(--surface); color: var(--text); }
  .btn { padding: 7px 16px; border: 1px solid var(--border); border-radius: 8px;
    background: var(--surface); color: var(--text); font-size: 13px; cursor: pointer;
    text-decoration: none; display: inline-block; }
  .btn:hover { background: var(--bg); }
  .btn-primary { background: var(--accent); color: #fff; border-color: var(--accent); }
  .btn-primary:hover { opacity: 0.9; }
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 640px) { .two-col { grid-template-columns: 1fr; } }
  .form-row { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
  .form-row label { font-size: 12px; color: var(--muted); }
  .form-row input, .form-row select { padding: 7px 10px; border: 1px solid var(--border);
    border-radius: 8px; font-size: 13px; background: var(--surface); color: var(--text); }
  .shift-day { background: var(--amber-bg); color: var(--amber); }
  .shift-night { background: #E6F1FB; color: var(--accent); }
  .empty { color: var(--muted); font-size: 13px; text-align: center; padding: 24px; }
</style>
</head>
<body>
<div class="topbar">
  <h1>ЛВТ Производство</h1>
  <nav class="nav">
    <a href="/" class="{{ 'active' if page=='report' else '' }}">Отчёт</a>
    <a href="/week" class="{{ 'active' if page=='week' else '' }}">Неделя</a>
    <a href="/mixer" class="{{ 'active' if page=='mixer' else '' }}">Миксер</a>
    <a href="/extruder" class="{{ 'active' if page=='extruder' else '' }}">Экструзия</a>
    <a href="/tasks" class="{{ 'active' if page=='tasks' else '' }}">Задание</a>
    <a href="/recipe" class="{{ 'active' if page=='recipe' else '' }}">Рецептура</a>
    <a href="/users" class="{{ 'active' if page=='users' else '' }}">Пользователи</a>
  </nav>
</div>
<div class="container">
{{ content }}
</div>
</body>
</html>
"""


def render(page, content):
    return render_template_string(TEMPLATE, page=page, content=Markup(content))


def badge(pct):
    if pct <= 2:
        return f'<span class="badge badge-ok">{pct}%</span>'
    elif pct <= 5:
        return f'<span class="badge badge-warn">{pct}%</span>'
    return f'<span class="badge badge-err">{pct}%</span>'


def progress_color(pct):
    if pct >= 80:
        return "#639922"
    elif pct >= 50:
        return "#EF9F27"
    return "#E24B4A"


@app.route("/")
def report():
    date_str = request.args.get("date", date.today().strftime("%d.%m.%Y"))
    r = get_daily_report(date_str)
    pct = round(r["total_defect"] / r["total_qty"] * 100, 1) if r["total_qty"] else 0

    decor_rows = ""
    for d in r["by_decor"]:
        dpct = round(d["defect"] / d["qty"] * 100, 1) if d["qty"] else 0
        decor_rows += f"""<tr>
          <td><b>{d['decor']}</b></td>
          <td>{d['qty']}</td>
          <td>{d['defect']} {badge(dpct)}</td>
        </tr>"""

    remark_rows = ""
    for rm in r["remarks"]:
        remark_rows += f"<tr><td>{rm['remark_type']}</td><td>{rm['qty']}</td><td>{rm['reason']}</td><td>{rm['operator']}</td></tr>"

    recipe_rows = ""
    for comp in r["recipe"]:
        total_comp = comp["kg_per_batch"] * r["batches"]
        recipe_rows += f"<tr><td>{comp['component']}</td><td>{comp['kg_per_batch']} кг</td><td><b>{total_comp:.1f} кг</b></td></tr>"

    content = f"""
    <div class="date-bar">
      <form method="get" style="display:flex;gap:8px;align-items:center">
        <label style="font-size:13px;color:var(--muted)">Дата:</label>
        <input type="text" name="date" value="{date_str}" placeholder="дд.мм.гггг" style="padding:7px 12px;border:1px solid var(--border);border-radius:8px;font-size:13px">
        <button type="submit" class="btn btn-primary">Показать</button>
      </form>
    </div>

    <div class="grid-4">
      <div class="card accent"><div class="label">Выпуск листов</div><div class="value">{r['total_qty']}</div><div class="sub">за {date_str}</div></div>
      <div class="card {'red' if pct > 5 else 'green'}"><div class="label">Брак</div><div class="value">{r['total_defect']}</div><div class="sub">{pct}% от выпуска</div></div>
      <div class="card"><div class="label">Замесов</div><div class="value">{r['batches']}</div><div class="sub">{r['mixer_detail']}</div></div>
      <div class="card"><div class="label">Сырьё израсходовано</div><div class="value">{r['total_kg'] / 1000:.2f} тн</div><div class="sub">{r['total_kg']:.0f} кг</div></div>
    </div>

    <div class="two-col">
      <div class="section">
        <h2>Выпуск по декорам</h2>
        {'<table><thead><tr><th>Декор</th><th>Листов</th><th>Брак</th></tr></thead><tbody>' + decor_rows + '</tbody></table>' if decor_rows else '<div class="empty">Нет данных за эту дату</div>'}
      </div>
      <div class="section">
        <h2>Расход сырья ({r['batches']} замесов)</h2>
        {'<table><thead><tr><th>Компонент</th><th>На замес</th><th>Итого</th></tr></thead><tbody>' + recipe_rows + '</tbody></table>' if r['batches'] else '<div class="empty">Нет замесов за эту дату</div>'}
      </div>
    </div>

    <div class="section">
      <h2>Замечания по смене</h2>
      {'<table><thead><tr><th>Тип</th><th>Кол-во</th><th>Причина</th><th>Оператор</th></tr></thead><tbody>' + remark_rows + '</tbody></table>' if remark_rows else '<div class="empty">Замечаний нет</div>'}
    </div>
    """
    return render("report", content)


@app.route("/week")
def week_report():
    week_start_str = request.args.get("week", "")
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    if not week_start_str:
        week_start_str = monday.strftime("%d.%m.%Y")

    tasks = get_tasks(week_start_str)
    progress_html = ""
    for t in tasks:
        pallets = get_pallets()
        done = sum(p["qty"] for p in pallets if p["decor"] == t["decor"])
        pct = round(done / t["plan_qty"] * 100) if t["plan_qty"] else 0
        pct_clamped = min(pct, 100)
        color = progress_color(pct)
        if pct >= 100:
            b = '<span class="badge badge-ok">Выполнен</span>'
        elif pct >= 50:
            b = f'<span class="badge badge-warn">{pct}%</span>'
        else:
            b = f'<span class="badge badge-err">{pct}%</span>'

        progress_html += f"""
        <div class="progress-wrap">
          <div class="progress-label">
            <span><b>{t['decor']}</b> · {t['length']}мм · {t['thickness']}мм · {t['overlay']}</span>
            <span>{done} / {t['plan_qty']} {b}</span>
          </div>
          <div class="progress-bar"><div class="progress-fill" style="width:{pct_clamped}%;background:{color}"></div></div>
        </div>"""

    content = f"""
    <div class="date-bar">
      <form method="get" style="display:flex;gap:8px;align-items:center">
        <label style="font-size:13px;color:var(--muted)">Неделя с:</label>
        <input type="text" name="week" value="{week_start_str}" placeholder="дд.мм.гггг">
        <button type="submit" class="btn btn-primary">Показать</button>
      </form>
    </div>
    <div class="section">
      <h2>Выполнение недельного задания · {week_start_str}</h2>
      {progress_html if progress_html else '<div class="empty">Задание на эту неделю не задано</div>'}
    </div>"""
    return render("week", content)


@app.route("/mixer")
def mixer_page():
    shifts = get_mixer_shifts()
    rows = ""
    for s in shifts:
        shift_cls = "shift-day" if s["shift"] == "день" else "shift-night"
        rows += f"""<tr>
          <td>{s['date']}</td>
          <td><span class="badge {shift_cls}">{s['shift'].capitalize()}</span></td>
          <td>{s['operator']}</td>
          <td><b>{s['batches']}</b></td>
          <td style="color:var(--muted)">{round(s['batches'] * 584.35, 0):.0f} кг</td>
          <td style="color:var(--muted);font-size:11px">{s['created_at']}</td>
        </tr>"""

    content = f"""
    <div class="section">
      <h2>История замесов (последние 50 записей)</h2>
      {'<table><thead><tr><th>Дата</th><th>Смена</th><th>Оператор</th><th>Замесов</th><th>Сырьё</th><th>Внесено</th></tr></thead><tbody>' + rows + '</tbody></table>' if rows else '<div class="empty">Нет данных</div>'}
    </div>"""
    return render("mixer", content)


@app.route("/extruder")
def extruder_page():
    date_filter = request.args.get("date", "")
    pallets = get_pallets(date_filter if date_filter else None)
    rows = ""
    for p in pallets:
        shift_cls = "shift-day" if p["shift"] == "день" else "shift-night"
        rows += f"""<tr>
          <td>{p['date']}</td>
          <td><span class="badge {shift_cls}">{p['shift'].capitalize()}</span></td>
          <td>{p['decor']}</td>
          <td>{p['length']}</td>
          <td>{p['thickness']}</td>
          <td>{p['overlay']}</td>
          <td>#{p['pallet_num']}</td>
          <td><b>{p['qty']}</b></td>
          <td>{'<span class="badge badge-err">' + str(p['defect']) + '</span>' if p['defect'] else '0'}</td>
          <td>{p['time_str']}</td>
          <td style="color:var(--muted)">{p['operator']}</td>
        </tr>"""

    content = f"""
    <div class="date-bar">
      <form method="get" style="display:flex;gap:8px;align-items:center">
        <input type="text" name="date" value="{date_filter}" placeholder="дд.мм.гггг (пусто = все)">
        <button type="submit" class="btn btn-primary">Фильтр</button>
        <a href="/extruder" class="btn">Все записи</a>
      </form>
    </div>
    <div class="section">
      <h2>Паллеты экструзии</h2>
      {'<div style="overflow-x:auto"><table><thead><tr><th>Дата</th><th>Смена</th><th>Декор</th><th>Длина</th><th>Толщ.</th><th>Овер.</th><th>Пал.</th><th>Листов</th><th>Брак</th><th>Время</th><th>Оператор</th></tr></thead><tbody>' + rows + '</tbody></table></div>' if rows else '<div class="empty">Нет данных</div>'}
    </div>"""
    return render("extruder", content)


@app.route("/tasks", methods=["GET", "POST"])
def tasks_page():
    msg = ""
    if request.method == "POST":
        try:
            save_task(
                request.form["week_start"],
                request.form["decor"],
                int(request.form["length"]),
                float(request.form["thickness"]),
                float(request.form["overlay"]),
                int(request.form["plan_qty"])
            )
            msg = '<div style="color:var(--green);margin-bottom:12px">✅ Позиция добавлена</div>'
        except Exception as e:
            msg = f'<div style="color:var(--red);margin-bottom:12px">Ошибка: {e}</div>'

    week_start_str = request.args.get("week", date.today().strftime("%d.%m.%Y"))
    tasks = get_tasks(week_start_str)
    task_rows = ""
    for t in tasks:
        task_rows += f"<tr><td>{t['decor']}</td><td>{t['length']}</td><td>{t['thickness']}</td><td>{t['overlay']}</td><td><b>{t['plan_qty']}</b></td></tr>"

    content = f"""
    {msg}
    <div class="two-col">
      <div class="section">
        <h2>Добавить позицию в задание</h2>
        <form method="post">
          <div class="form-row"><label>Неделя с (дд.мм.гггг)</label><input name="week_start" value="{week_start_str}" required></div>
          <div class="form-row"><label>Декор</label><input name="decor" placeholder="82019-9" required></div>
          <div class="form-row"><label>Длина (мм)</label><input name="length" value="1220" required></div>
          <div class="form-row"><label>Толщина (мм)</label><input name="thickness" value="2" required></div>
          <div class="form-row"><label>Оверлайн</label><input name="overlay" value="0.25" required></div>
          <div class="form-row"><label>Плановое кол-во</label><input name="plan_qty" placeholder="800" required></div>
          <button type="submit" class="btn btn-primary">Добавить</button>
        </form>
      </div>
      <div class="section">
        <h2>Задание на неделю с {week_start_str}</h2>
        <div class="date-bar" style="margin-bottom:12px">
          <form method="get" style="display:flex;gap:8px">
            <input type="text" name="week" value="{week_start_str}" placeholder="дд.мм.гггг">
            <button type="submit" class="btn">Загрузить</button>
          </form>
        </div>
        {'<table><thead><tr><th>Декор</th><th>Длина</th><th>Толщ.</th><th>Овер.</th><th>План</th></tr></thead><tbody>' + task_rows + '</tbody></table>' if task_rows else '<div class="empty">Задание не задано</div>'}
      </div>
    </div>"""
    return render("tasks", content)


@app.route("/recipe", methods=["GET", "POST"])
def recipe_page():
    msg = ""
    if request.method == "POST":
        try:
            update_recipe(request.form["component"], float(request.form["kg"]))
            msg = '<div style="color:var(--green);margin-bottom:12px">✅ Рецептура обновлена</div>'
        except Exception as e:
            msg = f'<div style="color:var(--red);margin-bottom:12px">Ошибка: {e}</div>'

    recipe = get_recipe()
    total = sum(r["kg_per_batch"] for r in recipe)
    rows = ""
    for r in recipe:
        rows += f"""<tr>
          <td>{r['component']}</td>
          <td><b>{r['kg_per_batch']}</b> кг</td>
          <td style="color:var(--muted)">{r['updated_at']}</td>
        </tr>"""

    options = "\n".join(f'<option value="{r["component"]}">{r["component"]}</option>' for r in recipe)

    content = f"""
    {msg}
    <div class="two-col">
      <div class="section">
        <h2>Текущая рецептура (на 1 замес)</h2>
        <table><thead><tr><th>Компонент</th><th>кг/замес</th><th>Обновлено</th></tr></thead>
        <tbody>{rows}</tbody>
        <tfoot><tr><td><b>Итого</b></td><td><b>{total:.2f} кг</b></td><td></td></tr></tfoot>
        </table>
      </div>
      <div class="section">
        <h2>Изменить компонент</h2>
        <form method="post">
          <div class="form-row"><label>Компонент</label>
            <select name="component">{options}</select>
          </div>
          <div class="form-row"><label>Новое значение (кг/замес)</label>
            <input name="kg" type="number" step="0.01" required>
          </div>
          <button type="submit" class="btn btn-primary">Сохранить</button>
        </form>
      </div>
    </div>"""
    return render("recipe", content)


@app.route("/users", methods=["GET", "POST"])
def users_page():
    msg = ""
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "add":
                msg = '<div style="color:var(--amber);margin-bottom:12px">Добавление через бота: оператор вводит /start и код доступа</div>'
            elif action == "remove":
                tg_id = int(request.form["tg_id"])
                revoke_user(tg_id)
                msg = '<div style="color:var(--green);margin-bottom:12px">✅ Доступ отозван</div>'
        except Exception as e:
            msg = f'<div style="color:var(--red);margin-bottom:12px">Ошибка: {e}</div>'

    users = get_all_users()
    role_labels = {"boss": "👑 Руководитель", "mixer": "🧪 Миксерщик", "extruder": "⚙️ Экструзия"}
    rows = ""
    for u in users:
        rows += f"""<tr>
          <td><b>{u['name']}</b></td>
          <td><code>{u['tg_id']}</code></td>
          <td>{role_labels.get(u['role'], u['role'])}</td>
          <td style="color:var(--muted)">{u['created_at']}</td>
          <td>
            <form method="post" style="display:inline" onsubmit="return confirm('Удалить {u['name']}?')">
              <input type="hidden" name="action" value="remove">
              <input type="hidden" name="tg_id" value="{u['tg_id']}">
              <button type="submit" class="btn" style="color:var(--red);padding:4px 10px;font-size:12px">Удалить</button>
            </form>
          </td>
        </tr>"""

    content = f"""
    {msg}
    <div class="two-col">
      <div class="section">
        <h2>Добавить пользователя</h2>
        <form method="post">
          <input type="hidden" name="action" value="add">
          <div class="form-row"><label>Telegram ID</label>
            <input name="tg_id" type="number" placeholder="123456789" required>
          </div>
          <div class="form-row"><label>Имя сотрудника</label>
            <input name="name" placeholder="Хамиков С." required>
          </div>
          <div class="form-row"><label>Роль</label>
            <select name="role" required>
              <option value="mixer">🧪 Миксерщик</option>
              <option value="extruder">⚙️ Оператор экструзии</option>
              <option value="boss">👑 Руководитель</option>
            </select>
          </div>
          <button type="submit" class="btn btn-primary">Добавить</button>
        </form>
        <div style="margin-top:16px;padding-top:16px;border-top:1px solid var(--border);font-size:12px;color:var(--muted)">
          Как узнать Telegram ID сотрудника:<br>
          1. Сотрудник находит бота и нажимает /start<br>
          2. Бот показывает его ID<br>
          3. Добавьте его ID сюда
        </div>
      </div>
      <div class="section">
        <h2>Список пользователей ({len(users)})</h2>
        {'<div style="overflow-x:auto"><table><thead><tr><th>Имя</th><th>ID</th><th>Роль</th><th>Добавлен</th><th></th></tr></thead><tbody>' + rows + '</tbody></table></div>' if rows else '<div class="empty">Нет пользователей</div>'}
      </div>
    </div>"""
    return render("users", content)


if __name__ == "__main__":
    init_db()
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
