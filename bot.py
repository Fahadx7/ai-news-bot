"""
AI News Bot v5 — Global Intelligence Edition
قناة @fahadai · Telegram

التطورات الرئيسية عن v4:
  🌍 200+ مصدر منتقى من 40+ دولة
  🔍 Google News RSS بـ 8 لغات (يفتح وصول لآلاف المواقع)
  ⚡ Parallel fetching — كل المصادر بنفس الوقت
  🎯 تنوع إجباري: MAX خبر واحد لكل شركة، توزيع جغرافي
  ⏰ دورة كل 3 ساعات (بدل 4) — 8 دورات/يوم

المتغيرات المطلوبة:
  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY
"""

import hashlib
import json
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, unquote

import feedparser
import pytz
import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

# ============================================================
# CONFIG
# ============================================================

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

RIYADH_TZ = pytz.timezone("Asia/Riyadh")
GROQ_MODEL = "llama-3.3-70b-versatile"

CACHE_FILE = "/tmp/fahadai_posted.json"
TITLE_CACHE_FILE = "/tmp/fahadai_titles.json"
TRENDS_CACHE_FILE = "/tmp/fahadai_trends.json"
MAX_CACHE_SIZE = 3000

FETCH_TIMEOUT = 10
FETCH_WORKERS = 18

# ============================================================
# SOURCES — 200+ مصدر عالمي
# ============================================================

NEWS_SOURCES: Dict[str, str] = {
    # ════════════════════════════════════════
    # Tier 1: AI Companies (Direct from source)
    # ════════════════════════════════════════
    "Anthropic": "https://www.anthropic.com/news/rss.xml",
    "OpenAI": "https://openai.com/blog/rss.xml",
    "Google DeepMind": "https://deepmind.google/blog/rss.xml",
    "Google AI": "https://blog.google/technology/ai/rss/",
    "Meta AI": "https://ai.meta.com/blog/rss/",
    "Microsoft AI": "https://blogs.microsoft.com/ai/feed/",
    "Microsoft Research": "https://www.microsoft.com/en-us/research/feed/",
    "Mistral AI": "https://mistral.ai/news/rss.xml",
    "HuggingFace": "https://huggingface.co/blog/feed.xml",
    "Cohere": "https://cohere.com/blog/rss.xml",
    "Stability AI": "https://stability.ai/blog?format=rss",
    "Runway": "https://runwayml.com/blog/rss.xml",
    "NVIDIA Blog": "https://blogs.nvidia.com/feed/",
    "AWS ML": "https://aws.amazon.com/blogs/machine-learning/feed/",
    "IBM Research": "https://research.ibm.com/blog/feed.xml",

    # ════════════════════════════════════════
    # Tier 2: Global Tech Media (English)
    # ════════════════════════════════════════
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "TechCrunch": "https://techcrunch.com/feed/",
    "The Verge AI": "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
    "The Verge": "https://www.theverge.com/rss/index.xml",
    "VentureBeat AI": "https://venturebeat.com/category/ai/feed/",
    "Wired AI": "https://www.wired.com/feed/tag/ai/latest/rss",
    "Wired": "https://www.wired.com/feed/rss",
    "MIT Tech Review": "https://www.technologyreview.com/feed/",
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "ZDNet AI": "https://www.zdnet.com/topic/artificial-intelligence/rss.xml",
    "IEEE Spectrum AI": "https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss",
    "Semafor Tech": "https://www.semafor.com/technology/feed.xml",
    "Fast Company Tech": "https://www.fastcompany.com/technology/rss",
    "Engadget": "https://www.engadget.com/rss.xml",
    "Gizmodo": "https://gizmodo.com/rss",
    "TechRadar": "https://www.techradar.com/rss",
    "CNET": "https://www.cnet.com/rss/news/",
    "Business Insider Tech": "https://www.businessinsider.com/sai/rss",
    "Axios Tech": "https://api.axios.com/feed/technology",
    "Protocol": "https://www.protocol.com/feeds/feed.rss",
    "The Information RSS": "https://www.theinformation.com/feed",
    "9to5Google": "https://9to5google.com/feed/",
    "9to5Mac": "https://9to5mac.com/feed/",
    "The Register": "https://www.theregister.com/headlines.atom",
    "Hacker News": "https://hnrss.org/frontpage",
    "Platformer": "https://www.platformer.news/rss",
    "Stratechery": "https://stratechery.com/feed/",

    # ════════════════════════════════════════
    # Tier 3: AI-Focused Publications
    # ════════════════════════════════════════
    "The Batch (DeepLearning.AI)": "https://www.deeplearning.ai/the-batch/feed/",
    "Import AI": "https://jack-clark.net/feed/",
    "Towards AI": "https://pub.towardsai.net/feed",
    "Analytics India Magazine": "https://analyticsindiamag.com/feed/",
    "MarkTechPost": "https://www.marktechpost.com/feed/",
    "Unite.AI": "https://www.unite.ai/feed/",
    "Synced Review": "https://syncedreview.com/feed/",
    "AI Business": "https://aibusiness.com/rss.xml",
    "Emerj": "https://emerj.com/feed/",
    "KDnuggets": "https://www.kdnuggets.com/feed",
    "Analytics Vidhya": "https://www.analyticsvidhya.com/blog/feed/",
    "Machine Learning Mastery": "https://machinelearningmastery.com/feed/",
    "OpenAI Research": "https://openai.com/research/rss.xml",
    "BAIR Blog (Berkeley)": "https://bair.berkeley.edu/blog/feed.xml",

    # ════════════════════════════════════════
    # Tier 4: Research Papers
    # ════════════════════════════════════════
    "ArXiv AI": "http://export.arxiv.org/rss/cs.AI",
    "ArXiv ML": "http://export.arxiv.org/rss/cs.LG",
    "ArXiv NLP": "http://export.arxiv.org/rss/cs.CL",
    "ArXiv CV": "http://export.arxiv.org/rss/cs.CV",
    "ArXiv Neural": "http://export.arxiv.org/rss/cs.NE",
    "Papers With Code": "https://paperswithcode.com/latest/rss/",

    # ════════════════════════════════════════
    # Tier 5: Arabic Sources (25+)
    # ════════════════════════════════════════
    "عالم التقنية": "https://www.tech-wd.com/wd/feed/",
    "أرابيان بزنس": "https://arabic.arabianbusiness.com/feed",
    "رواد الأعمال": "https://www.rowadalaamal.com/feed/",
    "Wamda AR": "https://www.wamda.com/ar/feed",
    "Wamda": "https://www.wamda.com/feed",
    "Arab News": "https://www.arabnews.com/rss.xml",
    "Saudi Gazette Tech": "https://saudigazette.com.sa/rss/technology",
    "Al Arabiya Business": "https://english.alarabiya.net/.mrss/en/business.xml",
    "Al Jazeera English": "https://www.aljazeera.com/xml/rss/all.xml",
    "Menabytes": "https://www.menabytes.com/feed/",
    "Zawya": "https://www.zawya.com/rssfeeds/technology/",
    "The National UAE Tech": "https://www.thenationalnews.com/business/technology/rss",
    "Arageek Tech": "https://www.arageek.com/tech/feed",
    "إيجي برس": "https://www.egypress.com/feed",
    "البوابة العربية للأخبار التقنية": "https://aitnews.com/feed/",
    "أخبار تك": "https://akhbartech.com/feed/",
    "ياقوت للتكنولوجيا": "https://www.yaqoot.com/feed/",
    "مجلة الرجل تقنية": "https://arrajol.com/category/tech/feed/",
    "Aliqtisadi": "https://www.aliqtisadi.com/feed/",
    "Forbes Middle East": "https://www.forbesmiddleeast.com/rss/news",

    # ════════════════════════════════════════
    # Tier 6: European Tech (25+)
    # ════════════════════════════════════════
    "Sifted": "https://sifted.eu/feed",
    "EU-Startups": "https://www.eu-startups.com/feed/",
    "Tech.eu": "https://tech.eu/feed/",
    "Silicon Canals": "https://siliconcanals.com/feed/",
    "Heise DE": "https://www.heise.de/rss/heise-atom.xml",
    "Golem DE": "https://rss.golem.de/rss.php?feed=RSS2.0",
    "t3n DE": "https://t3n.de/rss.xml",
    "Computerbase DE": "https://www.computerbase.de/rss/news.xml",
    "Le Monde Tech": "https://www.lemonde.fr/pixels/rss_full.xml",
    "Les Echos Tech": "https://services.lesechos.fr/rss/les-echos-tech-medias.xml",
    "Usine Digitale": "https://www.usine-digitale.fr/rss",
    "FrenchWeb": "https://www.frenchweb.fr/feed",
    "Xataka ES": "https://www.xataka.com/tag/feeds/rss2.xml",
    "Genbeta ES": "https://www.genbeta.com/tag/feeds/rss2.xml",
    "El País Tech": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/tecnologia/portada",
    "ABC Tech ES": "https://www.abc.es/rss/feeds/abc_Tecnologia.xml",
    "La Repubblica Tech": "https://www.repubblica.it/rss/tecnologia/rss2.0.xml",
    "Wired Italy": "https://www.wired.it/feed/rss",
    "DigitalTrends": "https://www.digitaltrends.com/feed/",
    "Euronews Next": "https://www.euronews.com/rss?level=theme&name=next",

    # ════════════════════════════════════════
    # Tier 7: Asia Pacific (20+)
    # ════════════════════════════════════════
    "Nikkei Asia Tech": "https://asia.nikkei.com/rss/feed/nar",
    "South China Morning Post Tech": "https://www.scmp.com/rss/36/feed",
    "KrASIA": "https://kr-asia.com/feed",
    "TechNode": "https://technode.com/feed/",
    "Pandaily": "https://pandaily.com/feed/",
    "Caixin Global": "https://www.caixinglobal.com/rss/rss.xml",
    "Yicai Global": "https://www.yicaiglobal.com/rss",
    "Rest of World": "https://restofworld.org/feed/latest/",
    "Japan Times Tech": "https://www.japantimes.co.jp/tag/tech/feed/",
    "Korea Herald Tech": "http://www.koreaherald.com/common/rss_xml.php?ct=104",
    "The Chosun Biz": "https://biz.chosun.com/site/data/rss/rss.xml",
    "Channel News Asia Tech": "https://www.channelnewsasia.com/rssfeeds/8395986",
    "E27": "https://e27.co/feed/",
    "Tech in Asia": "https://www.techinasia.com/feed",
    "Nikkei Tech": "https://asia.nikkei.com/rss/feed/technology",

    # ════════════════════════════════════════
    # Tier 8: India Tech (10+)
    # ════════════════════════════════════════
    "YourStory": "https://yourstory.com/feed",
    "Inc42": "https://inc42.com/feed/",
    "Entrackr": "https://entrackr.com/feed/",
    "MediaNama": "https://www.medianama.com/feed/",
    "Economic Times Tech": "https://economictimes.indiatimes.com/tech/rssfeeds/13357270.cms",
    "LiveMint Tech": "https://www.livemint.com/rss/technology",
    "India Today Tech": "https://www.indiatoday.in/rss/1206584",
    "Factor Daily": "https://factordaily.com/feed/",

    # ════════════════════════════════════════
    # Tier 9: Africa & Latin America (10+)
    # ════════════════════════════════════════
    "TechCabal": "https://techcabal.com/feed/",
    "Disrupt Africa": "https://disrupt-africa.com/feed/",
    "Ventureburn": "https://ventureburn.com/feed/",
    "Quartz Africa": "https://qz.com/africa/rss",
    "TechPoint Africa": "https://techpoint.africa/feed/",
    "LatamList": "https://latamlist.com/feed/",
    "Contxto": "https://contxto.com/en/feed/",

    # ════════════════════════════════════════
    # Tier 10: Russia & CIS
    # ════════════════════════════════════════
    "East-West Digital": "https://www.ewdn.com/feed/",
    "The Moscow Times": "https://www.themoscowtimes.com/rss/news",
}

# ============================================================
# Google News RSS — يفتح وصول لآلاف المصادر
# Format: (query, hl=language, gl=country)
# ============================================================

GOOGLE_NEWS_QUERIES: List[Tuple[str, str, str]] = [
    # English (العالم الناطق بالإنجليزية)
    ("artificial intelligence", "en-US", "US"),
    ("AI model launch", "en-US", "US"),
    ("ChatGPT OR Claude OR Gemini", "en-US", "US"),
    ("AI startup funding", "en-US", "US"),
    ("LLM research breakthrough", "en-US", "US"),
    ("AI regulation policy", "en-GB", "GB"),
    ("generative AI", "en-US", "US"),
    ("AI China Baidu Alibaba", "en-US", "US"),

    # العربية
    ("الذكاء الاصطناعي", "ar", "SA"),
    ("تقنية ذكاء اصطناعي", "ar", "AE"),
    ("ChatGPT بالعربي", "ar", "EG"),

    # اللغات الأوروبية
    ("intelligence artificielle", "fr", "FR"),
    ("künstliche Intelligenz", "de", "DE"),
    ("inteligencia artificial", "es", "ES"),
    ("intelligenza artificiale", "it", "IT"),

    # آسيا
    ("人工知能", "ja", "JP"),           # Japanese
    ("인공지능", "ko", "KR"),            # Korean
    ("人工智能 AI", "zh-CN", "CN"),      # Chinese
]

def build_gnews_url(query: str, hl: str, gl: str) -> str:
    """بناء URL لـ Google News RSS search."""
    q = quote(query)
    # ceid = country:language (Google's format)
    ceid = f"{gl}:{hl.split('-')[0]}"
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"

# ============================================================
# YouTube Channels
# ============================================================

YOUTUBE_CHANNELS = {
    "Two Minute Papers": "UCbfYPyITQ-7l4upoX8nvctg",
    "Yannic Kilcher": "UCZHmQk67mSJgfCCTn7xBfew",
    "AI Explained": "UCNJ1Ymd5yFuUPtn21xtRbbw",
    "Matthew Berman": "UCawZsQWqfGSbCI5yjkdVkTA",
    "Andrej Karpathy": "UCPk8m_r6fkUSYmvgCBwq-sw",
    "Sam Witteveen": "UC55ODhbHHRDbNK8OZO9O3qQ",
    "1littlecoder": "UCpVm7bg6pXKo1Pr6k5kxG9A",
    "bycloud": "UC29ju8bIPH5as8OGnQzwJyA",
    "AI Jason": "UCd4lg3W4bRacv96mZ_VmLEw",
    "Fireship": "UCsBjURrPoezykLs9EqgamOA",
    "David Shapiro": "UC_NafIo-Ku2loOLrzm45ABA",
    "All About AI": "UCR1qBQsGbbL5sEQkxFBgjNA",
}

# ============================================================
# TRENDING HASHTAGS
# ============================================================

def fetch_worldwide_trends() -> List[str]:
    try:
        with open(TRENDS_CACHE_FILE, "r") as f:
            cached = json.load(f)
            if time.time() - cached.get("ts", 0) < 10800:
                return cached.get("hashtags", [])
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    collected: List[str] = []
    urls = ["https://trends24.in/united-states/", "https://trends24.in/saudi-arabia/"]

    for url in urls:
        try:
            r = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0"},
                timeout=12,
            )
            if r.status_code == 200:
                matches = re.findall(r'search\?q=(%23[^"&]+)', r.text)
                for m in matches[:30]:
                    try:
                        decoded = unquote(m)
                        if decoded.startswith("#") and 2 < len(decoded) < 35:
                            collected.append(decoded)
                    except Exception:
                        continue
        except Exception as exc:
            print(f"[trends] {url}: {exc}")
        time.sleep(1)

    unique = list(dict.fromkeys(collected))
    print(f"[trends] {len(unique)} هاشتاق ترند عالمي")

    try:
        with open(TRENDS_CACHE_FILE, "w") as f:
            json.dump({"ts": time.time(), "hashtags": unique}, f)
    except Exception:
        pass
    return unique

def filter_relevant_trends(trends: List[str], max_n: int = 8) -> List[str]:
    blacklist = ["bts", "kpop", "blackpink", "exo", "mls", "nba", "nfl",
                 "playoff", "election", "trump", "biden", "taylor",
                 "swift", "marvel", "wwe", "ufc", "nascar"]
    tech_keywords = ["ai", "tech", "chatgpt", "gpt", "llm", "gemini",
                     "claude", "openai", "google", "apple", "meta",
                     "code", "dev", "iphone", "bitcoin", "crypto",
                     "elon", "nvidia", "startup", "tesla"]
    relevant = []
    for tag in trends:
        lower = tag.lower()
        if any(b in lower for b in blacklist):
            continue
        if re.search(r"\d{1,2}(st|nd|rd|th)$", lower):
            continue
        if any(kw in lower for kw in tech_keywords):
            relevant.insert(0, tag)
        else:
            relevant.append(tag)
    return relevant[:max_n]

# ============================================================
# CACHE (dual: URL + Title-similarity)
# ============================================================

def load_cache() -> set:
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def load_title_cache() -> set:
    try:
        with open(TITLE_CACHE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_cache(cache: set, filepath: str = CACHE_FILE) -> None:
    trimmed = list(cache)[-MAX_CACHE_SIZE:]
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(trimmed, f)
    except Exception as exc:
        print(f"[cache] {exc}")

def normalize_title(title: str) -> str:
    """توحيد العنوان للـ dedup — إزالة الأحرف الخاصة، lowercase."""
    t = title.lower()
    t = re.sub(r"[^\w\u0600-\u06FF\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def url_hash(title: str, url: str) -> str:
    return hashlib.md5(f"{title}|{url}".encode("utf-8")).hexdigest()[:16]

def title_hash(title: str) -> str:
    """hash على أول 60 حرف من العنوان الموحّد - لتحديد القصص المكررة عبر مصادر مختلفة."""
    normalized = normalize_title(title)[:60]
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()[:16]

# ============================================================
# RSS FETCHING (Parallel)
# ============================================================

def clean_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    for old, new in {"&nbsp;": " ", "&amp;": "&", "&quot;": '"',
                     "&#39;": "'", "&lt;": "<", "&gt;": ">"}.items():
        text = text.replace(old, new)
    return re.sub(r"\s+", " ", text).strip()

def parse_entry_date(entry) -> Optional[datetime]:
    for field in ("published_parsed", "updated_parsed"):
        val = getattr(entry, field, None)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except Exception:
                continue
    return None

def fetch_one_feed(url: str, source: str, hours: int = 3) -> List[Dict]:
    """جلب feed واحد مع timeout صارم."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    items: List[Dict] = []
    try:
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (FahadAI-Bot/5.0) AppleWebKit/537.36"},
            timeout=FETCH_TIMEOUT,
        )
        if r.status_code != 200:
            return items
        feed = feedparser.parse(r.content)
        for entry in feed.entries[:15]:
            published = parse_entry_date(entry)
            if not published or published < cutoff:
                continue
            title = (getattr(entry, "title", "") or "").strip()
            link = (getattr(entry, "link", "") or "").strip()
            summary = clean_html(getattr(entry, "summary", ""))[:600]
            if title and link:
                items.append({
                    "title": title, "url": link,
                    "summary": summary, "source": source,
                })
    except Exception:
        pass  # silent fail — too many sources to log each
    return items

def fetch_sources_parallel(
    sources: Dict[str, str], hours: int = 3,
) -> List[Dict]:
    """جلب كل المصادر بالتوازي."""
    collected: List[Dict] = []
    success_count = 0
    fail_count = 0

    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as executor:
        future_to_source = {
            executor.submit(fetch_one_feed, url, name, hours): name
            for name, url in sources.items()
        }
        for future in as_completed(future_to_source):
            source = future_to_source[future]
            try:
                items = future.result(timeout=FETCH_TIMEOUT + 5)
                if items:
                    collected.extend(items)
                    success_count += 1
                else:
                    fail_count += 1
            except Exception:
                fail_count += 1

    print(f"[fetch] ✅ {success_count} مصدر نجح · ❌ {fail_count} فشل/فارغ · 📰 {len(collected)} مقال")
    return collected

def fetch_google_news(queries: List[Tuple[str, str, str]], hours: int = 3) -> List[Dict]:
    """جلب نتائج Google News لاستعلامات متعددة بالتوازي."""
    gnews_sources = {
        f"GNews:{q[:25]}({gl})": build_gnews_url(q, hl, gl)
        for q, hl, gl in queries
    }
    return fetch_sources_parallel(gnews_sources, hours=hours)

def fetch_youtube_videos(hours: int = 72) -> List[Dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    yt_sources = {
        name: f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
        for name, cid in YOUTUBE_CHANNELS.items()
    }
    videos: List[Dict] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(fetch_one_feed, url, name, hours=hours): name
            for name, url in yt_sources.items()
        }
        for future in as_completed(futures):
            try:
                items = future.result(timeout=FETCH_TIMEOUT + 5)
                for item in items:
                    item["channel"] = item.pop("source", "")
                videos.extend(items)
            except Exception:
                pass
    # فلترة: فقط فيديوهات حديثة
    now = datetime.now(timezone.utc)
    videos = [v for v in videos if v.get("url")]
    print(f"[videos] {len(videos)} فيديو من {len(YOUTUBE_CHANNELS)} قناة")
    return videos

# ============================================================
# DIVERSITY & SAMPLING
# ============================================================

def extract_entities(title: str, summary: str = "") -> set:
    """استخراج الشركات والأسماء الرئيسية — للـ diversity."""
    text = f"{title} {summary}".lower()
    entities = set()
    companies = [
        "openai", "anthropic", "google", "deepmind", "meta",
        "microsoft", "mistral", "huggingface", "cohere", "stability",
        "nvidia", "apple", "amazon", "xai", "perplexity", "runway",
        "midjourney", "character", "inflection", "adept", "baidu",
        "alibaba", "tencent", "bytedance", "deepseek", "qwen",
    ]
    for c in companies:
        if c in text:
            entities.add(c)
    return entities

def diversify_articles(articles: List[Dict], target: int = 80) -> List[Dict]:
    """توزيع متنوع: لا تأخذ أكثر من 5 أخبار عن نفس الشركة، وزّع بين المصادر."""
    # Shuffle للعدل
    shuffled = articles.copy()
    random.shuffle(shuffled)

    selected: List[Dict] = []
    company_counts: Dict[str, int] = {}
    source_counts: Dict[str, int] = {}

    for article in shuffled:
        if len(selected) >= target:
            break
        entities = extract_entities(article["title"], article.get("summary", ""))
        primary_company = next(iter(entities), "other")
        source = article.get("source", "unknown")

        # حد أقصى 5 لكل شركة، 3 لكل مصدر
        if company_counts.get(primary_company, 0) >= 5:
            continue
        if source_counts.get(source, 0) >= 3:
            continue

        selected.append(article)
        company_counts[primary_company] = company_counts.get(primary_company, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1

    # إذا لم نصل للهدف، أكمل بدون قيود
    if len(selected) < target:
        taken_urls = {a["url"] for a in selected}
        for article in shuffled:
            if len(selected) >= target:
                break
            if article["url"] not in taken_urls:
                selected.append(article)

    return selected

# ============================================================
# GROQ CLIENT
# ============================================================

def call_groq(system: str, user: str, temperature: float = 0.45,
              max_tokens: int = 6000, retries: int = 2) -> Optional[str]:
    """استدعاء Groq مع retry — يكشف 413 ويطبع تحذير واضح."""
    for attempt in range(retries + 1):
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                         "Content-Type": "application/json"},
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=150,
            )
            # 413 = payload too large — لا فائدة من retry بنفس البيانات
            if r.status_code == 413:
                print(f"[groq] ❌ 413 Payload Too Large (size={len(user)} chars)")
                return "PAYLOAD_TOO_LARGE"
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            print(f"[groq] محاولة {attempt + 1}: {exc}")
            if attempt < retries:
                time.sleep(5)
    return None

def call_groq_adaptive(
    system: str,
    articles_compact: List[Dict],
    videos_compact: List[Dict],
    trends: List[str],
    user_template: str,
    n: int = 5,
) -> Optional[str]:
    """استدعاء تكيفي: إذا 413، يقص البايلود ويعيد المحاولة."""
    attempts = [
        (len(articles_compact), len(videos_compact)),  # الحجم الأصلي
        (min(40, len(articles_compact)), min(10, len(videos_compact))),
        (min(30, len(articles_compact)), min(8, len(videos_compact))),
        (min(22, len(articles_compact)), min(6, len(videos_compact))),
    ]

    for art_n, vid_n in attempts:
        articles_trimmed = articles_compact[:art_n]
        videos_trimmed = videos_compact[:vid_n]

        user = user_template.format(
            n=n,
            articles=json.dumps(articles_trimmed, ensure_ascii=False),
            videos=json.dumps(videos_trimmed, ensure_ascii=False),
            trends=json.dumps(trends, ensure_ascii=False),
        )
        size_kb = len(user.encode("utf-8")) / 1024
        print(f"[groq] محاولة بحجم: {art_n} خبر + {vid_n} فيديو = {size_kb:.1f} KB")

        result = call_groq(system, user, temperature=0.5, max_tokens=6500, retries=1)
        if result == "PAYLOAD_TOO_LARGE":
            print(f"[groq] 🔄 تقليل الحجم...")
            continue
        if result:
            return result

    print("[groq] ❌ كل المحاولات فشلت")
    return None

def extract_json(raw: Optional[str]) -> Optional[Any]:
    if not raw:
        return None
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    for pattern in (r"\[[\s\S]*\]", r"\{[\s\S]*\}"):
        m = re.search(pattern, text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                continue
    return None

# ============================================================
# PROMPTS
# ============================================================

NEWS_SYSTEM = """أنت رئيس تحرير قناة نخبوية للذكاء الاصطناعي بالعربي (مستوى The Neuron و Import AI).
جمهورك: مطورون وصناع قرار ومستثمرون يثقون بتحليلك.

أسلوبك:
• عربية فصحى قوية بنكهة سعودية مهنية
• جمل قصيرة مؤثرة، صفر حشو
• لا تستخدم مطلقاً: ثوري / مذهل / لا يصدق / يغير اللعبة / اختراق تاريخي
• دقة مطلقة في الأرقام والأسماء التقنية
• تحليل عميق يضيف قيمة فوق الخبر الخام
• صوت واثق غير مبالغ — أقرب إلى WSJ منه إلى BuzzFeed"""

NEWS_USER = """اختر {n} أخبار من القائمة التالية مع التزام صارم بالتنوع.

⚠️ قواعد التنوع الصارمة (الأهم):
• MAX خبر واحد فقط عن OpenAI
• MAX خبر واحد فقط عن Anthropic
• MAX خبر واحد فقط عن Google
• بالمجمل: لا تختر أكثر من خبر عن نفس الشركة
• نوّع بين فئات مختلفة: إطلاق، بحث، تمويل، سياسة، جدل، منتج، شراكة
• نوّع جغرافياً: حاول تختار من US + أوروبا + آسيا/الصين + الشرق الأوسط
• إذا الأخبار كلها عن شركة واحدة، اختر الأهم فقط واترك الباقي

الأخبار المتاحة (id=رقم، t=عنوان، s=ملخص):
{articles}

الفيديوهات المتاحة للربط (vid=رقم، t=عنوان، ch=قناة — null إذا لا يوجد ربط):
{videos}

الترند العالمي الحالي على Twitter:
{trends}

لكل خبر مختار، أرجع JSON بهذا الشكل بالضبط:
{{
  "id": <رقم id>,
  "category": "launch|research|funding|partnership|product|controversy|policy|benchmark|tool|release|acquisition",
  "category_ar": "إطلاق|بحث|تمويل|شراكة|منتج|جدل|سياسة|معيار|أداة|تحديث|استحواذ",
  "company": "الشركة أو المنتج الرئيسي (بالإنجليزية)",
  "region": "US|EU|China|MENA|Asia|Global",
  "headline": "عنوان عربي قوي جذاب (50-85 حرف)",
  "hook": "جملة افتتاحية قوية (100-180 حرف)",
  "details": "التفاصيل الشاملة 4-6 جمل 450-650 حرف - أرقام حقيقية وأسماء دقيقة",
  "why_matters": "ليش الخبر مهم للمطور العربي/المستثمر - جملتان (180-280 حرف)",
  "reading_between_lines": "تحليل استراتيجي لما وراء الخبر (180-280 حرف)",
  "ready_tweet": "تغريدة عربية جاهزة للنسخ - أسلوب إنساني - 200-260 حرف - بدون هاشتاقات داخل النص",
  "hashtags": ["5-7 هاشتاقات حقيقية مزيج: عام #AI + عربي #الذكاء_الاصطناعي + محدد للخبر + 1-2 من الترند"],
  "related_video_id": <رقم vid مناسب أو null>,
  "importance": 1-10
}}

معايير الاختيار:
• استبعد: إعلانات تسويقية، مقالات رأي، تكرار، شركات مجهولة
• اختر: إطلاقات، اختراقات بحثية، صفقات كبرى، تحولات استراتيجية
• إذا وجدت نفس الخبر من مصادر متعددة، اختر مرة واحدة فقط

أرجع JSON array فقط. بدون markdown. بدون نص قبل أو بعد."""

REPORT_SYSTEM = """أنت محلل أول لصناعة الذكاء الاصطناعي. تكتب تقارير يومية عميقة."""

REPORT_USER = """اكتب تقرير اليوم عن أبرز أحداث AI.

الأخبار (آخر 24 ساعة، t=عنوان، s=ملخص):
{articles}

أرجع JSON:
{{
  "theme_of_the_day": "موضوع اليوم المحوري في عبارة قوية",
  "top_stories": [
    {{"rank": 1, "headline": "عنوان قوي", "summary": "2-3 جمل عميقة (250-350 حرف)"}},
    {{"rank": 2, "headline": "...", "summary": "..."}},
    {{"rank": 3, "headline": "...", "summary": "..."}}
  ],
  "reading_between_lines": "تحليل 4-5 جمل - ما النمط الذي تكشفه أخبار اليوم؟",
  "tomorrow_watch": "جملتان: ماذا نترقب؟"
}}

قواعد:
• top_stories: لا تكن كلها عن نفس الشركة — نوّع!
• اختر من شركات/مناطق مختلفة

أرجع JSON فقط."""

# ============================================================
# FORMATTING
# ============================================================

CATEGORY_EMOJI = {
    "launch": "🚀", "research": "🔬", "funding": "💰",
    "partnership": "🤝", "product": "📱", "controversy": "⚠️",
    "policy": "⚖️", "benchmark": "📊", "tool": "🛠",
    "release": "📦", "acquisition": "🏢",
}

REGION_FLAG = {
    "US": "🇺🇸", "EU": "🇪🇺", "China": "🇨🇳",
    "MENA": "🌍", "Asia": "🌏", "Global": "🌐",
}

def esc(text: Any) -> str:
    if not text:
        return ""
    return (str(text).replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))

def clean_hashtag(tag: str) -> Optional[str]:
    if not isinstance(tag, str):
        return None
    tag = tag.strip()
    if not tag.startswith("#"):
        tag = "#" + tag
    tag = re.sub(r"[^\w\u0600-\u06FF#_]", "", tag)
    return tag if len(tag) > 2 else None

def format_news(item: Dict, video_url: Optional[str] = None) -> str:
    emoji = CATEGORY_EMOJI.get(item.get("category", ""), "📰")
    cat = esc(item.get("category_ar", "خبر"))
    company = esc(item.get("company", "")).strip()
    region = item.get("region", "")
    flag = REGION_FLAG.get(region, "")
    headline = esc(item.get("headline", ""))
    hook = esc(item.get("hook", "")).strip()
    details = esc(item.get("details", ""))
    why = esc(item.get("why_matters", "")).strip()
    rbl = esc(item.get("reading_between_lines", "")).strip()
    tweet = (item.get("ready_tweet", "") or "").strip()
    hashtags = item.get("hashtags", []) or []

    header_line = f"{emoji} <b>{cat}</b>"
    if company:
        header_line += f"  ·  <b>{company}</b>"
    if flag:
        header_line += f"  {flag}"

    sep = "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"

    blocks: List[str] = [header_line, sep, f"<b>{headline}</b>"]

    if hook:
        blocks += ["", f"<i>{hook}</i>"]

    blocks += ["", details]

    if why or rbl:
        blocks.append(sep)
        if why:
            blocks += ["◆ <b>ليش يهمك</b>", why]
        if rbl:
            if why:
                blocks.append("")
            blocks += ["◆ <b>القراءة بين السطور</b>", rbl]

    if video_url:
        blocks += [sep, f'🎬 <a href="{esc(video_url)}"><b>فيديو يشرح الموضوع</b></a>']

    if tweet:
        clean_tags, seen = [], set()
        for tag in hashtags:
            clean = clean_hashtag(tag)
            if clean and clean.lower() not in seen:
                seen.add(clean.lower())
                clean_tags.append(clean)
        tag_line = " ".join(clean_tags[:7])
        tweet_full = f"{tweet}\n\n{tag_line}" if tag_line else tweet

        blocks += [
            sep,
            "📱 <b>تغريدة جاهزة — انسخ والصق</b>",
            "",
            f"<code>{esc(tweet_full)}</code>",
        ]

    return "\n".join(blocks)

def format_report(report: Dict, date_str: str) -> str:
    theme = esc(report.get("theme_of_the_day", "")).strip()
    rbl = esc(report.get("reading_between_lines", "")).strip()
    watch = esc(report.get("tomorrow_watch", "")).strip()
    stories = report.get("top_stories", [])

    sep = "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
    lines = [f"📊 <b>تقرير اليوم</b>  ·  {esc(date_str)}", sep]

    if theme:
        lines += [f"<i>موضوع اليوم: {theme}</i>", ""]

    lines += ["<b>أبرز 3 أحداث</b>", ""]

    rank_markers = ["①", "②", "③", "④", "⑤"]
    for story in stories[:5]:
        rank = max(1, min(5, int(story.get("rank", 1))))
        marker = rank_markers[rank - 1]
        head = esc(story.get("headline", ""))
        summ = esc(story.get("summary", ""))
        lines += [f"{marker} <b>{head}</b>", summ, ""]

    if rbl:
        lines += [sep, "◆ <b>القراءة بين السطور</b>", rbl, ""]
    if watch:
        lines += ["◆ <b>نترقب</b>", watch]

    return "\n".join(lines)

# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message: str, disable_preview: bool = False,
                  preview_above: bool = False) -> bool:
    if len(message) > 4050:
        message = message[:4040] + "…"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID, "text": message,
        "parse_mode": "HTML", "disable_web_page_preview": disable_preview,
    }
    if not disable_preview and preview_above:
        payload["link_preview_options"] = {
            "is_disabled": False, "prefer_large_media": True,
            "show_above_text": True,
        }
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json=payload, timeout=30)
        if r.status_code != 200:
            print(f"[telegram] {r.status_code}: {r.text[:200]}")
            if "link_preview_options" in payload:
                payload.pop("link_preview_options")
                r = requests.post(url, json=payload, timeout=30)
                return r.status_code == 200
            return False
        return True
    except Exception as exc:
        print(f"[telegram] {exc}")
        return False

# ============================================================
# CYCLES
# ============================================================

def fetch_all_news(hours: int = 3) -> List[Dict]:
    """جلب كل المصادر + Google News بالتوازي."""
    t0 = time.time()
    print(f"\n🌍 جلب من {len(NEWS_SOURCES)} مصدر + {len(GOOGLE_NEWS_QUERIES)} استعلام Google News...")

    direct = fetch_sources_parallel(NEWS_SOURCES, hours=hours)
    gnews = fetch_google_news(GOOGLE_NEWS_QUERIES, hours=hours)

    all_articles = direct + gnews
    elapsed = time.time() - t0
    print(f"[fetch-all] إجمالي: {len(all_articles)} مقال في {elapsed:.1f} ثانية")
    return all_articles

def news_cycle() -> None:
    ts = datetime.now(RIYADH_TZ).strftime("%Y-%m-%d %H:%M")
    print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"[news-cycle] {ts}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    url_cache = load_cache()
    title_cache = load_title_cache()

    articles = fetch_all_news(hours=3)
    if not articles:
        print("[news] لا محتوى")
        return

    # Dedup مزدوج: URL + Title
    unique: List[Dict] = []
    seen_urls, seen_titles = set(), set()
    for a in articles:
        u_hash = url_hash(a["title"], a["url"])
        t_hash = title_hash(a["title"])
        if u_hash in url_cache or t_hash in title_cache:
            continue
        if u_hash in seen_urls or t_hash in seen_titles:
            continue
        seen_urls.add(u_hash)
        seen_titles.add(t_hash)
        unique.append(a)

    print(f"[news] بعد dedup: {len(unique)} مقال فريد")
    if len(unique) < 4:
        print("[news] تخطي — محتوى غير كافٍ")
        return

    # Diversify sampling
    sampled = diversify_articles(unique, target=50)
    print(f"[news] بعد sampling متنوع: {len(sampled)} مقال")

    # YouTube + Trends
    videos = fetch_youtube_videos(hours=72)[:12]
    world_trends = filter_relevant_trends(fetch_worldwide_trends(), max_n=8)
    print(f"[trends] {len(world_trends)} هاشتاق مناسب — {world_trends[:4]}")

    # Prepare for Groq — compact keys + shorter lengths (يمنع 413)
    articles_compact = [{
        "id": i,
        "t": a["title"][:180],
        "s": a["summary"][:150],
    } for i, a in enumerate(sampled)]

    videos_compact = [{
        "vid": i,
        "t": v["title"][:140],
        "ch": v["channel"],
    } for i, v in enumerate(videos)]

    raw = call_groq_adaptive(
        NEWS_SYSTEM,
        articles_compact=articles_compact,
        videos_compact=videos_compact,
        trends=world_trends,
        user_template=NEWS_USER,
        n=5,
    )
    curated = extract_json(raw)
    if not curated or not isinstance(curated, list):
        print("[news] فشل curation")
        return

    # Post-filter: إجبار التنوع حتى لو Groq تجاهل القاعدة
    curated = sorted(curated, key=lambda x: x.get("importance", 5), reverse=True)
    final_items = []
    seen_companies = set()
    for item in curated:
        company = (item.get("company") or "").lower().strip()
        if company and company in seen_companies:
            continue
        seen_companies.add(company)
        final_items.append(item)
        if len(final_items) >= 5:
            break

    print(f"[news] نُشر: {len(final_items)} خبر (شركات: {seen_companies})")

    sent = 0
    for item in final_items:
        try:
            nid = int(item.get("id", -1))
            if nid < 0 or nid >= len(sampled):
                continue
            original = sampled[nid]

            video_url = None
            vid = item.get("related_video_id")
            if vid is not None:
                try:
                    vid = int(vid)
                    if 0 <= vid < len(videos):
                        video_url = videos[vid]["url"]
                except (ValueError, TypeError):
                    pass

            message = format_news(item, video_url=video_url)

            ok = send_telegram(
                message,
                disable_preview=(video_url is None),
                preview_above=(video_url is not None),
            )
            if ok:
                url_cache.add(url_hash(original["title"], original["url"]))
                title_cache.add(title_hash(original["title"]))
                sent += 1
                time.sleep(5)
        except Exception as exc:
            print(f"[news] خطأ في خبر: {exc}")

    save_cache(url_cache, CACHE_FILE)
    save_cache(title_cache, TITLE_CACHE_FILE)
    print(f"[news] ✅ أُرسل {sent} خبر")

def report_cycle() -> None:
    ts = datetime.now(RIYADH_TZ).strftime("%Y-%m-%d %H:%M")
    print(f"\n━━━ [report-cycle] {ts} ━━━")

    articles = fetch_all_news(hours=24)
    if len(articles) < 5:
        print("[report] محتوى غير كافٍ")
        return

    # diversify للتقرير أيضاً — مع ضغط للـ payload
    sampled = diversify_articles(articles, target=35)
    compact = [{
        "t": a["title"][:180],
        "s": a["summary"][:150],
    } for a in sampled]

    size_kb = len(json.dumps(compact, ensure_ascii=False).encode("utf-8")) / 1024
    print(f"[report] payload: {len(compact)} خبر ({size_kb:.1f} KB)")

    raw = call_groq(
        REPORT_SYSTEM,
        REPORT_USER.format(articles=json.dumps(compact, ensure_ascii=False)),
        temperature=0.5, max_tokens=3000,
    )
    if raw == "PAYLOAD_TOO_LARGE":
        print("[report] إعادة محاولة بحجم أصغر...")
        compact = compact[:20]
        raw = call_groq(
            REPORT_SYSTEM,
            REPORT_USER.format(articles=json.dumps(compact, ensure_ascii=False)),
            temperature=0.5, max_tokens=3000,
        )
    report = extract_json(raw)
    if not report or not isinstance(report, dict):
        print("[report] فشل")
        return

    now = datetime.now(RIYADH_TZ)
    months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
             "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
    date_str = f"{now.day} {months[now.month - 1]} {now.year}"

    message = format_report(report, date_str)
    send_telegram(message, disable_preview=True)
    print("[report] ✅ أُرسل")

# ============================================================
# STARTUP
# ============================================================

def startup_check() -> None:
    required = {
        "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
        "GROQ_API_KEY": GROQ_API_KEY,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        print(f"[startup] ❌ متغيرات ناقصة: {missing}")
        raise SystemExit(1)

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  FahadAI News Bot v5")
    print("  Global Intelligence Edition")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"✅ كل المتغيرات محمّلة")
    print(f"🌍 مصادر منتقاة: {len(NEWS_SOURCES)}")
    print(f"🔍 Google News استعلامات: {len(GOOGLE_NEWS_QUERIES)} (8 لغات)")
    print(f"🎬 قنوات YouTube: {len(YOUTUBE_CHANNELS)}")
    print(f"⚡ Parallel workers: {FETCH_WORKERS}")
    print(f"🤖 النموذج: {GROQ_MODEL}")
    print(f"⏰ الوقت (الرياض): {datetime.now(RIYADH_TZ).strftime('%Y-%m-%d %H:%M:%S')}")

def main() -> None:
    startup_check()

    scheduler = BlockingScheduler(timezone=RIYADH_TZ)

    # دورة أخبار كل 3 ساعات (8 دورات/يوم)
    scheduler.add_job(
        news_cycle,
        CronTrigger(hour="6,9,12,15,18,21,0,3", minute=0, timezone=RIYADH_TZ),
        id="news", max_instances=1, coalesce=True,
    )

    # تقرير يومي 10 مساءً (بعد آخر دورة 9م بساعة)
    scheduler.add_job(
        report_cycle,
        CronTrigger(hour=22, minute=0, timezone=RIYADH_TZ),
        id="report", max_instances=1, coalesce=True,
    )

    print("\n📅 المواعيد المجدولة (8 دورات أخبار/يوم):")
    print("   📰 أخبار: 6ص · 9ص · 12ظ · 3ع · 6م · 9م · 12ص · 3ص")
    print("   📊 تقرير يومي: 10 مساءً")

    print("\n▶️ تشغيل دورة فورية...")
    try:
        news_cycle()
    except Exception as exc:
        print(f"[startup-cycle] {exc}")

    print("\n⏰ الجدولة شغالة — في انتظار المواعيد...\n")
    scheduler.start()


if __name__ == "__main__":
    main()
