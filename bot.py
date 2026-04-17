"""
AI News Bot v3 — Professional Edition
قناة @fahadai · Telegram فقط (بدون X)

الميزات:
  • جلب من 35+ مصدر أخبار + 8 قنوات YouTube
  • تنسيق HTML احترافي (بدون شروح تغريدات)
  • دورة أخبار كل 4 ساعات
  • تقرير يومي مسائي (9 مساءً الرياض)
  • فيديوهات مختارة يومياً (2 ظهراً الرياض)
  • حماية من التكرار بـ cache

المتغيرات المطلوبة:
  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY
"""

import hashlib
import json
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

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
CHANNEL_HANDLE = "@fahadai"

CACHE_FILE = "/tmp/fahadai_posted.json"
MAX_CACHE_SIZE = 800

# ============================================================
# SOURCES
# ============================================================

NEWS_SOURCES = {
    # --- شركات AI الرئيسية ---
    "Anthropic": "https://www.anthropic.com/news/rss.xml",
    "OpenAI": "https://openai.com/blog/rss.xml",
    "Google DeepMind": "https://deepmind.google/blog/rss.xml",
    "Google AI Blog": "https://blog.google/technology/ai/rss/",
    "Meta AI": "https://ai.meta.com/blog/rss/",
    "Microsoft AI": "https://blogs.microsoft.com/ai/feed/",
    "Mistral": "https://mistral.ai/news/rss.xml",
    "HuggingFace": "https://huggingface.co/blog/feed.xml",
    "Cohere": "https://cohere.com/blog/rss.xml",
    "Stability AI": "https://stability.ai/blog?format=rss",

    # --- إعلام تقني ---
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "The Verge AI": "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
    "VentureBeat AI": "https://venturebeat.com/category/ai/feed/",
    "MIT Tech Review": "https://www.technologyreview.com/feed/",
    "Wired AI": "https://www.wired.com/feed/tag/ai/latest/rss",
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "ZDNet AI": "https://www.zdnet.com/topic/artificial-intelligence/rss.xml",
    "IEEE Spectrum AI": "https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss",
    "Semafor Tech": "https://www.semafor.com/technology/feed.xml",

    # --- أبحاث ---
    "ArXiv AI": "http://export.arxiv.org/rss/cs.AI",
    "ArXiv ML": "http://export.arxiv.org/rss/cs.LG",
    "ArXiv NLP": "http://export.arxiv.org/rss/cs.CL",

    # --- نشرات وتحليلات AI ---
    "The Batch (DeepLearning.AI)": "https://www.deeplearning.ai/the-batch/feed/",
    "Import AI": "https://jack-clark.net/feed/",
    "Towards AI": "https://pub.towardsai.net/feed",

    # --- مصادر عربية ---
    "عالم التقنية": "https://www.tech-wd.com/wd/feed/",
    "أرابيان بزنس": "https://arabic.arabianbusiness.com/feed",
    "رواد الأعمال": "https://www.rowadalaamal.com/feed/",
    "Wamda": "https://www.wamda.com/feed",
    "Arab News": "https://www.arabnews.com/rss.xml",
    "Saudi Gazette Tech": "https://saudigazette.com.sa/rss/technology",
    "Al Arabiya Business": "https://english.alarabiya.net/.mrss/en/business.xml",
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
}

# ============================================================
# CACHE (Deduplication)
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
        print(f"[cache] save error: {exc}")

def item_hash(title: str, url: str) -> str:
    return hashlib.md5(f"{title}|{url}".encode("utf-8")).hexdigest()[:16]

# ============================================================
# RSS FETCHING
# ============================================================

def clean_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

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
            request_headers={"User-Agent": "Mozilla/5.0 (FahadAI-Bot/3.0)"},
        )
        for entry in feed.entries[:20]:
            published = parse_entry_date(entry)
            if not published or published < cutoff:
                continue
            title = (getattr(entry, "title", "") or "").strip()
            link = (getattr(entry, "link", "") or "").strip()
            summary = clean_html(getattr(entry, "summary", ""))[:600]
            if title and link:
                items.append({
                    "title": title,
                    "url": link,
                    "summary": summary,
                    "source": source,
                    "published": published.isoformat(),
                })
    except Exception as exc:
        print(f"[rss] {source}: {exc}")
    return items

def fetch_all_news(hours: int = 4) -> List[Dict]:
    collected: List[Dict] = []
    for name, url in NEWS_SOURCES.items():
        collected.extend(fetch_rss(url, name, hours=hours))
        time.sleep(0.25)
    print(f"[news] {len(collected)} articles from {len(NEWS_SOURCES)} sources (last {hours}h)")
    return collected

def fetch_youtube_videos(hours: int = 30) -> List[Dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    videos: List[Dict] = []
    for channel, cid in YOUTUBE_CHANNELS.items():
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]:
                published = parse_entry_date(entry)
                if not published or published < cutoff:
                    continue
                videos.append({
                    "title": (getattr(entry, "title", "") or "").strip(),
                    "url": (getattr(entry, "link", "") or "").strip(),
                    "channel": channel,
                    "summary": clean_html(getattr(entry, "summary", ""))[:400],
                    "published": published.isoformat(),
                })
        except Exception as exc:
            print(f"[youtube] {channel}: {exc}")
        time.sleep(0.25)
    print(f"[videos] {len(videos)} videos (last {hours}h)")
    return videos

# ============================================================
# GROQ CLIENT
# ============================================================

def call_groq(
    system: str,
    user: str,
    temperature: float = 0.4,
    max_tokens: int = 3500,
    retries: int = 2,
) -> Optional[str]:
    for attempt in range(retries + 1):
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=90,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            print(f"[groq] attempt {attempt + 1} failed: {exc}")
            if attempt < retries:
                time.sleep(3)
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

NEWS_SYSTEM = """أنت محرر رئيسي لقناة أخبار ذكاء اصطناعي عربية احترافية (مستوى The Neuron و TLDR AI).
القواعد:
- عربية فصيحة رفيعة، بلمسة سعودية مهنية هادئة
- لا حشو، لا مبالغة، لا كلمات تسويقية (ثوري، مذهل، لا يُصدَّق)
- جمل قصيرة واضحة
- دقة تامة في الأسماء والأرقام"""

NEWS_USER = """اختر أهم {n} أخبار من القائمة. كل خبر مرقم بـ id.

معايير الاختيار الصارمة:
1. تأثير حقيقي على الصناعة: إطلاق نموذج، اختراق بحثي، صفقة كبرى، تغيير سياسة
2. مصداقية المصدر وجدّة الخبر
3. أهمية للمطور/الشركة العربية

استبعد:
- إعلانات تسويقية أو PR
- مقالات رأي عامة
- أخبار شركات صغيرة مجهولة
- تكرار أخبار سابقة
- hype بدون جوهر

لكل خبر مختار أرجع JSON بالحقول التالية بالضبط:
{{
  "id": <رقم id من القائمة>,
  "category": "launch|research|funding|partnership|product|controversy|policy|benchmark",
  "category_label_ar": "إطلاق|بحث|تمويل|شراكة|منتج|خلاف|سياسة|معيار",
  "company": "اسم الشركة الرئيسية في الخبر",
  "headline": "عنوان عربي قوي (حد أقصى 75 حرف، بدون أقواس أو اقتباسات)",
  "summary": "جملتان واضحتان تشرحان الخبر (حد أقصى 300 حرف)",
  "context": "جملة واحدة: لماذا هذا الخبر الآن؟ (اختياري - اتركها فارغة '' إذا غير مهم)",
  "impact": "جملة واحدة: الأثر العملي على المطور/الشركة (اختياري)",
  "importance": 1-10
}}

القائمة:
{articles}

أرجع JSON array فقط. بدون أي نص قبله أو بعده. بدون markdown."""

VIDEOS_SYSTEM = """أنت منسق محتوى فيديو AI. تختار أفضل الفيديوهات التعليمية والتحليلية العميقة."""

VIDEOS_USER = """اختر أفضل {n} فيديوهات من القائمة.

معايير:
- محتوى تقني عميق أو شرح موضوع مهم
- يضيف قيمة فعلية للمطور/المهتم بـ AI
- استبعد clickbait أو محتوى سطحي

لكل فيديو أرجع JSON بالحقول:
{{
  "id": <id من القائمة>,
  "title_ar": "عنوان مكيّف بالعربي يوصل الفكرة (حد أقصى 80 حرف)",
  "channel": "اسم القناة كما هو",
  "description_ar": "جملتان وصف بالعربي (حد أقصى 240 حرف)",
  "value_prop": "جملة واحدة: ليش هذا الفيديو يستحق المشاهدة",
  "category": "tutorial|analysis|news|research|interview"
}}

القائمة:
{videos}

أرجع JSON array فقط."""

REPORT_SYSTEM = """أنت محلل صناعة الذكاء الاصطناعي. تكتب تقارير يومية احترافية قصيرة بعمق تحليلي."""

REPORT_USER = """اكتب تقريراً يومياً عن أبرز أحداث AI اليوم.

الأخبار المتاحة:
{articles}

أرجع JSON بالشكل التالي:
{{
  "top_stories": [
    {{"rank": 1, "headline": "عنوان مختصر قوي", "summary": "جملتان واضحتان"}},
    {{"rank": 2, "headline": "...", "summary": "..."}},
    {{"rank": 3, "headline": "...", "summary": "..."}}
  ],
  "theme_of_the_day": "موضوع اليوم الأبرز في جملة (مثلاً: 'حرب النماذج المفتوحة' أو 'صعود AI Agents')",
  "reading_between_lines": "فقرة تحليلية 3-4 جمل: ماذا تخبرنا أخبار اليوم مجتمعة؟ ما النمط؟",
  "tomorrow_watch": "جملتان: ماذا نترقب في الأيام القادمة؟"
}}

أرجع JSON فقط، بالعربية الفصحى المهنية."""

# ============================================================
# TELEGRAM FORMATTING
# ============================================================

CATEGORY_EMOJI = {
    "launch": "🚀",
    "research": "🔬",
    "funding": "💰",
    "partnership": "🤝",
    "product": "📱",
    "controversy": "⚠️",
    "policy": "⚖️",
    "benchmark": "📊",
}

def esc(text: Any) -> str:
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

def format_news(item: Dict, url: str, source: str, idx: int, total: int) -> str:
    emoji = CATEGORY_EMOJI.get(item.get("category", ""), "📰")
    label = esc(item.get("category_label_ar", "خبر"))
    company = esc(item.get("company", ""))
    headline = esc(item.get("headline", ""))
    summary = esc(item.get("summary", ""))
    context = esc(item.get("context", "")).strip()
    impact = esc(item.get("impact", "")).strip()

    header = f"{emoji} <b>{label}</b>"
    if company:
        header += f" · {company}"

    lines = [header, "", f"<b>{headline}</b>", "", summary]

    if context:
        lines += ["", f"📌 <b>السياق:</b> {context}"]
    if impact:
        lines += [f"💡 <b>الأثر:</b> {impact}"]

    lines += [
        "",
        f'🔗 <a href="{esc(url)}">{esc(source)}</a>',
        "",
        f"<i>{idx}/{total} · {CHANNEL_HANDLE}</i>",
    ]
    return "\n".join(lines)

def format_video(item: Dict, url: str) -> str:
    title = esc(item.get("title_ar", ""))
    channel = esc(item.get("channel", ""))
    desc = esc(item.get("description_ar", ""))
    value = esc(item.get("value_prop", "")).strip()

    lines = [
        f"🎬 <b>فيديو مختار</b> · {channel}",
        "",
        f"<b>{title}</b>",
        "",
        desc,
    ]
    if value:
        lines += ["", f"💎 <b>ليش يستحق:</b> {value}"]
    lines += [
        "",
        f'▶️ <a href="{esc(url)}">مشاهدة على YouTube</a>',
        "",
        f"<i>{CHANNEL_HANDLE}</i>",
    ]
    return "\n".join(lines)

def format_report(report: Dict, date_str: str) -> str:
    theme = esc(report.get("theme_of_the_day", "")).strip()
    reading = esc(report.get("reading_between_lines", "")).strip()
    watch = esc(report.get("tomorrow_watch", "")).strip()

    lines = [
        f"📊 <b>تقرير اليوم</b> · {date_str}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "<b>أبرز أحداث الذكاء الاصطناعي</b>",
    ]
    if theme:
        lines += ["", f"<i>موضوع اليوم: {theme}</i>"]

    lines.append("")
    rank_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    for story in report.get("top_stories", [])[:5]:
        rank = max(1, min(5, int(story.get("rank", 1))))
        emoji = rank_emojis[rank - 1]
        head = esc(story.get("headline", ""))
        summ = esc(story.get("summary", ""))
        lines += [f"{emoji} <b>{head}</b>", summ, ""]

    if reading:
        lines += [
            "━━━━━━━━━━━━━━━━━━━━━━",
            "",
            "<b>📖 القراءة بين السطور</b>",
            reading,
            "",
        ]
    if watch:
        lines += ["<b>🔭 ماذا نترقب؟</b>", watch, ""]

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"<i>📡 {CHANNEL_HANDLE}</i>",
    ]
    return "\n".join(lines)

# ============================================================
# TELEGRAM SEND
# ============================================================

def send_telegram(message: str, disable_preview: bool = False) -> bool:
    if len(message) > 4050:
        message = message[:4040] + "…"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": disable_preview,
            },
            timeout=30,
        )
        if r.status_code != 200:
            print(f"[telegram] {r.status_code}: {r.text[:250]}")
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
    print(f"\n━━━ [news-cycle] {ts} ━━━")

    cache = load_cache()
    articles = fetch_all_news(hours=4)

    fresh = [a for a in articles if item_hash(a["title"], a["url"]) not in cache]
    print(f"[news] fresh after dedup: {len(fresh)}")
    if len(fresh) < 3:
        print("[news] skip — not enough fresh content")
        return

    # Trim and index for Groq
    pool = fresh[:60]
    compact = [{
        "id": i,
        "title": a["title"][:220],
        "summary": a["summary"][:280],
        "source": a["source"],
    } for i, a in enumerate(pool)]

    raw = call_groq(
        NEWS_SYSTEM,
        NEWS_USER.format(n=6, articles=json.dumps(compact, ensure_ascii=False)),
        temperature=0.35,
        max_tokens=3800,
    )
    curated = extract_json(raw)
    if not curated or not isinstance(curated, list):
        print("[news] curation failed")
        return

    # Sort by importance, cap at 6
    curated = sorted(curated, key=lambda x: x.get("importance", 5), reverse=True)[:6]
    total = len(curated)

    for i, item in enumerate(curated, 1):
        try:
            idx = int(item.get("id", -1))
            if idx < 0 or idx >= len(pool):
                continue
            original = pool[idx]
            url = original["url"]
            source = original["source"]

            message = format_news(item, url, source, i, total)
            if send_telegram(message):
                cache.add(item_hash(original["title"], url))
                time.sleep(4)  # gentle pacing
        except Exception as exc:
            print(f"[news] item {i} error: {exc}")

    save_cache(cache)
    print(f"[news] sent {total} items")

def video_cycle() -> None:
    ts = datetime.now(RIYADH_TZ).strftime("%Y-%m-%d %H:%M")
    print(f"\n━━━ [video-cycle] {ts} ━━━")

    cache = load_cache()
    videos = fetch_youtube_videos(hours=30)
    fresh = [v for v in videos if item_hash(v["title"], v["url"]) not in cache]

    if not fresh:
        print("[videos] no fresh videos")
        return

    pool = fresh[:15]
    compact = [{
        "id": i,
        "title": v["title"][:220],
        "channel": v["channel"],
        "description": v["summary"][:280],
    } for i, v in enumerate(pool)]

    raw = call_groq(
        VIDEOS_SYSTEM,
        VIDEOS_USER.format(n=3, videos=json.dumps(compact, ensure_ascii=False)),
        temperature=0.4,
        max_tokens=2200,
    )
    curated = extract_json(raw)
    if not curated or not isinstance(curated, list):
        print("[videos] curation failed")
        return

    # Header
    send_telegram(
        "🎬 <b>فيديوهات اليوم المختارة</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>{len(curated)} فيديو مختارة بعناية · {CHANNEL_HANDLE}</i>",
        disable_preview=True,
    )
    time.sleep(2)

    for video in curated[:3]:
        try:
            idx = int(video.get("id", -1))
            if idx < 0 or idx >= len(pool):
                continue
            original = pool[idx]
            if send_telegram(format_video(video, original["url"])):
                cache.add(item_hash(original["title"], original["url"]))
                time.sleep(4)
        except Exception as exc:
            print(f"[videos] error: {exc}")

    save_cache(cache)
    print(f"[videos] sent {len(curated)} videos")

def report_cycle() -> None:
    ts = datetime.now(RIYADH_TZ).strftime("%Y-%m-%d %H:%M")
    print(f"\n━━━ [report-cycle] {ts} ━━━")

    articles = fetch_all_news(hours=24)
    if len(articles) < 5:
        print("[report] not enough content")
        return

    compact = [{
        "title": a["title"][:220],
        "summary": a["summary"][:280],
        "source": a["source"],
    } for a in articles[:45]]

    raw = call_groq(
        REPORT_SYSTEM,
        REPORT_USER.format(articles=json.dumps(compact, ensure_ascii=False)),
        temperature=0.5,
        max_tokens=2800,
    )
    report = extract_json(raw)
    if not report or not isinstance(report, dict):
        print("[report] generation failed")
        return

    now = datetime.now(RIYADH_TZ)
    months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
             "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
    date_str = f"{now.day} {months[now.month - 1]} {now.year}"

    message = format_report(report, date_str)
    send_telegram(message, disable_preview=True)
    print("[report] sent")

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

    print("[startup] ✅ كل المتغيرات محمّلة")
    print(f"[startup] مصادر أخبار: {len(NEWS_SOURCES)}")
    print(f"[startup] قنوات YouTube: {len(YOUTUBE_CHANNELS)}")
    print(f"[startup] النموذج: {GROQ_MODEL}")
    print(f"[startup] القناة: {CHANNEL_HANDLE}")
    print(f"[startup] الوقت الحالي (الرياض): {datetime.now(RIYADH_TZ).strftime('%Y-%m-%d %H:%M:%S')}")

def main() -> None:
    startup_check()

    scheduler = BlockingScheduler(timezone=RIYADH_TZ)

    # أخبار كل 4 ساعات — أوقات محددة
    scheduler.add_job(
        news_cycle,
        CronTrigger(hour="8,12,16,20,0,4", minute=0, timezone=RIYADH_TZ),
        id="news",
        max_instances=1,
        coalesce=True,
    )

    # فيديوهات يومياً 2 ظهراً
    scheduler.add_job(
        video_cycle,
        CronTrigger(hour=14, minute=0, timezone=RIYADH_TZ),
        id="videos",
        max_instances=1,
        coalesce=True,
    )

    # تقرير يومي 9 مساءً
    scheduler.add_job(
        report_cycle,
        CronTrigger(hour=21, minute=0, timezone=RIYADH_TZ),
        id="report",
        max_instances=1,
        coalesce=True,
    )

    print("\n[scheduler] المهام المجدولة:")
    print("  📰 الأخبار: 8ص · 12ظ · 4ع · 8م · 12ص · 4ص (الرياض)")
    print("  🎬 الفيديوهات: 2 ظهراً")
    print("  📊 التقرير اليومي: 9 مساءً")

    # تشغيل دورة أخبار فورية عند بدء التشغيل
    print("\n[scheduler] ▶️ تشغيل دورة أخبار فورية...")
    try:
        news_cycle()
    except Exception as exc:
        print(f"[startup-cycle] خطأ: {exc}")

    print("\n[scheduler] ⏰ الجدولة شغالة — في انتظار المواعيد...")
    scheduler.start()


if __name__ == "__main__":
    main()
