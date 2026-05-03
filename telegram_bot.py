"""
telegram_bot.py — Telegram Bot Listener (الجديد في v8)
يستقبل أوامر من تيليقرام ويرد عليها فوراً:
    /start    — رسالة ترحيب
    /picks    — أفضل 5 أخبار اليوم بصيغة Twitter-ready
    /saudi    — أفضل 5 أخبار سعودية اليوم
    /tech     — أفضل 5 أخبار تقنية
    /help     — قائمة الأوامر

يشتغل بالـ long polling (مو webhook) عشان ما يحتاج public URL.
"""

import logging
import time
from threading import Thread

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, is_saudi_news

log = logging.getLogger(__name__)

API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


# ═══════════════════════════════════════════════
# Cache بسيط للأخبار
# ═══════════════════════════════════════════════
_news_cache: list[dict] = []
_cache_timestamp: float = 0
CACHE_TTL = 1800  # 30 دقيقة


def update_news_cache(articles: list[dict]) -> None:
    """يحدّث cache الأخبار. يُستدعى من main عند كل دورة."""
    global _news_cache, _cache_timestamp
    _news_cache = articles
    _cache_timestamp = time.time()
    log.info("[bot] cache محدّث: %d خبر", len(articles))


def get_cached_news() -> list[dict]:
    """يرجع الأخبار من cache أو فارغ."""
    if time.time() - _cache_timestamp > CACHE_TTL:
        return []
    return _news_cache


# ═══════════════════════════════════════════════
# Polling
# ═══════════════════════════════════════════════
def get_updates(offset: int = 0) -> list[dict]:
    """يجلب آخر الرسائل من تيليقرام."""
    try:
        r = requests.get(
            f"{API_URL}/getUpdates",
            params={"offset": offset, "timeout": 30},
            timeout=35,
        )
        if r.status_code == 200:
            data = r.json()
            return data.get("result", [])
        else:
            log.warning("[bot] getUpdates HTTP %s", r.status_code)
            return []
    except requests.exceptions.Timeout:
        return []
    except Exception as e:
        log.error("[bot] getUpdates exception: %s", e)
        time.sleep(5)
        return []


def send_chat_action(chat_id: str, action: str = "typing") -> None:
    """يظهر 'يكتب...' في تيليقرام."""
    try:
        requests.post(
            f"{API_URL}/sendChatAction",
            json={"chat_id": chat_id, "action": action},
            timeout=5,
        )
    except Exception:
        pass


# ═══════════════════════════════════════════════
# معالجة الأوامر
# ═══════════════════════════════════════════════
def handle_start(chat_id: str) -> None:
    from telegram_sender import send_message
    text = (
        "👋 <b>أهلاً بك في AI News Bot v8</b>\n\n"
        "أنا بوت أخبار ذكي أرسل لك أهم الأخبار التقنية والسعودية يومياً.\n\n"
        "<b>📋 الأوامر المتاحة:</b>\n"
        "🌟 /picks — أفضل 5 أخبار اليوم (جاهزة لتويتر)\n"
        "🇸🇦 /saudi — أفضل 5 أخبار سعودية\n"
        "💻 /tech — أفضل 5 أخبار تقنية\n"
        "❓ /help — هذه القائمة\n\n"
        "<b>📅 المواعيد التلقائية:</b>\n"
        "8 صباحاً · 1 ظهراً · 6 مساءً · 10 مساءً\n\n"
        "كل خبر يأتي مع <b>نسخة جاهزة لتويتر</b> + زر نشر مباشر 🐦"
    )
    send_message(text, chat_id=chat_id)


def handle_help(chat_id: str) -> None:
    handle_start(chat_id)


def handle_picks(chat_id: str, filter_type: str = "all") -> None:
    """يرسل أفضل أخبار حسب الفلتر."""
    from telegram_sender import send_message, send_news_digest
    from groq_client import GroqClient

    send_chat_action(chat_id, "typing")

    cached = get_cached_news()
    if not cached:
        send_message(
            "⏳ ما عندي أخبار محدّثة حالياً.\n"
            "البوت ينتظر الدورة القادمة.\n\n"
            "الدورات: 8ص · 1ظ · 6م · 10م",
            chat_id=chat_id,
        )
        return

    # طبّق الفلتر
    if filter_type == "saudi":
        filtered = [a for a in cached if is_saudi_news(a)]
        cycle_name = "🇸🇦 أفضل 5 أخبار سعودية"
        if not filtered:
            send_message("ما لقيت أخبار سعودية حالياً 😕", chat_id=chat_id)
            return
    elif filter_type == "tech":
        tech_keywords = ["AI", "ذكاء", "تقنية", "tech", "OpenAI", "Anthropic", "Google"]
        filtered = [
            a for a in cached
            if any(kw.lower() in (a.get("title", "") + a.get("summary", "")).lower()
                   for kw in tech_keywords)
        ]
        cycle_name = "💻 أفضل 5 أخبار تقنية"
        if not filtered:
            send_message("ما لقيت أخبار تقنية حالياً 😕", chat_id=chat_id)
            return
    else:
        filtered = cached
        cycle_name = "🌟 أفضل 5 أخبار اليوم"

    # ولّد picks
    send_message("⚡ جاري اختيار أفضل الأخبار وصياغتها لتويتر...", chat_id=chat_id)
    send_chat_action(chat_id, "typing")

    try:
        groq = GroqClient()
        picks = groq.generate_picks(filtered, count=5)
        if not picks:
            send_message("❌ فشل توليد الأخبار، حاول مرة ثانية.", chat_id=chat_id)
            return
        send_news_digest(picks, cycle_name=cycle_name, show_twitter_versions=True)
    except Exception as e:
        log.error("[bot] picks failed: %s", e)
        send_message(f"❌ خطأ: {str(e)[:200]}", chat_id=chat_id)


def handle_command(message: dict) -> None:
    """يوزّع الأوامر."""
    chat = message.get("chat", {})
    chat_id = str(chat.get("id", ""))
    if not chat_id:
        return

    text = (message.get("text") or "").strip()
    log.info("[bot] أمر من %s: %s", chat_id, text)

    # افصل الأمر
    cmd = text.split()[0].lower() if text else ""
    if "@" in cmd:  # /picks@FahadNewsBot
        cmd = cmd.split("@")[0]

    if cmd == "/start":
        handle_start(chat_id)
    elif cmd == "/help":
        handle_help(chat_id)
    elif cmd == "/picks":
        handle_picks(chat_id, "all")
    elif cmd == "/saudi":
        handle_picks(chat_id, "saudi")
    elif cmd == "/tech":
        handle_picks(chat_id, "tech")
    else:
        # تجاهل أو رد بسيط
        if cmd.startswith("/"):
            from telegram_sender import send_message
            send_message(
                f"❓ أمر غير معروف: <code>{cmd}</code>\n"
                f"اكتب /help للأوامر المتاحة.",
                chat_id=chat_id,
            )


# ═══════════════════════════════════════════════
# الـ Polling Loop
# ═══════════════════════════════════════════════
def polling_loop() -> None:
    """يستمع لرسائل تيليقرام بشكل مستمر."""
    if not TELEGRAM_BOT_TOKEN:
        log.warning("[bot] لا يوجد TOKEN — البوت معطّل")
        return

    log.info("[bot] 🤖 Telegram polling started")
    offset = 0

    while True:
        try:
            updates = get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message") or update.get("edited_message")
                if not message:
                    continue
                if message.get("text", "").startswith("/"):
                    handle_command(message)
        except Exception as e:
            log.error("[bot] polling exception: %s", e)
            time.sleep(5)


def start_bot_in_background() -> None:
    """يشغّل البوت في thread منفصل."""
    if not TELEGRAM_BOT_TOKEN:
        return
    thread = Thread(target=polling_loop, daemon=True, name="telegram-polling")
    thread.start()
    log.info("[bot] ✅ Polling thread started")
