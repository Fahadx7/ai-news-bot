"""
telegram_sender.py — يرسل الأخبار لتيليقرام
"""

import logging
from typing import Optional

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

log = logging.getLogger(__name__)


def send_message(
    text: str,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML",
    disable_preview: bool = False,
) -> bool:
    """يرسل رسالة لتيليقرام."""
    if not TELEGRAM_BOT_TOKEN:
        log.warning("[telegram] لا يوجد TELEGRAM_BOT_TOKEN — تخطّي")
        return False

    chat_id = chat_id or TELEGRAM_CHAT_ID
    if not chat_id:
        log.warning("[telegram] لا يوجد TELEGRAM_CHAT_ID")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    # تيليقرام يحدد كل رسالة بـ 4096 حرف
    if len(text) > 4000:
        text = text[:3990] + "...\n\n[محتوى مقطوع]"

    try:
        r = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": disable_preview,
            },
            timeout=15,
        )
        if r.status_code == 200:
            log.info("[telegram] ✅ نُشرت رسالة")
            return True
        else:
            log.error("[telegram] ❌ HTTP %s: %s", r.status_code, r.text[:200])
            return False
    except Exception as e:
        log.error("[telegram] ❌ exception: %s", e)
        return False


def format_news_digest(articles: list[dict], cycle_name: str = "نشرة") -> str:
    """يصيغ قائمة أخبار لتيليقرام."""
    if not articles:
        return f"📰 <b>{cycle_name}</b>\n\nلا توجد أخبار مهمة الآن."

    lines = [f"📰 <b>{cycle_name}</b>\n"]

    for i, a in enumerate(articles, start=1):
        emoji = a.get("emoji", "•")
        title = a.get("title_ar") or a.get("title", "")
        summary = a.get("summary_ar") or ""
        source = a.get("source", "")
        url = a.get("url", "")

        lines.append(f"\n{emoji} <b>{title}</b>")
        if summary:
            lines.append(summary)
        if source:
            lines.append(f"<i>المصدر: {source}</i>")
        if url:
            lines.append(f'<a href="{url}">قراءة المزيد</a>')

    return "\n".join(lines)
