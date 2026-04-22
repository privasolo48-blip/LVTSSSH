import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
from datetime import date as dt_date

from db.database import (
    save_mixer_shift, save_pallet, save_remark, save_task,
    get_daily_report, get_recipe, update_recipe, get_tasks, get_pallets,
    check_code, authorize_user, get_user_role, get_all_users, revoke_user,
    get_codes, update_code, get_transit_pallets, get_transit_count,
    process_lacquer, get_warehouse_summary, get_warehouse_total, init_db,
    get_active_tasks, complete_task_pallet
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_ТОКЕН")
WEB_URL = os.getenv("WEB_URL", "").rstrip("/")

import urllib.request, json as _json

def fetch_tasks():
    """Получить задание из веб-панели (единый источник правды)"""
    if not WEB_URL:
        return []
    try:
        with urllib.request.urlopen(f"{WEB_URL}/api/tasks", timeout=5) as r:
            data = _json.loads(r.read())
            return data.get("tasks", [])
    except Exception as e:
        print(f"[fetch_tasks error] {e}", flush=True)
        return []

def post_complete(task_id, operator, qty):
    """Отметить паллету как выполненную через API"""
    if not WEB_URL:
        return complete_task_pallet(task_id, operator, qty)
    try:
        payload = _json.dumps({"task_id": task_id, "operator": operator, "qty": qty}).encode()
        req = urllib.request.Request(
            f"{WEB_URL}/api/complete_pallet",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = _json.loads(r.read())
            return data.get("result") if data.get("ok") else None
    except Exception as e:
        print(f"[post_complete error] {e}", flush=True)
        return complete_task_pallet(task_id, operator, qty)
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

ROLE_NAMES = {
    "mixer": "🧪 Миксерщик",
    "extruder": "⚙️ Экструзия",
    "lacquer": "🎨 Оператор лака",
    "boss": "👑 Руководитель",
}


# ── СОСТОЯНИЯ ────────────────────────────────────────────────────────────────

class Auth(StatesGroup):
    code = State()

class Mixer(StatesGroup):
    date = State(); shift = State(); operator = State(); batches = State()

class Extruder(StatesGroup):
    date = State(); shift = State(); operator = State()
    decor = State(); length = State(); thickness = State()
    overlay = State(); pallet_num = State(); qty = State()
    defect = State(); time_str = State(); next_action = State()

class ExtruderTask(StatesGroup):
    operator = State()
    selecting = State()
    confirm_qty = State()

class Remark(StatesGroup):
    remark_type = State(); qty = State(); reason = State()

class Lacquer(StatesGroup):
    selecting = State()

class Task(StatesGroup):
    week_start = State(); adding = State()

class BossDate(StatesGroup):
    waiting = State()


# ── HELPERS ───────────────────────────────────────────────────────────────────

def kb(*buttons):
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    m.add(*[types.KeyboardButton(b) for b in buttons])
    return m

def remove_kb():
    return types.ReplyKeyboardRemove()

def today():
    return dt_date.today().strftime("%d.%m.%Y")

def role_menu(role):
    if role == "boss":
        return kb("📊 Отчёт за сегодня", "📅 Отчёт за дату",
                  "📋 Задание на неделю", "🏭 Транзит",
                  "🏪 Склад", "⚗️ Рецептура",
                  "🤖 ИИ Ассистент", "👥 Пользователи",
                  "🔑 Коды доступа", "🚪 Выйти")
    elif role == "mixer":
        return kb("➕ Внести смену", "🏠 Меню", "🚪 Выйти")
    elif role == "extruder":
        return kb("📋 Задание на смену", "🏭 Транзит", "🚪 Выйти")
    elif role == "lacquer":
        return kb("📦 Транзитная зона", "✅ Обработать паллету", "🏪 Склад", "🚪 Выйти")
    return remove_kb()

async def show_menu(message, role):
    transit = get_transit_count()
    extra = f"\n⚠️ В транзите: <b>{transit} паллет</b>" if transit > 0 and role in ("lacquer","boss","extruder") else ""
    await message.answer(
        f"Вы вошли как: <b>{ROLE_NAMES[role]}</b>{extra}\n\nВыберите действие:",
        reply_markup=role_menu(role)
    )


# ── АВТОРИЗАЦИЯ ───────────────────────────────────────────────────────────────

@dp.message_handler(commands=["start"], state="*")
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    role = get_user_role(message.from_user.id)
    if role:
        await show_menu(message, role)
    else:
        await Auth.code.set()
        await message.answer("🔐 Бот только для сотрудников.\n\nВведите код доступа:", reply_markup=remove_kb())

@dp.message_handler(state=Auth.code)
async def auth_check(message: types.Message, state: FSMContext):
    role = check_code(message.text)
    if not role:
        await message.answer("❌ Неверный код. Попробуйте ещё раз."); return
    authorize_user(message.from_user.id, message.from_user.full_name, message.from_user.username, role)
    await state.finish()
    await message.answer(f"✅ Доступ получен!\nРоль: <b>{ROLE_NAMES[role]}</b>")
    await show_menu(message, role)

@dp.message_handler(lambda m: m.text == "🚪 Выйти", state="*")
async def logout(message: types.Message, state: FSMContext):
    await state.finish()
    revoke_user(message.from_user.id)
    await message.answer(
        "👋 Вы вышли из аккаунта.\n\nДля входа нажмите /start и введите код доступа.",
        reply_markup=types.ReplyKeyboardRemove()
    )

@dp.message_handler(lambda m: m.text in ["🏠 Меню", "🏠 Главное меню"], state="*")
async def go_home(message: types.Message, state: FSMContext):
    await state.finish()
    role = get_user_role(message.from_user.id)
    if role:
        await show_menu(message, role)
    else:
        await cmd_start(message, state)


# ── МИКСЕР ────────────────────────────────────────────────────────────────────

@dp.message_handler(lambda m: m.text == "➕ Внести смену", state="*")
async def mixer_start(message: types.Message, state: FSMContext):
    if get_user_role(message.from_user.id) not in ("mixer","boss"):
        await message.answer("⛔ Нет доступа"); return
    await state.finish(); await Mixer.date.set()
    await message.answer("Дата:", reply_markup=kb(today(), "◀️ Отмена"))

@dp.message_handler(state=Mixer.date)
async def mx_date(message: types.Message, state: FSMContext):
    if message.text == "◀️ Отмена":
        await state.finish(); await cmd_start(message, state); return
    await state.update_data(date=message.text); await Mixer.shift.set()
    await message.answer("Смена:", reply_markup=kb("День","Ночь","◀️ Отмена"))

@dp.message_handler(state=Mixer.shift)
async def mx_shift(message: types.Message, state: FSMContext):
    if message.text == "◀️ Отмена":
        await state.finish(); await cmd_start(message, state); return
    await state.update_data(shift=message.text.lower()); await Mixer.operator.set()
    await message.answer("Ваше имя:", reply_markup=remove_kb())

@dp.message_handler(state=Mixer.operator)
async def mx_operator(message: types.Message, state: FSMContext):
    await state.update_data(operator=message.text); await Mixer.batches.set()
    await message.answer("Количество замесов:")

@dp.message_handler(state=Mixer.batches)
async def mx_batches(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введите число"); return
    batches = int(message.text); data = await state.get_data()
    recipe = get_recipe()
    total_kg = sum(r["kg_per_batch"] for r in recipe) * batches
    lines = "\n".join(f"  {r['component']}: {r['kg_per_batch']*batches:.1f} кг" for r in recipe)
    save_mixer_shift(data["date"], data["shift"], data["operator"], batches)
    await state.finish()
    role = get_user_role(message.from_user.id)
    await message.answer(
        f"✅ Смена сохранена!\n📅 {data['date']} · {data['shift'].capitalize()}\n"
        f"👤 {data['operator']}\n🔄 Замесов: {batches}\n\n"
        f"⚖️ Расход ({total_kg:.1f} кг):\n{lines}",
        reply_markup=role_menu(role)
    )


# ── ЭКСТРУЗИЯ (ЗАДАНИЕ-ОРИЕНТИРОВАННАЯ) ──────────────────────────────────────

@dp.message_handler(lambda m: m.text == "📋 Задание на смену", state="*")
async def ext_task_start(message: types.Message, state: FSMContext):
    if get_user_role(message.from_user.id) not in ("extruder", "boss"):
        await message.answer("⛔ Нет доступа"); return
    await state.finish()
    tasks = fetch_tasks()
    if not tasks:
        await message.answer(
            "📋 Задание на эту неделю не задано.\n\nОбратитесь к руководителю.",
            reply_markup=role_menu(get_user_role(message.from_user.id))
        ); return
    await ExtruderTask.operator.set()
    await message.answer("Введите ваше имя:", reply_markup=remove_kb())

@dp.message_handler(state=ExtruderTask.operator)
async def ext_task_operator(message: types.Message, state: FSMContext):
    await state.update_data(operator=message.text)
    await show_task_list(message, state)

async def show_task_list(message, state):
    tasks = fetch_tasks()
    data = await state.get_data()
    lines = []
    btns = []
    for t in tasks:
        status = "✅" if t["done"] else ("🟡" if t["pct"] >= 50 else "🔴")
        bar = "█" * (t["pct"] // 10) + "░" * (10 - t["pct"] // 10)
        lines.append(
            f"{status} <b>{t['decor']}</b> · {t['length']}мм · {t['thickness']}мм\n"
            f"   {bar} {t['pct']}%\n"
            f"   Сделано: {t['done_qty']}/{t['plan_qty']} листов ({t['done_cnt']} паллет из {t['pallets_needed']})"
        )
        if not t["done"]:
            btns.append(f"✔️ {t['decor']} ({t['done_cnt']}/{t['pallets_needed']})")

    btns.append("⚠️ Замечание")
    btns.append("🏠 Меню")

    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    m.add(*[types.KeyboardButton(b) for b in btns])

    await ExtruderTask.selecting.set()
    week_label = tasks[0]["week_start"] if tasks else ""
    header = f"📋 <b>Задание · неделя с {week_label}</b>\n👤 {data.get('operator','')}\n\n"
    footer = "\n\n<i>Нажмите на декор чтобы отметить паллету как выполненную</i>"
    await message.answer(
        header + "\n\n".join(lines) + footer,
        reply_markup=m
    )

@dp.message_handler(state=ExtruderTask.selecting)
async def ext_task_select(message: types.Message, state: FSMContext):
    role = get_user_role(message.from_user.id)
    data = await state.get_data()

    if message.text == "🏠 Меню":
        await state.finish(); await show_menu(message, role); return

    if message.text == "⚠️ Замечание":
        await Remark.remark_type.set()
        await message.answer("Тип замечания:", reply_markup=kb("Обрыв", "Остановка", "Другое")); return

    # Парсим декор из кнопки вида "✔️ 82019-9 (2/6)"
    if message.text.startswith("✔️ "):
        try:
            decor = message.text.replace("✔️ ", "").split(" (")[0].strip()
            # Найти task_id по декору
            tasks = fetch_tasks()
            task = next((t for t in tasks if t["decor"] == decor), None)
            if not task:
                await message.answer("Задание не найдено."); return
            if task["done"]:
                await message.answer(f"✅ {decor} уже полностью выполнен!"); return

            await state.update_data(task_id=task["id"], decor=decor,
                                    plan_qty=task["plan_qty"], qty_done=task["done_qty"])
            await ExtruderTask.confirm_qty.set()

            remaining = task["plan_qty"] - task["done_qty"]
            default_qty = min(150, remaining)
            await message.answer(
                f"📦 Паллета готова: <b>{decor}</b>\n\n"
                f"Осталось произвести: {remaining} листов\n\n"
                f"Введите точное количество листов или выберите:",
                reply_markup=kb(str(default_qty), "150", "200", "250", "◀️ Назад")
            )
        except Exception as e:
            await message.answer(f"Ошибка: {e}")
    else:
        await message.answer("Выберите декор из списка или нажмите 🏠 Меню")

@dp.message_handler(state=ExtruderTask.confirm_qty)
async def ext_task_confirm(message: types.Message, state: FSMContext):
    role = get_user_role(message.from_user.id)
    data = await state.get_data()

    if message.text == "◀️ Назад":
        await show_task_list(message, state); return

    if message.text == "◀️ Назад":
        await show_task_list(message, state); return
    try:
        qty = int(message.text.strip())
        if qty <= 0 or qty > 500:
            await message.answer("Введите число от 1 до 500"); return
    except ValueError:
        await message.answer("⚠️ Введите число, например: 175"); return

    result = post_complete(data["task_id"], data.get("operator",""), qty)
    if not result:
        await message.answer("Ошибка — задание не найдено"); return

    transit = get_transit_count()
    pct = round(result["done_qty"] / result["plan_qty"] * 100) if result["plan_qty"] else 0
    done_flag = "✅ Задание выполнено!" if pct >= 100 else ""

    await message.answer(
        f"✅ Паллета #{result['pallet_num']} записана!\n"
        f"🎨 {result['decor']} · {qty} листов\n"
        f"🏭 Отправлена в транзитную зону\n\n"
        f"Прогресс: {result['done_qty']}/{result['plan_qty']} листов ({pct}%)\n"
        f"Паллет сдано: {result['done_cnt']}\n"
        f"{done_flag}"
    )
    # Вернуться к списку заданий
    await show_task_list(message, state)


# ── ТРАНЗИТ ───────────────────────────────────────────────────────────────────

@dp.message_handler(lambda m: m.text in ["🏭 Транзит","🏭 Транзитная зона","📦 Транзитная зона"], state="*")
async def show_transit(message: types.Message, state: FSMContext):
    role = get_user_role(message.from_user.id)
    if role not in ("lacquer","boss","extruder"):
        await message.answer("⛔ Нет доступа"); return
    pallets = get_transit_pallets()
    if not pallets:
        await message.answer("✅ Транзитная зона пуста — все паллеты обработаны!",
                             reply_markup=role_menu(role)); return
    lines = []
    for p in pallets:
        lines.append(f"🔸 <b>ID{p['id']}</b> · {p['decor']} · #{p['pallet_num']} · {p['qty']} шт · {p['date']}")
    await message.answer(
        f"🏭 <b>Транзитная зона</b> ({len(pallets)} паллет):\n\n" + "\n".join(lines) +
        "\n\nДля обработки нажми <b>✅ Обработать паллету</b>",
        reply_markup=role_menu(role)
    )


# ── ЛАК ───────────────────────────────────────────────────────────────────────

@dp.message_handler(lambda m: m.text == "✅ Обработать паллету", state="*")
async def lac_start(message: types.Message, state: FSMContext):
    if get_user_role(message.from_user.id) not in ("lacquer","boss"):
        await message.answer("⛔ Нет доступа"); return
    pallets = get_transit_pallets()
    if not pallets:
        await message.answer("✅ Нет паллет для обработки — транзит пуст!"); return
    await state.finish()
    # Показываем кнопки с ID паллет
    btns = [f"ID{p['id']}: {p['decor']} #{p['pallet_num']} ({p['qty']}шт)" for p in pallets]
    btns.append("◀️ Назад")
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    m.add(*[types.KeyboardButton(b) for b in btns])
    await Lacquer.selecting.set()
    await message.answer("Выберите паллету которую обработали:", reply_markup=m)

@dp.message_handler(state=Lacquer.selecting)
async def lac_select(message: types.Message, state: FSMContext):
    role = get_user_role(message.from_user.id)
    if message.text == "◀️ Назад":
        await state.finish(); await show_menu(message, role); return
    try:
        pallet_id = int(message.text.split(":")[0].replace("ID","").strip())
        operator = message.from_user.full_name
        process_lacquer(pallet_id, operator)
        transit = get_transit_count()
        await state.finish()
        await message.answer(
            f"✅ Паллета ID{pallet_id} обработана лаком!\n"
            f"📦 Отправлена на <b>Склад</b>\n\n"
            f"🏭 Осталось в транзите: {transit} паллет",
            reply_markup=role_menu(role)
        )
    except Exception as e:
        await message.answer(f"Ошибка: {e}\nВыберите паллету из списка.")


# ── СКЛАД ─────────────────────────────────────────────────────────────────────

@dp.message_handler(lambda m: m.text == "🏪 Склад", state="*")
async def show_warehouse(message: types.Message, state: FSMContext):
    role = get_user_role(message.from_user.id)
    if role not in ("lacquer","boss","extruder"):
        await message.answer("⛔ Нет доступа"); return
    summary = get_warehouse_summary()
    total = get_warehouse_total()
    if not summary:
        await message.answer("📦 Склад пуст.", reply_markup=role_menu(role)); return
    lines = []
    for s in summary:
        lines.append(f"🎨 <b>{s['decor']}</b>: {s['total_qty']} шт · {s['pallets']} паллет")
    await message.answer(
        f"🏪 <b>Склад</b>\n"
        f"Всего: <b>{total['total']} листов</b> · {total['pallets']} паллет\n\n" +
        "\n".join(lines),
        reply_markup=role_menu(role)
    )


# ── РУКОВОДИТЕЛЬ ──────────────────────────────────────────────────────────────

@dp.message_handler(lambda m: m.text == "📊 Отчёт за сегодня", state="*")
async def rep_today(message: types.Message, state: FSMContext):
    if get_user_role(message.from_user.id) != "boss":
        await message.answer("⛔ Нет доступа"); return
    await send_report(message, today())

@dp.message_handler(lambda m: m.text == "📅 Отчёт за дату", state="*")
async def rep_date_ask(message: types.Message, state: FSMContext):
    if get_user_role(message.from_user.id) != "boss":
        await message.answer("⛔ Нет доступа"); return
    await BossDate.waiting.set()
    await message.answer("Введите дату (дд.мм.гггг):", reply_markup=remove_kb())

@dp.message_handler(state=BossDate.waiting)
async def rep_date(message: types.Message, state: FSMContext):
    await state.finish(); await send_report(message, message.text)

async def send_report(message, date_str):
    r = get_daily_report(date_str)
    pct = round(r["total_defect"]/r["total_qty"]*100,1) if r["total_qty"] else 0
    by_decor = "\n".join(f"  • {d['decor']}: {d['qty']} шт, брак {d['defect']}"
                         for d in r["by_decor"]) or "  нет данных"
    remarks = "\n".join(f"  • {rm['remark_type']}: {rm['qty']}x — {rm['reason']}"
                        for rm in r["remarks"]) or "  нет"
    recipe_lines = "\n".join(f"  {c['component']}: {c['kg_per_batch']*r['batches']:.1f} кг"
                             for c in r["recipe"])
    await message.answer(
        f"📊 <b>Отчёт за {date_str}</b>\n{'─'*28}\n"
        f"🔄 Замесов: {r['batches']} ({r['mixer_detail']})\n"
        f"⚖️ Сырьё: {r['total_kg']:.1f} кг\n\n"
        f"📦 Выпуск: {r['total_qty']} листов\n"
        f"❌ Брак: {r['total_defect']} ({pct}%)\n\n"
        f"По декорам:\n{by_decor}\n\n"
        f"🎨 Лак: {r['lac_pallets']} паллет · {r['lac_qty']} листов\n\n"
        f"⚠️ Замечания:\n{remarks}\n\n"
        f"⚗️ Расход сырья:\n{recipe_lines}",
        reply_markup=role_menu("boss")
    )

@dp.message_handler(lambda m: m.text == "📋 Недельное задание", state="*")
async def task_start(message: types.Message, state: FSMContext):
    if get_user_role(message.from_user.id) != "boss":
        await message.answer("⛔ Нет доступа"); return
    await Task.week_start.set()
    await message.answer("Дата начала недели (дд.мм.гггг):", reply_markup=remove_kb())

@dp.message_handler(state=Task.week_start)
async def task_week(message: types.Message, state: FSMContext):
    date_text = message.text.strip()
    for p in ["пн, ","вт, ","ср, ","чт, ","пт, ","сб, ","вс, "]:
        if date_text.lower().startswith(p): date_text = date_text[len(p):].strip(); break
    await state.update_data(week_start=date_text, tasks=[])
    await Task.adding.set()
    await message.answer(
        f"📋 Задание на неделю с <b>{date_text}</b>\n\n"
        "Введите строки (можно несколько через Enter):\n"
        "<code>декор длина толщина оверлайн кол-во</code>\n\n"
        "<code>82019-9 1220 2 0.25 800</code>\n"
        "<code>81111-4 1220 2 0.25 600</code>\n\n"
        "По окончании отправьте /done"
    )

@dp.message_handler(state=Task.adding)
async def task_add(message: types.Message, state: FSMContext):
    if message.text.strip() == "/done":
        data = await state.get_data()
        tasks = data.get("tasks",[])
        await state.finish()
        lines = "\n".join(f"  • {t['decor']} — {t['qty']} шт." for t in tasks)
        await message.answer(f"✅ Задание сохранено!\nПозиций: {len(tasks)}\n{lines}",
                             reply_markup=role_menu("boss")); return
    rows = [l.strip() for l in message.text.strip().split("\n") if l.strip()]
    data = await state.get_data(); saved = []; errors = []
    for row in rows:
        try:
            p = row.split()
            decor,length,thickness,overlay,qty = p[0],int(p[1]),float(p[2]),float(p[3]),int(p[4])
            save_task(data["week_start"],decor,length,thickness,overlay,qty)
            saved.append({"decor":decor,"qty":qty})
        except Exception: errors.append(row)
    tasks = data.get("tasks",[]) + saved
    await state.update_data(tasks=tasks)
    resp = "\n".join(f"✅ {t['decor']} · {t['qty']} шт." for t in saved)
    if errors: resp += f"\n⚠️ Не распознано: {len(errors)} строк"
    resp += f"\n\nВсего: {len(tasks)} поз. Ещё или /done"
    await message.answer(resp)

@dp.message_handler(lambda m: m.text == "⚗️ Рецептура", state="*")
async def recipe_show(message: types.Message, state: FSMContext):
    if get_user_role(message.from_user.id) != "boss":
        await message.answer("⛔ Нет доступа"); return
    r = get_recipe(); total = sum(x["kg_per_batch"] for x in r)
    lines = "\n".join(f"  {x['component']}: {x['kg_per_batch']} кг" for x in r)
    await message.answer(f"⚗️ Рецептура:\n\n{lines}\n\nИтого: {total:.2f} кг/замес\n\n"
                         f"Изменить: <code>/recipe Компонент кг</code>")

@dp.message_handler(commands=["recipe"], state="*")
async def recipe_update(message: types.Message, state: FSMContext):
    if get_user_role(message.from_user.id) != "boss":
        await message.answer("⛔ Нет доступа"); return
    p = message.text.split(maxsplit=2)
    if len(p) < 3: await message.answer("Формат: /recipe Компонент кг"); return
    update_recipe(p[1], float(p[2]))
    await message.answer(f"✅ {p[1]}: {p[2]} кг/замес")

@dp.message_handler(lambda m: m.text == "👥 Пользователи", state="*")
async def users_list(message: types.Message, state: FSMContext):
    if get_user_role(message.from_user.id) != "boss":
        await message.answer("⛔ Нет доступа"); return
    users = get_all_users()
    if not users: await message.answer("Нет пользователей."); return
    lines = [f"• <b>{u['name']}</b> {('@'+u['username']) if u['username'] else ''}\n"
             f"  {ROLE_NAMES.get(u['role'],u['role'])} · ID: <code>{u['tg_id']}</code>"
             for u in users]
    await message.answer("👥 <b>Пользователи:</b>\n\n"+"\n\n".join(lines)+
                         "\n\nОтозвать: <code>/revoke TG_ID</code>")

@dp.message_handler(commands=["revoke"], state="*")
async def revoke_cmd(message: types.Message, state: FSMContext):
    if get_user_role(message.from_user.id) != "boss":
        await message.answer("⛔ Нет доступа"); return
    p = message.text.split()
    if len(p) < 2: await message.answer("Формат: /revoke TG_ID"); return
    revoke_user(int(p[1])); await message.answer(f"✅ Доступ для {p[1]} отозван.")

@dp.message_handler(lambda m: m.text == "🔑 Коды доступа", state="*")
async def codes_show(message: types.Message, state: FSMContext):
    if get_user_role(message.from_user.id) != "boss":
        await message.answer("⛔ Нет доступа"); return
    codes = get_codes()
    lines = "\n".join(f"  {ROLE_NAMES.get(c['role'],c['role'])}: <code>{c['code']}</code>" for c in codes)
    await message.answer(f"🔑 <b>Коды доступа:</b>\n\n{lines}\n\n"
                         f"Сменить: <code>/code mixer новый_код</code>")

@dp.message_handler(commands=["code"], state="*")
async def code_update(message: types.Message, state: FSMContext):
    if get_user_role(message.from_user.id) != "boss":
        await message.answer("⛔ Нет доступа"); return
    p = message.text.split()
    if len(p) < 3: await message.answer("Формат: /code роль код"); return
    update_code(p[1], p[2])
    await message.answer(f"✅ Код для {p[1]}: <code>{p[2]}</code>")


@dp.message_handler(lambda m: m.text == "📋 Задание на неделю", state="*")
async def boss_view_tasks(message: types.Message, state: FSMContext):
    role = get_user_role(message.from_user.id)
    if role not in ("boss", "extruder"):
        await message.answer("⛔ Нет доступа"); return
    tasks = fetch_tasks()
    if not tasks:
        await message.answer(
            "📋 Задание не задано.\n\nДобавьте задание через веб-панель → раздел Задание.",
            reply_markup=role_menu(role)
        ); return
    week = tasks[0].get("week_start", "")
    lines = []
    total_plan = 0
    total_done = 0
    for t in tasks:
        status = "✅" if t["done"] else ("🟡" if t["pct"] >= 50 else "🔴")
        bar = "█" * (t["pct"] // 10) + "░" * (10 - t["pct"] // 10)
        lines.append(
            f"{status} <b>{t['decor']}</b>\n"
            f"   {bar} {t['pct']}%\n"
            f"   {t['done_qty']}/{t['plan_qty']} листов · {t['done_cnt']}/{t['pallets_needed']} паллет"
        )
        total_plan += t["plan_qty"]
        total_done += t["done_qty"]
    total_pct = round(total_done / total_plan * 100) if total_plan else 0
    await message.answer(
        f"📋 <b>Задание · неделя с {week}</b>\n\n" +
        "\n\n".join(lines) +
        f"\n\n{'─'*25}\n"
        f"Итого: {total_done}/{total_plan} листов ({total_pct}%)",
        reply_markup=role_menu(role)
    )


# ── ИИ АССИСТЕНТ ──────────────────────────────────────────────────────────────

class AIChat(StatesGroup):
    waiting = State()

@dp.message_handler(lambda m: m.text == "🤖 ИИ Ассистент", state="*")
async def ai_start(message: types.Message, state: FSMContext):
    role = get_user_role(message.from_user.id)
    if role != "boss":
        await message.answer("⛔ Нет доступа"); return
    await AIChat.waiting.set()
    await message.answer(
        "🤖 <b>ИИ Ассистент</b>\n\n"
        "Я знаю всё о вашем производстве. Спрашивайте:\n\n"
        "• Сколько листов выпущено за неделю?\n"
        "• Какой % брака по декору 82019-9?\n"
        "• Сколько паллет на складе?\n"
        "• Что сейчас в транзите?\n\n"
        "Введите вопрос или нажмите ◀️ Выйти из ИИ",
        reply_markup=kb("◀️ Выйти из ИИ")
    )

@dp.message_handler(state=AIChat.waiting)
async def ai_answer(message: types.Message, state: FSMContext):
    if message.text in ["◀️ Выйти из ИИ", "/done"]:
        await state.finish()
        await show_menu(message, "boss"); return

    thinking = await message.answer("🤔 Анализирую данные...")

    try:
        import urllib.request as ur
        import json as js

        # Собираем актуальные данные производства
        tasks = fetch_tasks()
        today = __import__('datetime').date.today().strftime("%d.%m.%Y")
        report = get_daily_report(today)
        warehouse = get_warehouse_summary()
        warehouse_total = get_warehouse_total()
        transit = get_transit_pallets()

        context = f"""Ты — аналитик производства ЛВТ-ламината. Отвечай кратко и по делу на русском языке.

ДАННЫЕ ПРОИЗВОДСТВА (актуальные):

📅 Сегодня: {today}

📦 Выпуск сегодня:
- Листов: {report["total_qty"]}
- Брак: {report["total_defect"]} ({round(report["total_defect"]/report["total_qty"]*100,1) if report["total_qty"] else 0}%)
- Замесов: {report["batches"]}
- Сырьё: {report["total_kg"]} кг

По декорам сегодня:
{chr(10).join(f"  {d['decor']}: {d['qty']} шт, брак {d['defect']}" for d in report["by_decor"]) or "  нет данных"}

🏭 Транзитная зона: {len(transit)} паллет
{chr(10).join(f"  {p['decor']} #{p['pallet_num']} - {p['qty']} шт" for p in transit) or "  пусто"}

🏪 Склад:
- Всего: {warehouse_total.get("total",0)} листов, {warehouse_total.get("pallets",0)} паллет
{chr(10).join(f"  {s['decor']}: {s['total_qty']} шт ({s['pallets']} паллет)" for s in warehouse) or "  пусто"}

📋 Текущее задание:
{chr(10).join(f"  {t['decor']}: {t['done_qty']}/{t['plan_qty']} листов ({t['pct']}%)" for t in tasks) or "  задание не задано"}
"""

        ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
        if not ANTHROPIC_KEY:
            await thinking.delete()
            await message.answer("⚠️ ANTHROPIC_API_KEY не задан в переменных окружения.")
            return

        payload = js.dumps({
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": f"{context}\n\nВопрос: {message.text}"}]
        }).encode()

        req = ur.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01"
            },
            method="POST"
        )
        with ur.urlopen(req, timeout=30) as resp:
            result = js.loads(resp.read())
            answer = result["content"][0]["text"]

        await thinking.delete()
        await message.answer(
            f"🤖 {answer}",
            reply_markup=kb("◀️ Выйти из ИИ")
        )

    except Exception as e:
        await thinking.delete()
        await message.answer(f"⚠️ Ошибка: {str(e)[:200]}")

@dp.message_handler(state="*")
async def fallback(message: types.Message, state: FSMContext):
    role = get_user_role(message.from_user.id)
    if role: await show_menu(message, role)
    else: await message.answer("Введите /start")

if __name__ == "__main__":
    init_db()
    print("Бот запущен (aiogram 2.x)...")
    executor.start_polling(dp, skip_updates=True)
