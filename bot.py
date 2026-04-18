"""
AI News Bot v4 — Signature Edition
قناة @fahadai · Telegram

التغييرات الرئيسية عن v3:
  ✨ أسلوب جديد كلياً (hook + تحليل عميق + تغريدة جاهزة)
  📱 تغريدة جاهزة للنسخ مع هاشتاقات ترند عالمية حقيقية
  🎬 ربط فيديو YouTube بالخبر تلقائياً
  📖 محتوى أطول وأعمق (1200+ حرف/خبر)
  🚫 حذف مصدر الخبر الأصلي وتوقيع القناة

المتغيرات المطلوبة:
  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import unquote

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
TRENDS_CACHE_FILE = "/tmp/fahadai_trends.json"
MAX_CACHE_SIZE = 1000

# ============================================================
# SOURCES
# ============================================================

NEWS_SOURCES = {
    # شركات AI الرئيسية
    "Anthropic": "https://www.anthropic.com/news/rss.xml",
    "OpenAI": "https://openai.com/blog/rss.xml",
    "Google DeepMind": "https://deepmind.google/blog/rss.xml",
    "Google AI": "https://blog.google/technology/ai/rss/",
    "Meta AI": "https://ai.meta.com/blog/rss/",
    "Microsoft AI": "https://blogs.microsoft.com/ai/feed/",
    "Mistral": "https://mistral.ai/news/rss.xml",
    "HuggingFace": "https://huggingface.co/blog/feed.xml",
    "Cohere": "https://cohere.com/blog/rss.xml",
    "Stability AI": "https://stability.ai/blog?format=rss",
    # إعلام تقني
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "The Verge AI": "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
    "VentureBeat AI": "https://venturebeat.com/category/ai/feed/",
    "MIT Tech Review": "https://www.technologyreview.com/feed/",
    "Wired AI": "https://www.wired.com/feed/tag/ai/latest/rss",
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "ZDNet AI": "https://www.zdnet.com/topic/artificial-intelligence/rss.xml",
    "IEEE Spectrum AI": "https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss",
    "Semafor Tech": "https://www.semafor.com/technology/feed.xml",
    # أبحاث
    "ArXiv AI": "http://export.arxiv.org/rss/cs.AI",
    "ArXiv ML": "http://export.arxiv.org/rss/cs.LG",
    "ArXiv NLP": "http://export.arxiv.org/rss/cs.CL",
    # نشرات AI
    "The Batch": "https://www.deeplearning.ai/the-batch/feed/",
    "Import AI": "https://jack-clark.net/feed/",
    "Towards AI": "https://pub.towardsai.net/feed",
    # مصادر عربية
    "عالم التقنية": "https://www.tech-wd.com/wd/feed/",
    "أرابيان بزنس": "https://arabic.arabianbusiness.com/feed",
    "رواد الأعمال": "https://www.rowadalaamal.com/feed/",
    "Wamda": "https://www.wamda.com/feed",
    "Arab News": "https://www.arabnews.com/rss.xml",
    "Saudi Gazette": "https://saudigazette.com.sa/rss/technology",
}

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
    """جلب ترند هاشتاقات من trends24.in مع cache 3 ساعات."""
    try:
        with open(TRENDS_CACHE_FILE, "r") as f:
            cached = json.load(f)
            if time.time() - cached.get("ts", 0) < 10800:
                return cached.get("hashtags", [])
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    collected: List[str] = []
    urls = [
        "https://trends24.in/united-states/",
        "https://trends24.in/saudi-arabia/",
    ]

    for url in urls:
        try:
            r = requests.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/120.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                },
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
    """فلترة الترند — استبعاد غير المناسب لقناة AI."""
    blacklist = [
        "bts", "kpop", "blackpink", "exo", "mls", "nba", "nfl",
        "playoff", "election", "trump", "biden", "taylor",
        "swift", "marvel", "wwe", "ufc", "nascar",
    ]
    tech_keywords = [
        "ai", "tech", "chatgpt", "gpt", "llm", "gemini",
        "claude", "openai", "google", "apple", "meta",
        "code", "dev", "iphone", "bitcoin", "crypto",
        "elon", "nvidia", "startup", "tesla",
    ]
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

def save_cache(cache: set) -> None:
    trimmed = list(cache)[-MAX_CACHE_SIZE:]
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(trimmed, f)
    except Exception as exc:
        print(f"[cache] {exc}")

def item_hash(title: str, url: str) -> str:
    return hashlib.md5(f"{title}|{url}".encode("utf-8")).hexdigest()[:16]

# ============================================================
# RSS FETCHING
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

def fetch_rss(url: str, source: str, hours: int = 4) -> List[Dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    items: List[Dict] = []
    try:
        feed = feedparser.parse(
            url,
            request_headers={"User-Agent": "Mozilla/5.0 (FahadAI-Bot/4.0)"},
        )
        for entry in feed.entries[:20]:
            published = parse_entry_date(entry)
            if not published or published < cutoff:
                continue
            title = (getattr(entry, "title", "") or "").strip()
            link = (getattr(entry, "link", "") or "").strip()
            summary = clean_html(getattr(entry, "summary", ""))[:800]
            if title and link:
                items.append({
                    "title": title, "url": link,
                    "summary": summary, "source": source,
                })
    except Exception as exc:
        print(f"[rss] {source}: {exc}")
    return items

def fetch_all_news(hours: int = 4) -> List[Dict]:
    collected: List[Dict] = []
    for name, url in NEWS_SOURCES.items():
        collected.extend(fetch_rss(url, name, hours=hours))
        time.sleep(0.2)
    print(f"[news] {len(collected)} مقال من {len(NEWS_SOURCES)} مصدر (آخر {hours}س)")
    return collected

def fetch_youtube_videos(hours: int = 72) -> List[Dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    videos: List[Dict] = []
    for channel, cid in YOUTUBE_CHANNELS.items():
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:4]:
                published = parse_entry_date(entry)
                if not published or published < cutoff:
                    continue
                videos.append({
                    "title": (getattr(entry, "title", "") or "").strip(),
                    "url": (getattr(entry, "link", "") or "").strip(),
                    "channel": channel,
                    "summary": clean_html(getattr(entry, "summary", ""))[:300],
                })
        except Exception as exc:
            print(f"[youtube] {channel}: {exc}")
        time.sleep(0.2)
    print(f"[videos] {len(videos)} فيديو من {len(YOUTUBE_CHANNELS)} قناة")
    return videos

# ============================================================
# GROQ CLIENT
# ============================================================

def call_groq(system: str, user: str, temperature: float = 0.45,
              max_tokens: int = 5500, retries: int = 2) -> Optional[str]:
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
                timeout=120,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            print(f"[groq] محاولة {attempt + 1}: {exc}")
            if attempt < retries:
                time.sleep(4)
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

NEWS_USER = """اختر أهم {n} أخبار من القائمة واكتب تحليلاً احترافياً لكل خبر.

الأخبار المتاحة (مرقمة بـ id):
{articles}

الفيديوهات المتاحة للربط (مرقمة بـ vid — null إذا لا يوجد ربط):
{videos}

الترند العالمي الحالي على Twitter (استفد منه في التغريدة إن كان ذا صلة):
{trends}

لكل خبر مختار، أرجع JSON بهذا الشكل بالضبط:
{{
  "id": <رقم id>,
  "category": "launch|research|funding|partnership|product|controversy|policy|benchmark|tool|release|acquisition",
  "category_ar": "إطلاق|بحث|تمويل|شراكة|منتج|جدل|سياسة|معيار|أداة|تحديث|استحواذ",
  "company": "الشركة أو المنتج الرئيسي (بالإنجليزية)",
  "headline": "عنوان عربي قوي جذاب (50-85 حرف) يجعل القارئ يتوقف",
  "hook": "جملة افتتاحية قوية تختصر ليش هذا الخبر يستحق وقتك الآن (100-180 حرف)",
  "details": "التفاصيل الشاملة - 4-6 جمل - 450-650 حرف - أرقام حقيقية وأسماء دقيقة وسياق تاريخي مختصر",
  "why_matters": "ليش الخبر مهم تحديداً للمطور العربي أو الشركات الناشئة أو المستثمر - جملتان قويتان (180-280 حرف)",
  "reading_between_lines": "تحليل استراتيجي لما وراء الخبر - النوايا الحقيقية، المنافسة الخفية، التوجه طويل المدى (180-280 حرف)",
  "ready_tweet": "تغريدة عربية كاملة جاهزة للنسخ - أسلوب إنساني جذاب يشد المتابع - 200-260 حرف - بدون هاشتاقات داخل النص - بدون روابط - تبدو كتغريدة إنسان محترف وليس بوت",
  "hashtags": ["5-7 هاشتاقات حقيقية مستخدمة على Twitter: مزيج من #AI و#ChatGPT إلخ + هاشتاق عربي + هاشتاقات محددة للخبر + 1-2 من الترند إن كان مناسباً"],
  "related_video_id": <رقم vid إذا الفيديو فعلاً يناقش نفس الموضوع/الشركة، وإلا null>,
  "importance": 1-10
}}

معايير الاختيار:
• استبعد: إعلانات تسويقية، مقالات رأي عامة، تكرار أخبار سابقة، شركات مجهولة صغيرة
• اختر: إطلاقات نماذج، اختراقات بحثية، صفقات كبرى، تحولات استراتيجية، تقييمات أداء

قواعد الهاشتاقات:
• كلها حقيقية ومستخدمة (لا تخترع)
• نصفها إنجليزي عام (#AI #ChatGPT #Tech) ونصفها محدد للخبر (#OpenAI #Gemini)
• واحد عربي على الأقل (#الذكاء_الاصطناعي)
• إن وجد في الترند هاشتاق مناسب، أدرجه

قواعد التغريدة الجاهزة:
• تبدو إنسانية مو آلية — كأن كاتبها خبير تقني عربي
• تبدأ بما يلفت الانتباه (سؤال، رقم، ملاحظة حادة)
• تنتهي بخلاصة أو فكرة قوية

قواعد الربط بالفيديو:
• اختر vid فقط إذا الفيديو فعلاً عن نفس الموضوع/الشركة
• لو غير متأكد، ضع null

أرجع JSON array فقط. بدون markdown. بدون نص قبل أو بعد."""

REPORT_SYSTEM = """أنت محلل أول لصناعة الذكاء الاصطناعي. تكتب تقارير يومية عميقة بلغة استراتيجية."""

REPORT_USER = """اكتب تقرير اليوم عن أبرز أحداث AI.

الأخبار (آخر 24 ساعة):
{articles}

أرجع JSON:
{{
  "theme_of_the_day": "موضوع اليوم المحوري في عبارة واحدة قوية",
  "top_stories": [
    {{"rank": 1, "headline": "عنوان قوي", "summary": "2-3 جمل عميقة (250-350 حرف)"}},
    {{"rank": 2, "headline": "...", "summary": "..."}},
    {{"rank": 3, "headline": "...", "summary": "..."}}
  ],
  "reading_between_lines": "تحليل 4-5 جمل - ما النمط الذي تكشفه أخبار اليوم مجتمعة؟",
  "tomorrow_watch": "جملتان: ماذا نترقب؟"
}}

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
    # السماح بالحروف العربية والإنجليزية والأرقام والـ underscore
    tag = re.sub(r"[^\w\u0600-\u06FF#_]", "", tag)
    return tag if len(tag) > 2 else None

def format_news(item: Dict, video_url: Optional[str] = None) -> str:
    """التنسيق الجديد — بدون مصدر، بدون توقيع، تغريدة جاهزة."""
    emoji = CATEGORY_EMOJI.get(item.get("category", ""), "📰")
    cat = esc(item.get("category_ar", "خبر"))
    company = esc(item.get("company", "")).strip()
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
# TELEGRAM SEND
# ============================================================

def send_telegram(message: str, disable_preview: bool = False,
                  preview_above: bool = False) -> bool:
    if len(message) > 4050:
        message = message[:4040] + "…"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": disable_preview,
    }
    if not disable_preview and preview_above:
        payload["link_preview_options"] = {
            "is_disabled": False,
            "prefer_large_media": True,
            "show_above_text": True,
        }

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json=payload, timeout=30)
        if r.status_code != 200:
            print(f"[telegram] {r.status_code}: {r.text[:300]}")
            # fallback بدون preview options إذا فشل
            if "link_preview_options" in payload:
                payload.pop("link_preview_options")
                r = requests.post(url, json=payload, timeout=30)
                return r.status_code == 200
            return False
        return True
    except Exception as exc:
        print(f"[telegram] exception: {exc}")
        return False

# ============================================================
# CYCLES
# ============================================================

def news_cycle() -> None:
    ts = datetime.now(RIYADH_TZ).strftime("%Y-%m-%d %H:%M")
    print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"[news-cycle] {ts}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    cache = load_cache()
    articles = fetch_all_news(hours=4)
    fresh = [a for a in articles if item_hash(a["title"], a["url"]) not in cache]
    print(f"[news] جديدة بعد dedup: {len(fresh)}")
    if len(fresh) < 3:
        print("[news] تخطي — محتوى غير كافٍ")
        return

    videos = fetch_youtube_videos(hours=72)
    video_pool = videos[:40]

    world_trends = fetch_worldwide_trends()
    relevant_trends = filter_relevant_trends(world_trends, max_n=8)
    print(f"[trends] مناسبة: {len(relevant_trends)} — أمثلة: {relevant_trends[:4]}")

    news_pool = fresh[:60]
    articles_compact = [{
        "id": i,
        "title": a["title"][:240],
        "summary": a["summary"][:320],
        "source": a["source"],
    } for i, a in enumerate(news_pool)]

    videos_compact = [{
        "vid": i,
        "title": v["title"][:180],
        "channel": v["channel"],
    } for i, v in enumerate(video_pool)]

    raw = call_groq(
        NEWS_SYSTEM,
        NEWS_USER.format(
            n=5,
            articles=json.dumps(articles_compact, ensure_ascii=False),
            videos=json.dumps(videos_compact, ensure_ascii=False),
            trends=json.dumps(relevant_trends, ensure_ascii=False),
        ),
        temperature=0.45,
        max_tokens=6000,
    )
    curated = extract_json(raw)
    if not curated or not isinstance(curated, list):
        print("[news] فشل curation")
        return

    curated = sorted(curated, key=lambda x: x.get("importance", 5), reverse=True)[:5]
    sent = 0

    for item in curated:
        try:
            nid = int(item.get("id", -1))
            if nid < 0 or nid >= len(news_pool):
                continue
            original = news_pool[nid]

            video_url = None
            vid = item.get("related_video_id")
            if vid is not None:
                try:
                    vid = int(vid)
                    if 0 <= vid < len(video_pool):
                        video_url = video_pool[vid]["url"]
                except (ValueError, TypeError):
                    pass

            message = format_news(item, video_url=video_url)

            ok = send_telegram(
                message,
                disable_preview=(video_url is None),
                preview_above=(video_url is not None),
            )
            if ok:
                cache.add(item_hash(original["title"], original["url"]))
                sent += 1
                time.sleep(5)
        except Exception as exc:
            print(f"[news] خطأ في خبر: {exc}")

    save_cache(cache)
    print(f"[news] أُرسل {sent} خبر")

def report_cycle() -> None:
    ts = datetime.now(RIYADH_TZ).strftime("%Y-%m-%d %H:%M")
    print(f"\n━━━ [report-cycle] {ts} ━━━")

    articles = fetch_all_news(hours=24)
    if len(articles) < 5:
        print("[report] محتوى غير كافٍ")
        return

    compact = [{
        "title": a["title"][:240],
        "summary": a["summary"][:280],
        "source": a["source"],
    } for a in articles[:50]]

    raw = call_groq(
        REPORT_SYSTEM,
        REPORT_USER.format(articles=json.dumps(compact, ensure_ascii=False)),
        temperature=0.5,
        max_tokens=3000,
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
    print("[report] أُرسل")

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
    print("  FahadAI News Bot v4")
    print("  Signature Edition")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"✅ كل المتغيرات محمّلة")
    print(f"📰 مصادر أخبار: {len(NEWS_SOURCES)}")
    print(f"🎬 قنوات YouTube: {len(YOUTUBE_CHANNELS)}")
    print(f"🤖 النموذج: {GROQ_MODEL}")
    print(f"⏰ الوقت (الرياض): {datetime.now(RIYADH_TZ).strftime('%Y-%m-%d %H:%M:%S')}")

def main() -> None:
    startup_check()

    scheduler = BlockingScheduler(timezone=RIYADH_TZ)

    scheduler.add_job(
        news_cycle,
        CronTrigger(hour="8,12,16,20,0,4", minute=0, timezone=RIYADH_TZ),
        id="news", max_instances=1, coalesce=True,
    )

    scheduler.add_job(
        report_cycle,
        CronTrigger(hour=21, minute=0, timezone=RIYADH_TZ),
        id="report", max_instances=1, coalesce=True,
    )

    print("\n📅 المواعيد المجدولة:")
    print("   📰 أخبار: 8ص · 12ظ · 4ع · 8م · 12ص · 4ص")
    print("   📊 تقرير يومي: 9 مساءً")

    print("\n▶️ تشغيل دورة فورية...")
    try:
        news_cycle()
    except Exception as exc:
        print(f"[startup-cycle] {exc}")

    print("\n⏰ الجدولة شغالة — في انتظار المواعيد...\n")
    scheduler.start()


if __name__ == "__main__":
    main()
