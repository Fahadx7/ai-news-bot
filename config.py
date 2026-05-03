"""
config.py — إعدادات البوت v8
"""

import os
from zoneinfo import ZoneInfo

# ═══ المنطقة الزمنية ═══
RIYADH_TZ = ZoneInfo("Asia/Riyadh")

# ═══ مفاتيح API ═══
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# ═══ نماذج Groq ═══
GROQ_MODELS = [
    os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
    "llama-3.1-8b-instant",
    "openai/gpt-oss-120b",
]

# ═══ إعدادات الجلب ═══
PARALLEL_WORKERS = 18
FETCH_TIMEOUT = 25
SOURCE_RETRIES = 1

# ═══ Curation ═══
BATCH_SIZE = 8
MAX_TITLE_LEN = 120
MAX_SUMMARY_LEN = 200
MAX_PAYLOAD_KB = 6
MAX_FINAL_NEWS = 10
MAX_FINAL_VIDEOS = 4
PREFILTER_MAX = 80

# ═══ الجدولة ═══
SCHEDULE_HOURS = [8, 13, 18, 22]
DAILY_REPORT_HOUR = 23

# ═══════════════════════════════════════════════
# مصادر RSS
# ═══════════════════════════════════════════════

# 🇸🇦 مصادر سعودية فقط
SAUDI_SOURCES = [
    "https://sabq.org/feed",
    "https://www.spa.gov.sa/RssFeeds.php?cat=1&l=ar",
    "https://www.spa.gov.sa/RssFeeds.php?cat=4&l=ar",
    "https://www.alriyadh.com/file/rss/saudi.xml",
    "https://www.okaz.com.sa/rss",
    "https://www.alyaum.com/rss",
    "https://www.al-jazirah.com/rss/local.xml",
    "https://www.aleqt.com/rss/economy.xml",
    "https://www.argaam.com/ar/rss/main",
    "https://www.makkahnewspaper.com/rss/saudi-arabia",
    "https://www.alwatan.com.sa/rss",
    "https://www.al-madina.com/rss/saudi.xml",
    "https://aawsat.com/feed",
    "https://www.alarabiya.net/.mrss/ar/saudi-today.xml",
]

# 🌍 مصادر عربية عامة
ARABIC_SOURCES = [
    "https://www.aljazeera.net/aljazeerarss/a7c186be-1baa-4bd4-9d80-a84db769f779/73d0e1b4-532f-45ef-b135-bfdff8b8cab9",
    "https://arabic.cnn.com/api/v1/rss/middle_east/rss.xml",
    "https://www.bbc.com/arabic/index.xml",
    "https://www.alarabiya.net/.mrss/ar.xml",
    "https://www.skynewsarabia.com/web/rss/97.xml",
    "https://www.france24.com/ar/rss",
    "https://www.dw.com/ar/rss/all-rss/s-9119",
]

# 💻 مصادر تقنية إنجليزية
TECH_SOURCES = [
    "https://feeds.reuters.com/reuters/technologyNews",
    "https://www.theverge.com/rss/index.xml",
    "https://techcrunch.com/feed/",
    "https://feeds.arstechnica.com/arstechnica/index",
    "https://www.wired.com/feed/rss",
    "https://venturebeat.com/feed/",
    "https://www.engadget.com/rss.xml",
]

# 🤖 مصادر AI متخصصة
AI_SOURCES = [
    "https://openai.com/blog/rss/",
    "https://www.anthropic.com/news/rss",
    "https://deepmind.google/blog/rss.xml",
    "https://huggingface.co/blog/feed.xml",
]

# 📊 مصادر اقتصاد
FINANCE_SOURCES = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://www.ft.com/rss/home",
]

RSS_SOURCES = {
    "saudi": SAUDI_SOURCES,
    "ar": ARABIC_SOURCES,
    "tech": TECH_SOURCES,
    "ai": AI_SOURCES,
    "finance": FINANCE_SOURCES,
}

# ═══════════════════════════════════════════════
# Google News Queries
# ═══════════════════════════════════════════════
GOOGLE_NEWS_QUERIES = {
    "saudi": [
        "السعودية اقتصاد",
        "السعودية تقنية",
        "رؤية 2030",
        "نيوم",
        "صندوق الاستثمارات العامة",
        "أرامكو",
        "هيئة الذكاء الاصطناعي السعودية",
    ],
    "tech": [
        "ذكاء اصطناعي",
        "OpenAI",
        "Anthropic Claude",
        "AI breakthrough",
        "AI startup funding",
    ],
}

# ═══════════════════════════════════════════════
# كلمات مفتاحية لتصنيف الأخبار السعودية
# ═══════════════════════════════════════════════
SAUDI_KEYWORDS = [
    "السعودية", "المملكة", "الرياض", "جدة", "مكة", "المدينة المنورة",
    "نيوم", "NEOM", "أرامكو", "Aramco", "صندوق الاستثمارات",
    "رؤية 2030", "Vision 2030", "ولي العهد", "المملكة العربية",
    "Saudi", "الهيئة السعودية", "وزارة سعودية", "سدير",
    "روشن", "القدية", "الدرعية", "البحر الأحمر",
    "ستة", "لوسيل", "الفيصلية",
]


def is_saudi_news(article: dict) -> bool:
    """يحدد إذا كان الخبر سعودياً بناءً على الكلمات المفتاحية."""
    text = (
        (article.get("title", "") + " " + article.get("summary", ""))
        .lower()
    )
    keywords_lower = [kw.lower() for kw in SAUDI_KEYWORDS]
    return any(kw in text for kw in keywords_lower)
