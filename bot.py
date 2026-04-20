"""
AI News Bot v6 — Newsroom Edition
قناة @fahadai · Telegram

الفلسفة: قناة إخبارية بمعايير العربية الإخبارية للذكاء الاصطناعي.

التطورات الرئيسية عن v5:
  🖼️  استخراج og:image من كل مقال — القناة حية بصرياً
  🎬 YouTube thumbnails كـ fallback ذكي
  🏷️ قاعدة هاشتاقات عالمية مدروسة (نمو حقيقي لتويتر)
  📝 أسلوب "العربية الإخبارية" — صياغة صحفية محترفة
  ⏰ 4 دورات/يوم بأوقات قصوى التفاعل
  🌍 200+ مصدر + Google News بـ 8 لغات (من v5)

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
from urllib.parse import quote, unquote, urlparse

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
# Qwen3-32b: أفضل نموذج للعربية على Groq (من Alibaba، حل محل qwen-qwq-32b)
# بديل احتياطي: "openai/gpt-oss-120b" أو "llama-3.3-70b-versatile"
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3-32b").strip()
GROQ_FALLBACK_MODEL = "llama-3.3-70b-versatile"

CACHE_FILE = "/tmp/fahadai_posted.json"
TITLE_CACHE_FILE = "/tmp/fahadai_titles.json"
TRENDS_CACHE_FILE = "/tmp/fahadai_trends.json"
MAX_CACHE_SIZE = 3000

FETCH_TIMEOUT = 10
FETCH_WORKERS = 18
IMAGE_TIMEOUT = 7

# ============================================================
# SOURCES — 130+ مصدر منتقى
# ============================================================

NEWS_SOURCES: Dict[str, str] = {
    # Tier 1: AI Companies
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

    # Tier 2: Global Tech Media
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

    # Tier 3: AI-Focused
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

    # Tier 4: Research
    "ArXiv AI": "http://export.arxiv.org/rss/cs.AI",
    "ArXiv ML": "http://export.arxiv.org/rss/cs.LG",
    "ArXiv NLP": "http://export.arxiv.org/rss/cs.CL",
    "ArXiv CV": "http://export.arxiv.org/rss/cs.CV",
    "ArXiv Neural": "http://export.arxiv.org/rss/cs.NE",
    "Papers With Code": "https://paperswithcode.com/latest/rss/",

    # Tier 5: Arabic
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
    "البوابة العربية للأخبار التقنية": "https://aitnews.com/feed/",
    "أخبار تك": "https://akhbartech.com/feed/",
    "Aliqtisadi": "https://www.aliqtisadi.com/feed/",
    "Forbes Middle East": "https://www.forbesmiddleeast.com/rss/news",

    # Tier 6: Europe
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
    "Wired Italy": "https://www.wired.it/feed/rss",
    "DigitalTrends": "https://www.digitaltrends.com/feed/",
    "Euronews Next": "https://www.euronews.com/rss?level=theme&name=next",

    # Tier 7: Asia Pacific
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
    "E27": "https://e27.co/feed/",
    "Tech in Asia": "https://www.techinasia.com/feed",
    "Nikkei Tech": "https://asia.nikkei.com/rss/feed/technology",

    # Tier 8: India
    "YourStory": "https://yourstory.com/feed",
    "Inc42": "https://inc42.com/feed/",
    "Entrackr": "https://entrackr.com/feed/",
    "MediaNama": "https://www.medianama.com/feed/",
    "Economic Times Tech": "https://economictimes.indiatimes.com/tech/rssfeeds/13357270.cms",
    "LiveMint Tech": "https://www.livemint.com/rss/technology",
    "India Today Tech": "https://www.indiatoday.in/rss/1206584",

    # Tier 9: Africa & LatAm
    "TechCabal": "https://techcabal.com/feed/",
    "Disrupt Africa": "https://disrupt-africa.com/feed/",
    "Ventureburn": "https://ventureburn.com/feed/",
    "Quartz Africa": "https://qz.com/africa/rss",
    "TechPoint Africa": "https://techpoint.africa/feed/",
    "Contxto": "https://contxto.com/en/feed/",
}

GOOGLE_NEWS_QUERIES: List[Tuple[str, str, str]] = [
    ("artificial intelligence", "en-US", "US"),
    ("AI model launch", "en-US", "US"),
    ("ChatGPT OR Claude OR Gemini", "en-US", "US"),
    ("AI startup funding", "en-US", "US"),
    ("LLM research breakthrough", "en-US", "US"),
    ("AI regulation policy", "en-GB", "GB"),
    ("generative AI", "en-US", "US"),
    ("AI China Baidu Alibaba", "en-US", "US"),
    ("الذكاء الاصطناعي", "ar", "SA"),
    ("تقنية ذكاء اصطناعي", "ar", "AE"),
    ("ChatGPT بالعربي", "ar", "EG"),
    ("intelligence artificielle", "fr", "FR"),
    ("künstliche Intelligenz", "de", "DE"),
    ("inteligencia artificial", "es", "ES"),
    ("intelligenza artificiale", "it", "IT"),
    ("人工知能", "ja", "JP"),
    ("인공지능", "ko", "KR"),
    ("人工智能 AI", "zh-CN", "CN"),
]

def build_gnews_url(query: str, hl: str, gl: str) -> str:
    q = quote(query)
    ceid = f"{gl}:{hl.split('-')[0]}"
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"

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
    "All About AI": "UCR1qBQsGbbL5sEQkxFBgjNA",
}

# ============================================================
# HASHTAG DATABASE — مدروسة للنمو على تويتر
# ============================================================

HASHTAG_DATABASE = {
    "universal_big": [
        "#AI", "#ArtificialIntelligence", "#ChatGPT", "#Tech",
        "#TechNews", "#Innovation", "#Technology",
    ],
    "ai_niche": [
        "#MachineLearning", "#DeepLearning", "#GenAI", "#GenerativeAI",
        "#LLM", "#AIAgents", "#NeuralNetworks", "#AIResearch",
        "#OpenSourceAI", "#MultimodalAI", "#AGI", "#AISafety",
        "#FutureOfAI", "#AITools", "#AIRevolution", "#MLOps",
    ],
    "company_hashtags": {
        "openai": ["#OpenAI", "#ChatGPT", "#GPT5", "#Sora"],
        "anthropic": ["#Anthropic", "#Claude", "#ClaudeAI"],
        "google": ["#GoogleAI", "#Gemini", "#DeepMind"],
        "meta": ["#MetaAI", "#Llama", "#Meta"],
        "microsoft": ["#Microsoft", "#Copilot", "#AzureAI"],
        "mistral": ["#MistralAI", "#Mistral"],
        "nvidia": ["#NVIDIA", "#CUDA"],
        "apple": ["#AppleIntelligence", "#Apple"],
        "xai": ["#xAI", "#Grok"],
        "huggingface": ["#HuggingFace", "#OpenSource"],
        "deepseek": ["#DeepSeek", "#OpenSourceAI"],
        "qwen": ["#Qwen", "#AlibabaAI"],
    },
    "arabic_big": [
        "#الذكاء_الاصطناعي", "#ذكاء_اصطناعي", "#تقنية", "#تكنولوجيا",
    ],
    "arabic_niche": [
        "#برمجة", "#ابتكار", "#ستارتب", "#ريادة_الأعمال",
        "#تحول_رقمي", "#رؤية_2030", "#تقنيات",
    ],
    "category_specific": {
        "funding": ["#Funding", "#Startup", "#VC", "#Investment"],
        "research": ["#AIResearch", "#MLResearch", "#arXiv"],
        "policy": ["#AIPolicy", "#AIRegulation", "#AIEthics"],
        "launch": ["#Launch", "#ProductLaunch", "#NewAI"],
        "controversy": ["#AIEthics", "#AISafety"],
        "partnership": ["#Partnership", "#Tech"],
    }
}

# ============================================================
# TRENDING HASHTAGS (Twitter)
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
                                       "AppleWebKit/537.36 Chrome/120.0"},
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

def filter_relevant_trends(trends: List[str], max_n: int = 6) -> List[str]:
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
# CACHE
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
    t = title.lower()
    t = re.sub(r"[^\w\u0600-\u06FF\s]", "", t)
    return re.sub(r"\s+", " ", t).strip()

def url_hash(title: str, url: str) -> str:
    return hashlib.md5(f"{title}|{url}".encode("utf-8")).hexdigest()[:16]

def title_hash(title: str) -> str:
    normalized = normalize_title(title)[:60]
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()[:16]

# ============================================================
# IMAGE EXTRACTION — og:image
# ============================================================

def resolve_redirect_url(url: str, timeout: int = 6) -> str:
    """متابعة redirect للحصول على URL النهائي (مهم لـ Google News)."""
    if not url or not url.startswith("http"):
        return url
    # إذا ما كانت Google News، أرجع كما هي
    if "news.google.com" not in url:
        return url
    try:
        r = requests.head(
            url,
            allow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                   "AppleWebKit/537.36 Chrome/120.0"},
        )
        final = r.url
        if final and final != url and "news.google.com" not in final:
            return final
    except Exception:
        pass
    # محاولة ثانية بـ GET إذا HEAD فشل
    try:
        r = requests.get(
            url,
            allow_redirects=True,
            timeout=timeout,
            stream=True,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                   "AppleWebKit/537.36 Chrome/120.0"},
        )
        final = r.url
        r.close()
        if final and final != url:
            return final
    except Exception:
        pass
    return url

def fetch_og_image(url: str, timeout: int = IMAGE_TIMEOUT) -> Optional[str]:
    """استخراج og:image من صفحة المقال."""
    if not url or not url.startswith("http"):
        return None
    try:
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 Chrome/120.0",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
            },
            timeout=timeout,
            allow_redirects=True,
            stream=True,
        )
        if r.status_code != 200:
            return None

        # اقرأ أول 80KB فقط — og:image دائماً في <head>
        content = b""
        for chunk in r.iter_content(chunk_size=8192):
            content += chunk
            if len(content) > 80000:
                break
        r.close()

        try:
            html = content.decode("utf-8", errors="ignore")
        except Exception:
            return None

        # أنماط استخراج متعددة
        patterns = [
            r'<meta[^>]*property=["\']og:image:secure_url["\'][^>]*content=["\']([^"\']+)["\']',
            r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']og:image:secure_url["\']',
            r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']',
            r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\']',
            r'<meta[^>]*name=["\']twitter:image["\'][^>]*content=["\']([^"\']+)["\']',
            r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*name=["\']twitter:image["\']',
            r'<meta[^>]*name=["\']twitter:image:src["\'][^>]*content=["\']([^"\']+)["\']',
        ]

        for pattern in patterns:
            m = re.search(pattern, html, re.IGNORECASE)
            if m:
                img_url = m.group(1).strip()
                # تنظيف HTML entities
                img_url = img_url.replace("&amp;", "&")
                if (img_url.startswith(("http://", "https://"))
                        and len(img_url) < 500
                        and not img_url.endswith(".svg")):
                    return img_url

        return None
    except Exception:
        return None

def fetch_images_parallel(items: List[Dict]) -> Dict[int, Optional[str]]:
    """جلب og:images لكل المقالات المختارة بالتوازي."""
    results: Dict[int, Optional[str]] = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_idx = {
            executor.submit(fetch_og_image, item["url"]): idx
            for idx, item in enumerate(items)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result(timeout=IMAGE_TIMEOUT + 3)
            except Exception:
                results[idx] = None
    success = sum(1 for v in results.values() if v)
    print(f"[images] استخرجت {success}/{len(items)} صورة og:image")
    return results

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

def fetch_one_feed(url: str, source: str, hours: int = 6) -> List[Dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    items: List[Dict] = []
    try:
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (FahadAI-Bot/6.0)"},
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
                items.append({"title": title, "url": link,
                              "summary": summary, "source": source})
    except Exception:
        pass
    return items

def fetch_sources_parallel(sources: Dict[str, str], hours: int = 6) -> List[Dict]:
    collected: List[Dict] = []
    success = fail = 0
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as executor:
        future_to_source = {
            executor.submit(fetch_one_feed, url, name, hours): name
            for name, url in sources.items()
        }
        for future in as_completed(future_to_source):
            try:
                items = future.result(timeout=FETCH_TIMEOUT + 5)
                if items:
                    collected.extend(items)
                    success += 1
                else:
                    fail += 1
            except Exception:
                fail += 1
    print(f"[fetch] ✅ {success} مصدر · ❌ {fail} فارغ · 📰 {len(collected)} مقال")
    return collected

def fetch_google_news(queries: List[Tuple[str, str, str]], hours: int = 6) -> List[Dict]:
    gnews_sources = {
        f"GNews({gl}):{q[:20]}": build_gnews_url(q, hl, gl)
        for q, hl, gl in queries
    }
    return fetch_sources_parallel(gnews_sources, hours=hours)

def fetch_youtube_videos(hours: int = 72) -> List[Dict]:
    yt_sources = {
        name: f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
        for name, cid in YOUTUBE_CHANNELS.items()
    }
    videos: List[Dict] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(fetch_one_feed, url, name, hours): name
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
    print(f"[videos] {len(videos)} فيديو من {len(YOUTUBE_CHANNELS)} قناة")
    return videos

# ============================================================
# DIVERSITY
# ============================================================

def extract_entities(title: str, summary: str = "") -> set:
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

def diversify_articles(articles: List[Dict], target: int = 50) -> List[Dict]:
    shuffled = articles.copy()
    random.shuffle(shuffled)
    selected: List[Dict] = []
    company_counts: Dict[str, int] = {}
    source_counts: Dict[str, int] = {}

    for article in shuffled:
        if len(selected) >= target:
            break
        entities = extract_entities(article["title"], article.get("summary", ""))
        primary = next(iter(entities), "other")
        source = article.get("source", "unknown")
        if company_counts.get(primary, 0) >= 5:
            continue
        if source_counts.get(source, 0) >= 3:
            continue
        selected.append(article)
        company_counts[primary] = company_counts.get(primary, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1

    if len(selected) < target:
        taken = {a["url"] for a in selected}
        for article in shuffled:
            if len(selected) >= target:
                break
            if article["url"] not in taken:
                selected.append(article)
    return selected

# ============================================================
# GROQ
# ============================================================

def call_groq(system: str, user: str, temperature: float = 0.45,
              max_tokens: int = 6000, retries: int = 2) -> Optional[str]:
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
            if r.status_code == 413:
                print(f"[groq] ❌ 413 Payload Too Large (size={len(user)})")
                return "PAYLOAD_TOO_LARGE"
            if r.status_code == 401:
                print("━" * 50)
                print("[groq] ❌ 401 Unauthorized — مفتاح Groq مرفوض!")
                print("[groq] 🔧 الحل:")
                print("[groq]   1. اذهب إلى https://console.groq.com/keys")
                print("[groq]   2. ولّد مفتاح جديد (يبدأ بـ gsk_)")
                print("[groq]   3. حدّث GROQ_API_KEY في Railway Variables")
                print("━" * 50)
                return "INVALID_API_KEY"
            if r.status_code == 429:
                print(f"[groq] ⚠️ 429 Rate Limit — انتظار...")
                time.sleep(20)
                continue
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            print(f"[groq] محاولة {attempt + 1}: {exc}")
            if attempt < retries:
                time.sleep(5)
    return None

def call_groq_adaptive(system: str, articles_compact: List[Dict],
                       videos_compact: List[Dict], trends: List[str],
                       user_template: str, n: int = 5) -> Optional[str]:
    attempts = [
        (len(articles_compact), len(videos_compact)),
        (min(40, len(articles_compact)), min(10, len(videos_compact))),
        (min(28, len(articles_compact)), min(8, len(videos_compact))),
        (min(20, len(articles_compact)), min(6, len(videos_compact))),
    ]
    for art_n, vid_n in attempts:
        user = user_template.format(
            n=n,
            articles=json.dumps(articles_compact[:art_n], ensure_ascii=False),
            videos=json.dumps(videos_compact[:vid_n], ensure_ascii=False),
            trends=json.dumps(trends, ensure_ascii=False),
        )
        size_kb = len(user.encode("utf-8")) / 1024
        print(f"[groq] محاولة: {art_n} خبر + {vid_n} فيديو = {size_kb:.1f} KB")
        result = call_groq(system, user, temperature=0.5, max_tokens=6500, retries=1)
        if result == "PAYLOAD_TOO_LARGE":
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

NEWS_SYSTEM = """أنت محرر قناة تقنية سعودية بأسلوب المؤثرين التقنيين مثل أياد الحمود، فيصل سيف، وأسامة السبع.
جمهورك: السعوديون والخليجيون المهتمون بالتقنية والذكاء الاصطناعي.

🎯 أسلوبك:
• لهجة سعودية معاصرة — مثل ما تكلم صاحبك عن خبر قرأته للتو
• مباشر وبدون فلسفة: الخبر والتفاصيل، خلاص
• ممنوع الفصحى الجامدة الثقيلة — خلها طبيعية سلسة
• أول جملة تشد الانتباه فوراً — رقم، اسم، حدث
• ممنوع الكلمات المستهلكة: ثوري، مذهل، لا يصدق، يغير اللعبة، اختراق تاريخي
• دقة في الأرقام والأسماء — لا تخترع شيء
• كل جملة فيها قيمة — لا حشو لا تكرار
• تكتب كأنك إنسان حقيقي، لا بوت ولا ترجمة آلية

📝 مثال على النبرة:
❌ سيء (فصحى جامدة): "أعلنت شركة OpenAI في بيان رسمي صادر عنها عن إطلاق نموذجها الجديد"
✅ جيد (سعودي حديث): "OpenAI طلقت اليوم GPT-5 Turbo، أسرع وأقوى بـ 40%"

❌ سيء (ترجمة آلية): "يتوجب على المطورين العرب أخذ هذا الأمر بعين الاعتبار"
✅ جيد (مباشر): "لو أنت مطور، هذا الخبر يهمك مباشرة" """

NEWS_USER = """اختر {n} أخبار من القائمة التالية بمعايير صارمة.

⚠️ قواعد التنوع الحتمية:
• MAX خبر واحد لكل شركة (OpenAI/Anthropic/Google كلها مرة واحدة فقط)
• نوّع فئات: إطلاق + بحث + تمويل + سياسة + منتج + جدل
• نوّع جغرافياً: US + EU + China + MENA بتوازن
• استبعد: الإعلانات التسويقية، الآراء، التكرار، الشركات المجهولة

الأخبار (id=رقم، t=عنوان، s=ملخص، src=مصدر):
{articles}

الفيديوهات للربط (vid=رقم، t=عنوان، ch=قناة — null إذا لا يوجد ربط منطقي):
{videos}

الترند العالمي الحالي على Twitter:
{trends}

لكل خبر مختار، أرجع JSON بهذا الشكل بالضبط:
{{
  "id": <رقم id>,
  "category": "launch|research|funding|partnership|product|controversy|policy|benchmark|tool|release|acquisition",
  "category_ar": "إطلاق|بحث|تمويل|شراكة|منتج|جدل|سياسة|معيار|أداة|تحديث|استحواذ",
  "company": "الشركة الرئيسية بالإنجليزية",
  "region": "US|EU|China|MENA|Asia|Global",
  "headline": "عنوان قوي جذاب 50-85 حرف بأسلوب سعودي حديث - لا تبدأ بـ (أعلنت) أو (في خطوة)",
  "details": "تفاصيل الخبر كاملة 6-8 جمل 600-900 حرف - ابدأ بجملة قوية تشد الانتباه - اذكر الأرقام والأسماء والميزات الجديدة - اشرح ماذا يفعل وكيف يعمل ومتى يتوفر - أسلوب سعودي سلس كأنك تحكي لصاحبك",
  "source_name": "اسم المصدر بنفس ما وصلك في src — مثل: OpenAI Blog أو TechCrunch أو رويترز",
  "ready_tweet": "تغريدة 200-260 حرف بأسلوب سعودي حديث - تبدأ برقم/سؤال/ملاحظة - تنتهي بفكرة قوية - بدون هاشتاقات داخلها",
  "hashtags": ["7 هاشتاقات حقيقية للنمو على Twitter"],
  "related_video_id": <vid أو null>,
  "importance": 1-10
}}

🏷️ قواعد الهاشتاقات الصارمة:
• استخدم فقط هاشتاقات حقيقية وكاملة — ممنوع الهاشتاقات المقطوعة
• الهاشتاقات الإنجليزية (5 منها من القائمة الآمنة):
   #AI #ML #LLM #ArtificialIntelligence #ChatGPT #Tech #TechNews #Innovation
   #MachineLearning #DeepLearning #GenAI #GenerativeAI #AIAgents
   #AIResearch #OpenSourceAI #FutureOfAI #AITools #AIRevolution
   #OpenAI #Claude #Gemini #Llama #GoogleAI #MetaAI #Microsoft
   #Anthropic #MistralAI #NVIDIA #HuggingFace #DeepSeek
• الهاشتاقات العربية (1-2 من القائمة الآمنة فقط):
   #الذكاء_الاصطناعي  #ذكاء_اصطناعي  #تقنية  #تكنولوجيا
   #برمجة  #ابتكار  #ستارتب  #ريادة_الأعمال  #تحول_رقمي  #رؤية_2030
• ❌ ممنوع اختراع هاشتاقات عربية مركبة جديدة
• ❌ ممنوع الهاشتاقات التي أقل من 3 أحرف (ما عدا #AI #ML #AR #VR #AGI)

📱 قواعد التغريدة:
• تبدو مكتوبة من مؤثر سعودي تقني (أياد الحمود، فيصل سيف، السبع)
• لا تبدأ بـ "أعلنت" أو "في خطوة" — تقليدية جداً
• تبدأ برقم لافت، سؤال محفز، أو ملاحظة حادة
• تنتهي بفكرة قوية أو خلاصة واضحة
• لهجة سعودية حديثة، سلسة، بدون تصنع

أرجع JSON array فقط. بدون markdown. بدون شرح قبل أو بعد."""

REPORT_SYSTEM = """أنت محلل أول لصناعة الذكاء الاصطناعي. تكتب تقارير يومية عميقة."""

REPORT_USER = """اكتب تقرير اليوم عن أبرز أحداث AI.

الأخبار (آخر 24 ساعة، t=عنوان، s=ملخص):
{articles}

أرجع JSON:
{{
  "theme_of_the_day": "موضوع اليوم المحوري في عبارة قوية",
  "top_stories": [
    {{"rank": 1, "headline": "عنوان قوي", "summary": "2-3 جمل (250-350 حرف)"}},
    {{"rank": 2, "headline": "...", "summary": "..."}},
    {{"rank": 3, "headline": "...", "summary": "..."}}
  ],
  "reading_between_lines": "تحليل 4-5 جمل - ما النمط؟",
  "tomorrow_watch": "جملتان: ماذا نترقب؟"
}}

قواعد: نوّع الشركات والمناطق — لا تكن كلها عن شركة واحدة.
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

# قائمة هاشتاقات عربية آمنة (تُقبل فقط هذي)
SAFE_ARABIC_HASHTAGS = {
    "#الذكاء_الاصطناعي", "#ذكاء_اصطناعي", "#تقنية", "#تكنولوجيا",
    "#برمجة", "#ابتكار", "#ستارتب", "#ريادة_الأعمال",
    "#تحول_رقمي", "#رؤية_2030", "#تقنيات",
}

# الأجزاء العربية المقبولة في الهاشتاقات (whitelist)
ARABIC_HASHTAG_TOKENS = {
    "الذكاء", "الاصطناعي", "ذكاء", "اصطناعي",
    "تقنية", "تكنولوجيا", "برمجة", "ابتكار",
    "ستارتب", "ريادة", "الأعمال", "تحول", "رقمي",
    "رؤية", "2030", "تقنيات",
}

# اختصارات إنجليزية من حرفين مسموحة
SAFE_SHORT_EN_HASHTAGS = {
    "#AI", "#ML", "#AR", "#VR", "#IT", "#UX", "#UI",
    "#AGI", "#DL", "#NLP", "#GPT", "#LLM",
}

def is_arabic_char(c: str) -> bool:
    return "\u0600" <= c <= "\u06FF"

def clean_hashtag(tag: str) -> Optional[str]:
    """تنظيف الهاشتاق مع فلترة صارمة ضد المكسور."""
    if not isinstance(tag, str):
        return None
    tag = tag.strip()
    if not tag.startswith("#"):
        tag = "#" + tag
    tag = re.sub(r"[^\w\u0600-\u06FF#_]", "", tag)

    body = tag[1:]
    if len(body) < 2:
        return None

    # تحديد: هل الهاشتاق عربي؟
    has_arabic = any(is_arabic_char(c) for c in body)

    if has_arabic:
        # إذا عربي: لازم يكون من القائمة الآمنة
        if tag in SAFE_ARABIC_HASHTAGS:
            return tag
        tokens = body.split("_")
        if all(t in ARABIC_HASHTAG_TOKENS or t.isdigit() for t in tokens if t):
            return tag
        return None

    # اختصارات إنجليزية من حرفين — السماح فقط من whitelist
    if len(body) == 2:
        return tag if tag.upper() in SAFE_SHORT_EN_HASHTAGS else None

    # إنجليزي عادي: 3+ أحرف ويبدأ بحرف
    if len(body) < 3:
        return None
    if not body[0].isalpha():
        return None
    return tag

def format_news(item: Dict, video_url: Optional[str] = None,
                source_url: Optional[str] = None) -> str:
    """تنسيق مبسط: عنوان + تفاصيل + فيديو/مصدر + تغريدة."""
    emoji = CATEGORY_EMOJI.get(item.get("category", ""), "📰")
    cat = esc(item.get("category_ar", "خبر"))
    company = esc(item.get("company", "")).strip()
    region = item.get("region", "")
    flag = REGION_FLAG.get(region, "")
    headline = esc(item.get("headline", ""))
    details = esc(item.get("details", ""))
    source_name = esc(item.get("source_name", "")).strip()
    tweet = (item.get("ready_tweet", "") or "").strip()
    hashtags = item.get("hashtags", []) or []

    header_line = f"{emoji} <b>{cat}</b>"
    if company:
        header_line += f"  ·  <b>{company}</b>"
    if flag:
        header_line += f"  {flag}"

    sep = "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"

    blocks: List[str] = [header_line, sep, f"<b>{headline}</b>", "", details]

    # فيديو ذو صلة (إن وجد)
    if video_url:
        blocks += [sep, f'🎬 <a href="{esc(video_url)}"><b>فيديو يشرح الموضوع</b></a>']

    # المصدر — دائماً يظهر إذا متوفر
    if source_name or source_url:
        blocks.append(sep)
        if source_url and source_name:
            blocks.append(f'📎 <b>المصدر:</b> <a href="{esc(source_url)}">{source_name}</a>')
        elif source_name:
            blocks.append(f"📎 <b>المصدر:</b> {source_name}")
        elif source_url:
            blocks.append(f'📎 <a href="{esc(source_url)}">رابط الخبر</a>')

    # تغريدة جاهزة
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

def telegram_send_message(message: str, preview_url: Optional[str] = None,
                          disable_preview: bool = False) -> bool:
    """إرسال رسالة مع صورة كبيرة من preview_url (إن وجد)."""
    if len(message) > 4050:
        message = message[:4040] + "…"

    payload: Dict[str, Any] = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }

    if preview_url and not disable_preview:
        # preview_url لا يظهر في النص، فقط يستخدم لجلب الصورة
        payload["link_preview_options"] = {
            "is_disabled": False,
            "url": preview_url,
            "prefer_large_media": True,
            "show_above_text": True,
        }
    else:
        payload["disable_web_page_preview"] = True

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json=payload, timeout=30)
        if r.status_code == 200:
            return True
        print(f"[telegram] {r.status_code}: {r.text[:200]}")
        # fallback: إزالة link_preview_options
        if "link_preview_options" in payload:
            payload.pop("link_preview_options")
            payload["disable_web_page_preview"] = True
            r = requests.post(url, json=payload, timeout=30)
            return r.status_code == 200
        return False
    except Exception as exc:
        print(f"[telegram] {exc}")
        return False

def telegram_send_photo(photo_url: str, caption: str) -> bool:
    """إرسال صورة مع caption (حد أقصى 1024 حرف)."""
    if len(caption) > 1020:
        caption = caption[:1015] + "…"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML",
    }
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        r = requests.post(url, json=payload, timeout=30)
        if r.status_code == 200:
            return True
        print(f"[tg-photo] {r.status_code}: {r.text[:200]}")
        return False
    except Exception as exc:
        print(f"[tg-photo] {exc}")
        return False

# ============================================================
# CYCLES
# ============================================================

def fetch_all_news(hours: int = 6) -> List[Dict]:
    t0 = time.time()
    print(f"\n🌍 جلب من {len(NEWS_SOURCES)} مصدر + {len(GOOGLE_NEWS_QUERIES)} Google News...")
    direct = fetch_sources_parallel(NEWS_SOURCES, hours=hours)
    gnews = fetch_google_news(GOOGLE_NEWS_QUERIES, hours=hours)
    all_articles = direct + gnews
    elapsed = time.time() - t0
    print(f"[fetch-all] إجمالي: {len(all_articles)} مقال في {elapsed:.1f}س")
    return all_articles

def news_cycle() -> None:
    ts = datetime.now(RIYADH_TZ).strftime("%Y-%m-%d %H:%M")
    print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"[news-cycle] {ts}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    url_cache = load_cache()
    title_cache = load_title_cache()

    # 6 ساعات — لأن الدورة كل 4 ساعات، نريد overlap
    articles = fetch_all_news(hours=6)
    if not articles:
        print("[news] لا محتوى")
        return

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

    print(f"[news] فريدة بعد dedup: {len(unique)}")
    if len(unique) < 4:
        print("[news] تخطي — محتوى غير كافٍ")
        return

    sampled = diversify_articles(unique, target=50)
    print(f"[news] بعد sampling: {len(sampled)}")

    videos = fetch_youtube_videos(hours=72)[:12]
    world_trends = filter_relevant_trends(fetch_worldwide_trends(), max_n=6)
    print(f"[trends] {world_trends[:4]}")

    articles_compact = [{
        "id": i, "t": a["title"][:180], "s": a["summary"][:150],
        "src": a["source"],
    } for i, a in enumerate(sampled)]

    videos_compact = [{
        "vid": i, "t": v["title"][:140], "ch": v["channel"],
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

    # Post-filter: تنويع إجباري
    curated = sorted(curated, key=lambda x: x.get("importance", 5), reverse=True)
    final_items: List[Dict] = []
    seen_companies = set()
    for item in curated:
        company = (item.get("company") or "").lower().strip()
        if company and company in seen_companies:
            continue
        seen_companies.add(company)
        final_items.append(item)
        if len(final_items) >= 5:
            break

    print(f"[news] اختيار نهائي: {len(final_items)} ({seen_companies})")

    # جلب og:images بالتوازي — للمقالات المختارة فقط
    # نفعل redirect resolution على Google News URLs أولاً
    articles_for_images: List[Dict] = []
    final_urls: Dict[int, str] = {}  # idx -> final URL (بعد redirect)

    for idx, item in enumerate(final_items):
        try:
            nid = int(item.get("id", -1))
            if 0 <= nid < len(sampled):
                original = sampled[nid]
                # حل redirect إذا من Google News
                final_url = resolve_redirect_url(original["url"])
                final_urls[idx] = final_url
                articles_for_images.append({"url": final_url})
            else:
                articles_for_images.append({"url": ""})
                final_urls[idx] = ""
        except (ValueError, TypeError):
            articles_for_images.append({"url": ""})
            final_urls[idx] = ""

    resolved_count = sum(1 for u in final_urls.values()
                         if u and "news.google.com" not in u)
    print(f"[redirects] حُلّ {resolved_count}/{len(final_items)} Google News URL")

    images = fetch_images_parallel(articles_for_images)

    sent = 0
    for idx, item in enumerate(final_items):
        try:
            nid = int(item.get("id", -1))
            if nid < 0 or nid >= len(sampled):
                continue
            original = sampled[nid]

            # تحديد فيديو مرتبط
            video_url = None
            vid = item.get("related_video_id")
            if vid is not None:
                try:
                    vid = int(vid)
                    if 0 <= vid < len(videos):
                        video_url = videos[vid]["url"]
                except (ValueError, TypeError):
                    pass

            message = format_news(
                item,
                video_url=video_url,
                source_url=final_url or original["url"],
            )

            # استراتيجية الصور:
            # 1. إذا فيه og:image → استخدم final_url (بعد redirect)
            # 2. وإلا إذا فيه فيديو YouTube → استخدم الفيديو
            # 3. وإلا → نص فقط
            og_image = images.get(idx)
            final_url = final_urls.get(idx, "")
            preview_url = None
            if og_image and final_url:
                preview_url = final_url  # Telegram يسحب og:image منه
            elif video_url:
                preview_url = video_url

            ok = telegram_send_message(
                message,
                preview_url=preview_url,
                disable_preview=(preview_url is None),
            )
            if ok:
                url_cache.add(url_hash(original["title"], original["url"]))
                title_cache.add(title_hash(original["title"]))
                sent += 1
                time.sleep(6)  # تباعد طبيعي بين الأخبار
        except Exception as exc:
            print(f"[news] خطأ: {exc}")

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

    sampled = diversify_articles(articles, target=30)
    compact = [{"t": a["title"][:180], "s": a["summary"][:150]} for a in sampled]
    size_kb = len(json.dumps(compact, ensure_ascii=False).encode("utf-8")) / 1024
    print(f"[report] payload: {len(compact)} خبر ({size_kb:.1f} KB)")

    raw = call_groq(
        REPORT_SYSTEM,
        REPORT_USER.format(articles=json.dumps(compact, ensure_ascii=False)),
        temperature=0.5, max_tokens=3000,
    )
    if raw == "PAYLOAD_TOO_LARGE":
        compact = compact[:18]
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
    telegram_send_message(message, disable_preview=True)
    print("[report] ✅ أُرسل")

# ============================================================
# STARTUP
# ============================================================

def verify_groq_key() -> bool:
    """تحقق من صحة مفتاح Groq والنموذج. يحوّل لـ fallback إذا النموذج الأساسي مو متاح."""
    global GROQ_MODEL
    print(f"[health] فحص مفتاح Groq API والنموذج ({GROQ_MODEL})...")

    def try_model(model_id: str) -> Tuple[bool, int]:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                         "Content-Type": "application/json"},
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5,
                },
                timeout=15,
            )
            return r.status_code == 200, r.status_code
        except Exception as exc:
            print(f"[health] خطأ اتصال: {exc}")
            return False, 0

    ok, status = try_model(GROQ_MODEL)
    if ok:
        print(f"[health] ✅ المفتاح والنموذج {GROQ_MODEL} يعملان")
        return True

    if status == 401:
        print("━" * 50)
        print("[health] ❌ مفتاح Groq مرفوض (401)")
        print("[health] 🔧 افتح https://console.groq.com/keys وولّد جديد")
        print("━" * 50)
        return False

    # النموذج مش متاح — جرب fallback
    if status in (400, 404):
        print(f"[health] ⚠️ النموذج {GROQ_MODEL} غير متاح — تجريب fallback...")
        ok2, status2 = try_model(GROQ_FALLBACK_MODEL)
        if ok2:
            print(f"[health] ✅ تم التبديل إلى {GROQ_FALLBACK_MODEL}")
            GROQ_MODEL = GROQ_FALLBACK_MODEL
            return True
        print(f"[health] ❌ الـ fallback فشل أيضاً ({status2})")
        return False

    print(f"[health] ⚠️ رد غير متوقع: {status}")
    return False

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
    print("  FahadAI News Bot v6")
    print("  Newsroom Edition")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"✅ كل المتغيرات محمّلة")
    print(f"📰 مصادر منتقاة: {len(NEWS_SOURCES)}")
    print(f"🔍 Google News: {len(GOOGLE_NEWS_QUERIES)} استعلام / 8 لغات")
    print(f"🎬 YouTube: {len(YOUTUBE_CHANNELS)} قناة")
    print(f"🖼️  og:image extraction: مُفعّل")
    print(f"⚡ Parallel workers: {FETCH_WORKERS}")
    print(f"⏰ الوقت: {datetime.now(RIYADH_TZ).strftime('%Y-%m-%d %H:%M:%S')} (الرياض)")

    # فحص حيوية المفتاح قبل الجدولة
    if not verify_groq_key():
        print("\n⛔ توقف التشغيل — مفتاح Groq غير صالح")
        print("   أصلح المفتاح في Railway Variables ثم Railway يعيد التشغيل")
        raise SystemExit(1)

def main() -> None:
    startup_check()

    scheduler = BlockingScheduler(timezone=RIYADH_TZ)

    # 4 دورات أخبار — أوقات ذروة التفاعل في المنطقة العربية
    # 8ص = قبل الدوام | 1ظ = وقت الغداء | 6م = رجعة الدوام | 10م = قبل النوم
    scheduler.add_job(
        news_cycle,
        CronTrigger(hour="8,13,18,22", minute=0, timezone=RIYADH_TZ),
        id="news", max_instances=1, coalesce=True,
    )

    # تقرير يومي 11م — بعد آخر دورة أخبار بساعة
    scheduler.add_job(
        report_cycle,
        CronTrigger(hour=23, minute=0, timezone=RIYADH_TZ),
        id="report", max_instances=1, coalesce=True,
    )

    print("\n📅 المواعيد المجدولة (4 دورات/يوم):")
    print("   📰 أخبار: 8ص · 1ظ · 6م · 10م (أوقات الذروة في المنطقة العربية)")
    print("   📊 تقرير يومي شامل: 11 مساءً")

    print("\n▶️ تشغيل دورة فورية...")
    try:
        news_cycle()
    except Exception as exc:
        print(f"[startup-cycle] {exc}")

    print("\n⏰ الجدولة شغالة — في انتظار المواعيد...\n")
    scheduler.start()


if __name__ == "__main__":
    main()
