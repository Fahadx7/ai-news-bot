"""
news_fetcher.py — جالب الأخبار من RSS و Google News
"""

import hashlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote_plus

import requests

try:
    import feedparser
except ImportError:
    feedparser = None

from config import (
    FETCH_TIMEOUT,
    GOOGLE_NEWS_QUERIES,
    PARALLEL_WORKERS,
    RSS_SOURCES,
    SOURCE_RETRIES,
)

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════
# جلب RSS واحد
# ═══════════════════════════════════════════════
def fetch_rss(url: str, lang: str = "ar") -> list[dict]:
    """يجلب feed واحد ويرجع قائمة مقالات."""
    if feedparser is None:
        log.error("feedparser غير مثبّت")
        return []

    for attempt in range(SOURCE_RETRIES + 1):
        try:
            # نستخدم requests للحصول على timeout صحيح
            response = requests.get(
                url,
                timeout=FETCH_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0 (Bot; +https://aboamran2011.com)"},
            )
            if response.status_code != 200:
                if attempt < SOURCE_RETRIES:
                    continue
                return []

            feed = feedparser.parse(response.content)
            articles = []

            for entry in feed.entries[:30]:  # أقصى 30 من كل مصدر
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                if not title or not link:
                    continue

                summary = (
                    entry.get("summary", "")
                    or entry.get("description", "")
                ).strip()

                # تنظيف HTML من الـ summary
                summary = strip_html(summary)

                article = {
                    "id": hashlib.md5(link.encode()).hexdigest()[:12],
                    "title": title,
                    "summary": summary,
                    "url": link,
                    "source": feed.feed.get("title", url),
                    "lang": lang,
                    "published": entry.get("published", ""),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
                articles.append(article)

            return articles
        except Exception as e:
            if attempt >= SOURCE_RETRIES:
                log.debug("[fetch-rss] فشل %s: %s", url, e)
                return []
            time.sleep(1)
    return []


# ═══════════════════════════════════════════════
# تنظيف HTML
# ═══════════════════════════════════════════════
import re

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


# ═══════════════════════════════════════════════
# Google News
# ═══════════════════════════════════════════════
def google_news_url(query: str, lang: str = "ar") -> str:
    """يبني رابط Google News RSS لاستعلام."""
    hl = lang
    gl = "SA" if lang == "ar" else "US"
    return (
        f"https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl={hl}&gl={gl}&ceid={gl}:{hl}"
    )


# ═══════════════════════════════════════════════
# الجلب المتوازي الكامل
# ═══════════════════════════════════════════════
def fetch_all_news(
    rss_sources: dict = None,
    google_queries: list = None,
) -> list[dict]:
    """يجلب من كل المصادر بالتوازي."""
    rss_sources = rss_sources or RSS_SOURCES
    google_queries = google_queries or GOOGLE_NEWS_QUERIES

    # ابني قائمة كل الـ URLs
    tasks = []
    for lang, urls in rss_sources.items():
        for url in urls:
            tasks.append((url, lang))

    # أضف Google News queries
    for query in google_queries:
        # استعلم بالعربية والإنجليزية
        tasks.append((google_news_url(query, "ar"), "ar"))
        if len(query) > 3:  # كل استعلام بأكثر من 3 أحرف، استعلم بالإنجليزية كمان
            tasks.append((google_news_url(query, "en"), "en"))

    log.info("[fetch] جلب من %d مصدر بالتوازي...", len(tasks))
    start = time.time()

    all_articles = []
    success_count = 0
    fail_count = 0

    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        future_to_url = {
            executor.submit(fetch_rss, url, lang): (url, lang)
            for url, lang in tasks
        }
        for future in as_completed(future_to_url):
            url, lang = future_to_url[future]
            try:
                articles = future.result()
                if articles:
                    all_articles.extend(articles)
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                log.debug("[fetch] %s exception: %s", url, e)
                fail_count += 1

    elapsed = time.time() - start
    log.info(
        "[fetch] ✅ %d مصدر · ❌ %d فارغ · 📰 %d مقال (%.1fس)",
        success_count, fail_count, len(all_articles), elapsed,
    )

    return all_articles


# ═══════════════════════════════════════════════
# إزالة التكرار
# ═══════════════════════════════════════════════
def deduplicate(articles: list[dict]) -> list[dict]:
    """يحذف الأخبار المكررة بناءً على الـ URL والعنوان."""
    seen_urls = set()
    seen_titles = set()
    unique = []

    for a in articles:
        url = a.get("url", "")
        title = (a.get("title", "") or "").strip().lower()
        # signature بناءً على أول 50 حرف من العنوان
        title_sig = title[:50]

        if url in seen_urls or title_sig in seen_titles:
            continue

        seen_urls.add(url)
        if title_sig:
            seen_titles.add(title_sig)
        unique.append(a)

    log.info("[dedup] %d → %d فريد", len(articles), len(unique))
    return unique


# ═══════════════════════════════════════════════
# واجهة موحدة (للربط مع scheduler)
# ═══════════════════════════════════════════════
def fetch_top_arabic_news(limit: int = 1) -> list[dict]:
    """
    واجهة موحدة لباقي المشاريع — يجلب وينقّي ويرجع أهم الأخبار.
    تتوافق مع احتياج fahad-news-ai/scheduler.py
    """
    from groq_client import GroqClient

    raw = fetch_all_news()
    unique = deduplicate(raw)

    # طبّق curation فقط لو في GROQ_API_KEY
    try:
        groq = GroqClient()
        curated = groq.curate_news(unique, max_final=max(limit, 5))
        summarized = groq.summarize_news(curated[:limit])

        # حول للشكل المتوقع لـ fahad-news-ai
        return [
            {
                "title": a.get("title_ar") or a["title"],
                "content": a.get("summary_ar") or a.get("summary", ""),
                "source": a.get("source", ""),
                "url": a.get("url", ""),
            }
            for a in summarized
        ]
    except Exception as e:
        log.error("[fetch_top_arabic] فشل curation: %s — رجوع أول %d", e, limit)
        return [
            {
                "title": a["title"],
                "content": a.get("summary", ""),
                "source": a.get("source", ""),
                "url": a.get("url", ""),
            }
            for a in unique[:limit]
        ]
