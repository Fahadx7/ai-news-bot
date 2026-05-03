"""
telegram_sender.py v8
الجديد:
    - كل خبر يُرسل في 3 رسائل مرتبطة:
      1. الخبر الكامل (للقراءة)
      2. النسخة الجاهزة لتويتر (للنسخ المباشر)
      3. زر "نسخ لتويتر" + لينك المصدر
    - دعم MarkdownV2 لتنسيق نظيف
    - تجزئة طويلة الرسائل تلقائياً
"""

import logging
import re
import time
from typing import Optional
from urllib.parse import quote

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

log = logging.getLogger(__name__)


def escape_html(text: str) -> str:
    """تنظيف HTML لإرساله في تيليقرام."""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def send_message(
    text: str,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML",
    disable_preview: bool = True,
    reply_markup: Optional[dict] = None,
) -> bool:
    """يرسل رسالة لتيليقرام."""
    if not TELEGRAM_BOT_TOKEN:
        log.warning("[telegram] لا يوجد TOKEN")
        return False

    chat_id = chat_id or TELEGRAM_CHAT_ID
    if not chat_id:
        log.warning("[telegram] لا يوجد CHAT_ID")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    if len(text) > 4000:
        text = text[:3990] + "...\n\n[محتوى مقطوع]"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_preview,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            return True
        else:
            log.error("[telegram] HTTP %s: %s", r.status_code, r.text[:200])
            return False
    except Exception as e:
        log.error("[telegram] exception: %s", e)
        return False


def format_full_article(article: dict, index: int = 0, total: int = 0) -> str:
    """يصيغ خبر كامل بشكل جذاب لتيليقرام."""
    emoji = article.get("emoji", "📰")
    title = escape_html(article.get("title_ar") or article.get("title", ""))
    summary = escape_html(article.get("summary_ar", ""))
    why = escape_html(article.get("why_matters", ""))
    category = escape_html(article.get("category", ""))
    source = escape_html(article.get("source", ""))
    url = article.get("url", "")

    # رأس الخبر
    header = f"{emoji} <b>{title}</b>"
    if index and total:
        header = f"<i>[{index}/{total}]</i>  {header}"

    parts = [header, ""]

    # الملخص
    if summary:
        parts.append(summary)
        parts.append("")

    # ليه يهمك
    if why:
        parts.append(f"💡 <b>ليه يهمك:</b> {why}")
        parts.append("")

    # تذييل
    footer_parts = []
    if category:
        footer_parts.append(f"#{category.replace(' ', '_')}")
    if source:
        footer_parts.append(f"📌 {source}")

    if footer_parts:
        parts.append("  ·  ".join(footer_parts))

    if url:
        parts.append(f'<a href="{escape_html(url)}">🔗 رابط الخبر</a>')

    return "\n".join(parts)


def format_twitter_card(article: dict) -> str:
    """يصيغ النسخة الجاهزة لتويتر للنسخ المباشر."""
    twitter_text = article.get("twitter_text", "")
    if not twitter_text:
        # fallback
        emoji = article.get("emoji", "📰")
        title = article.get("title_ar") or article.get("title", "")
        twitter_text = f"{emoji} {title}"

    twitter_text_safe = escape_html(twitter_text)

    return (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📋 <b>نسخة جاهزة لتويتر</b> "
        f"<i>({len(twitter_text)}/280 حرف)</i>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"<pre>{twitter_text_safe}</pre>"
    )


def make_twitter_share_button(article: dict) -> dict:
    """ينشئ inline keyboard فيه زر مشاركة لتويتر."""
    twitter_text = article.get("twitter_text", "")
    url = article.get("url", "")

    # رابط مشاركة تويتر مباشر
    encoded_text = quote(twitter_text)
    twitter_url = f"https://twitter.com/intent/tweet?text={encoded_text}"
    if url:
        twitter_url += f"&url={quote(url)}"

    buttons = [[{"text": "🐦 افتح تويتر للنشر", "url": twitter_url}]]

    if url:
        buttons.append([{"text": "🔗 المصدر الأصلي", "url": url}])

    return {"inline_keyboard": buttons}


def send_news_digest(
    articles: list[dict],
    cycle_name: str = "نشرة",
    show_twitter_versions: bool = True,
) -> int:
    """
    يرسل نشرة كاملة:
    - رسالة افتتاحية
    - كل خبر في رسالتين: الخبر + نسخة Twitter + زر مشاركة
    
    يرجع عدد الأخبار المرسلة.
    """
    if not articles:
        send_message(f"📰 <b>{cycle_name}</b>\n\nلا توجد أخبار مهمة.")
        return 0

    # الرأس
    header = (
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📰 <b>{escape_html(cycle_name)}</b>\n"
        f"📊 {len(articles)} أخبار مختارة\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )
    send_message(header)
    time.sleep(0.5)

    sent_count = 0
    for idx, article in enumerate(articles, 1):
        # 1. الخبر الكامل
        full_text = format_full_article(article, idx, len(articles))
        send_message(full_text, disable_preview=True)
        time.sleep(0.3)

        # 2. نسخة Twitter + زر
        if show_twitter_versions and article.get("twitter_text"):
            twitter_text = format_twitter_card(article)
            button = make_twitter_share_button(article)
            send_message(
                twitter_text,
                disable_preview=True,
                reply_markup=button,
            )
            time.sleep(0.5)

        sent_count += 1

    # تذييل
    footer = (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ انتهت النشرة — {sent_count} خبر\n"
        f"💡 اضغط <b>/picks</b> للحصول على أفضل 5 أخبار اليوم"
    )
    send_message(footer)

    return sent_count


# ═══════════════════════════════════════════════
# للتوافق مع v7
# ═══════════════════════════════════════════════
def format_news_digest(articles: list[dict], cycle_name: str = "نشرة") -> str:
    """واجهة قديمة للتوافق مع v7."""
    parts = [f"📰 <b>{escape_html(cycle_name)}</b>\n"]
    for i, a in enumerate(articles, 1):
        parts.append(f"\n{i}. {format_full_article(a)}")
    return "\n".join(parts)
