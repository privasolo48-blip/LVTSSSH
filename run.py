#!/usr/bin/env python3
"""
Запуск бота и веб-панели одновременно (для локального тестирования)
"""
import subprocess
import sys
import os

os.chdir(os.path.dirname(__file__))

# Проверка .env
if not os.path.exists(".env"):
    if os.path.exists(".env.example"):
        import shutil
        shutil.copy(".env.example", ".env")
        print("⚠️  Создан файл .env из примера. Заполни BOT_TOKEN и BOSS_IDS!")
        sys.exit(1)

from dotenv import load_dotenv
load_dotenv()

token = os.getenv("BOT_TOKEN", "")
if not token or "ВСТАВЬ" in token or len(token) < 20:
    print("❌ Заполни BOT_TOKEN в файле .env")
    sys.exit(1)

print("🚀 Запуск ЛВТ Производство...")
print("   Веб-панель: http://localhost:5000")
print("   Бот: запущен (проверь Telegram)")
print("   Ctrl+C для остановки\n")

bot_proc = subprocess.Popen([sys.executable, "bot/bot.py"])
web_proc = subprocess.Popen([sys.executable, "web/app.py"])

try:
    bot_proc.wait()
    web_proc.wait()
except KeyboardInterrupt:
    print("\n⏹ Остановка...")
    bot_proc.terminate()
    web_proc.terminate()
