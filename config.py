"""
config.py — إعدادات البوت
"""

import os
from zoneinfo import ZoneInfo

# ═══ المنطقة الزمنية ═══
RIYADH_TZ = ZoneInfo("Asia/Riyadh")

# ═══ مفاتيح API (من Environment فقط) ═══
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# ═══ نماذج Groq (chain من الأقوى للأسرع) ═══
# الترتيب مهم: نبدأ بالأقوى، لو فشل ننتقل للأبسط
GROQ_MODELS = [
    os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),  # أساسي: 128K context
    "llama-3.1-8b-instant",                              # سريع: 128K context
    "openai/gpt-oss-120b",                               # كبير جداً
]

# ═══ إعدادات الجلب ═══
PARALLEL_WORKERS = 18
FETCH_TIMEOUT = 25  # ثانية لكل مصدر
SOURCE_RETRIES = 1

# ═══ إعدادات الـ Curation (الإصلاح الرئيسي للـ 413) ═══
# نقسم الأخبار على دفعات صغيرة بدل ما نرسلها مرة وحدة
BATCH_SIZE = 8                  # 8 أخبار لكل استدعاء Groq
MAX_TITLE_LEN = 120             # نقطع العنوان للضروري
MAX_SUMMARY_LEN = 200           # نقطع الملخص (بدل النص الكامل)
MAX_PAYLOAD_KB = 6              # حد أقصى لحجم الـ payload لكل request
MAX_FINAL_NEWS = 10             # عدد الأخبار النهائية بعد الـ curation
MAX_FINAL_VIDEOS = 4            # عدد الفيديوهات النهائية

# ═══ الجدولة (الرياض UTC+3) ═══
SCHEDULE_HOURS = [8, 13, 18, 22]  # 4 دورات أخبار يومياً
DAILY_REPORT_HOUR = 23            # تقرير شامل 11م

# ═══ مصادر RSS (مختصرة - عدّل حسب حاجتك) ═══
RSS_SOURCES = {
    "ar": [
        "https://www.aljazeera.net/aljazeerarss/a7c186be-1baa-4bd4-9d80-a84db769f779/73d0e1b4-532f-45ef-b135-bfdff8b8cab9",
        "https://arabic.cnn.com/api/v1/rss/middle_east/rss.xml",
        "https://www.bbc.com/arabic/index.xml",
        "https://www.alarabiya.net/.mrss/ar.xml",
        "https://www.skynewsarabia.com/web/rss/97.xml",
    ],
    "en": [
        "https://feeds.reuters.com/reuters/topNews",
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://www.theverge.com/rss/index.xml",
        "https://techcrunch.com/feed/",
        "https://feeds.arstechnica.com/arstechnica/index",
    ],
}

# ═══ Google News (مختصر) ═══
GOOGLE_NEWS_QUERIES = [
    "ذكاء اصطناعي",
    "OpenAI",
    "تقنية السعودية",
    "AI 2026",
    "Saudi Vision 2030",
]

# ═══ YouTube قنوات (channel IDs) ═══
YOUTUBE_CHANNELS = [
    # أضف channel IDs هنا
]
