import re
import asyncio
import gspread
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from oauth2client.service_account import ServiceAccountCredentials
import os

from aiohttp import web  # <-- HTTP server uchun qo‘shimcha

# ===========================
# BOT TOKEN (ENV dan oling)
# ===========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # Render.com da ENV o'rnatiladi
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN ENV o'rnatilmagan!")

GROUP_CHAT_ID = -4999278892

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ===========================
# GOOGLE SHEET ulanish
# ===========================
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
client = gspread.authorize(creds)

sheet_employees = client.open("WorkTime").worksheet("Employees")
sheet_records = client.open("WorkTime").worksheet("Record")

# ===========================
# Xodimni ID orqali topish
# ===========================
def get_employee_name(user_id: int):
    for emp in sheet_employees.get_all_records():
        if str(emp.get("ID")) == str(user_id):
            return emp.get("F.I.SH")
    return None

# ===========================
# VAQT AJRATISH
# ===========================
def extract_times(text: str):
    pattern = r"(\d{1,2})\D+(\d{2})\D+(\d{1,2})\D+(\d{2})"
    m = re.search(pattern, text)
    if not m:
        return None, None

    sh, sm, eh, em = m.groups()
    if not (0 <= int(sh) <= 23 and 0 <= int(eh) <= 23):
        return None, None
    if not (0 <= int(sm) <= 59 and 0 <= int(em) <= 59):
        return None, None

    return f"{sh.zfill(2)}:{sm.zfill(2)}", f"{eh.zfill(2)}:{em.zfill(2)}"

# ===========================
# ISH SOATINI HISOBLASH
# ===========================
def calc_hours(start, end):
    fmt = "%H:%M"
    s = datetime.strptime(start, fmt)
    e = datetime.strptime(end, fmt)
    hours = (e - s).seconds / 3600

    deduct = 0
    if e.time() >= datetime.strptime("16:00", fmt).time():
        deduct = 1
    elif e.time() >= datetime.strptime("12:00", fmt).time():
        deduct = 0.5
    if s.time() > datetime.strptime("13:00", fmt).time():
        deduct += 0.5

    return round(max(hours - deduct, 0), 2)

# ===========================
# MESSAGE_ID BO‘YICHA UPDATE
# ===========================
def update_record_by_message_id(message_id, new_row):
    rows = sheet_records.get_all_values()
    for idx, row in enumerate(rows, start=1):
        if row and row[0] == str(message_id):
            sheet_records.update(f"A{idx}:H{idx}", [new_row])
            return True
    return False

# ===========================
# START
# ===========================
@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer("✅ Ish vaqti bot ishga tushdi.")

# ===========================
# Oldingi sanani ochirish
# ===========================
def delete_record_by_user_and_date(user_id, date_str):
    rows = sheet_records.get_all_values()
    rows_to_delete = []

    for idx, row in enumerate(rows[1:], start=2):
        if len(row) >= 2 and row[0] == str(user_id) and row[1] == date_str:
            rows_to_delete.append(idx)

    for idx in reversed(rows_to_delete):
        sheet_records.delete_rows(idx)

    return len(rows_to_delete)

# ===========================
# YANGI XABAR SAQLASH
# ===========================
@dp.message()
async def save_time(message: types.Message):
    user_id = message.from_user.id
    name = get_employee_name(user_id)
    if not name:
        return

    lines = message.text.splitlines()
    date_pattern = r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})"
    current_date = None
    saved_count = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        date_match = re.search(date_pattern, line)
        if date_match:
            raw = date_match.group(1).replace("/", ".").replace("-", ".")
            d, m, y = raw.split(".")
            if len(y) == 2:
                y = "20" + y
            current_date = datetime.strptime(f"{d}.{m}.{y}", "%d.%m.%Y").date()
            continue

        if not current_date:
            continue

        start, end = extract_times(line)

        if start and end:
            hours = calc_hours(start, end)
            row = [ user_id, str(current_date), name, start, end, hours, line,message.message_id]
        else:
            row = [ user_id, str(current_date), name, "DAY", "OFF", 0, line,message.message_id]

        delete_record_by_user_and_date(user_id, str(current_date))
        sheet_records.append_row(row)

        current_date = None
        saved_count += 1

    if saved_count:
        await message.reply(f"✅ {saved_count} ta sana saqlandi")

# ===========================
# ✏️ EDIT QILINGANDA YANGILASH
# ===========================
@dp.edited_message()
async def edit_time(message: types.Message):
    user_id = message.from_user.id
    name = get_employee_name(user_id)
    if not name:
        return

    lines = message.text.splitlines()
    date_pattern = r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})"
    current_date = None
    updated_count = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        date_match = re.search(date_pattern, line)
        if date_match:
            raw = date_match.group(1).replace("/", ".").replace("-", ".")
            d, m, y = raw.split(".")
            if len(y) == 2:
                y = "20" + y
            current_date = datetime.strptime(f"{d}.{m}.{y}", "%d.%m.%Y").date()
            continue

        if not current_date:
            continue

        start, end = extract_times(line)

        if start and end:
            hours = calc_hours(start, end)
            row = [user_id, str(current_date), name, start, end, hours, line,message.message_id]
        else:
            row = [user_id, str(current_date), name, "DAY", "OFF", 0, line,message.message_id]

        if not update_record_by_message_id(message.message_id, row):
            delete_record_by_user_and_date(user_id, str(current_date))
            sheet_records.append_row(row)

        current_date = None
        updated_count += 1

    if updated_count:
        await message.reply(f"✏️ {updated_count} ta sana yangilandi")

# ===========================
# ESLATMA
# ===========================
async def remind_missing_times():
    yesterday = (datetime.now() - timedelta(days=1)).date()
    yesterday_str = yesterday.strftime("%Y-%m-%d")  # YYYY-MM-DD format

    employees = sheet_employees.get_all_records()
    records = sheet_records.get_all_records()

    submitted = {r["name"] for r in records if r.get("date") == yesterday_str}

    missing = [e["F.I.SH"] for e in employees if e["F.I.SH"] not in submitted]

    if not missing:
        return

    text = f"⏰ *Eslatma!*\n📅 Sana: {yesterday_str}\n\n❌ Ish vaqtini kiritmaganlar:\n"
    text += "\n".join(f"• {n}" for n in missing)
    text += "\n\nIltimos ish soatlarni vaqtida yuboringlar!!!"

    await bot.send_message(GROUP_CHAT_ID, text, parse_mode="Markdown")

# ===========================
# FAKE HTTP SERVER (Render Port uchun)
# ===========================
async def handle(request):
    return web.Response(text="Bot ishga tushdi!")

async def start_web():
    app = web.Application()
    app.router.add_get("/", handle)

    port = int(os.environ.get("PORT", 8000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

# ===========================
# RUN
# ===========================
async def main():
    scheduler = AsyncIOScheduler(timezone='Asia/Tashkent')
    scheduler.add_job(remind_missing_times, "cron", hour=9, minute=0)
    scheduler.add_job(remind_missing_times, "cron", hour=17, minute=10)
    scheduler.start()

    # Web server + polling bot parallel
    await asyncio.gather(
        start_web(),     # Render Free port uchun
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())
