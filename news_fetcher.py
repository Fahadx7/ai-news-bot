"""
news_fetcher.py v8
الجديد:
    - تصنيف تلقائي للأخبار السعودية (is_saudi flag)
    - smart_prefilter لتقليل الدفعات قبل Groq
    - دعم متعدد الفئات (saudi, ar, tech, ai, finance)
"""

import hashlib
import logging
import re
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
    PREFILTER_MAX,
    RSS_SOURCES,
    SOURCE_RETRIES,
    is_saudi_news,
)

log = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(text: str) -> str:
    if not text:
        return ""
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", text)).strip()


# ═══════════════════════════════════════════════
# جلب RSS
# ═══════════════════════════════════════════════
def fetch_rss(url: str, category: str = "ar") -> list[dict]:
    if feedparser is None:
        return []

    for attempt in range(SOURCE_RETRIES + 1):
        try:
            response = requests.get(
                url,
                timeout=FETCH_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0 (NewsBot)"},
            )
            if response.status_code != 200:
                if attempt < SOURCE_RETRIES:
                    continue
                return []

            feed = feedparser.parse(response.content)
            articles = []

            for entry in feed.entries[:25]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                if not title or not link:
                    continue

                summary = strip_html(
                    entry.get("summary", "") or entry.get("description", "")
                )

                article = {
                    "id": hashlib.md5(link.encode()).hexdigest()[:12],
                    "title": title,
                    "summary": summary,
                    "url": link,
                    "source": feed.feed.get("title", url),
                    "category": category,
                    "published": entry.get("published", ""),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }

                # تصنيف سعودي تلقائي
                article["is_saudi"] = (
                    category == "saudi" or is_saudi_news(article)
                )

                articles.append(article)

            return articles
        except Exception:
            if attempt >= SOURCE_RETRIES:
                return []
            time.sleep(1)
    return []


def google_news_url(query: str, lang: str = "ar") -> str:
    hl = lang
    gl = "SA" if lang == "ar" else "US"
    return (
        f"https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl={hl}&gl={gl}&ceid={gl}:{hl}"
    )


# ═══════════════════════════════════════════════
# الجلب الكامل
# ═══════════════════════════════════════════════
def fetch_all_news(
    rss_sources: dict = None,
    google_queries: dict = None,
) -> list[dict]:
    rss_sources = rss_sources or RSS_SOURCES
    google_queries = google_queries or GOOGLE_NEWS_QUERIES

    tasks = []
    for category, urls in rss_sources.items():
        for url in urls:
            tasks.append((url, category))

    # Google News بفئاتها
    for category, queries in google_queries.items():
        for q in queries:
            lang = "ar" if category == "saudi" else "ar"
            tasks.append((google_news_url(q, lang), category))

    log.info("[fetch] جلب من %d مصدر بالتوازي...", len(tasks))
    start = time.time()

    all_articles = []
    success = 0
    fail = 0

    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        futures = {
            executor.submit(fetch_rss, url, cat): (url, cat)
            for url, cat in tasks
        }
        for future in as_completed(futures):
            try:
                articles = future.result()
                if articles:
                    all_articles.extend(articles)
                    success += 1
                else:
                    fail += 1
            except Exception:
                fail += 1

    elapsed = time.time() - start
    saudi_count = sum(1 for a in all_articles if a.get("is_saudi"))
    log.info(
        "[fetch] ✅ %d مصدر · ❌ %d فارغ · 📰 %d مقال (🇸🇦 %d سعودي) (%.1fس)",
        success, fail, len(all_articles), saudi_count, elapsed,
    )

    return all_articles


# ═══════════════════════════════════════════════
# Dedup
# ═══════════════════════════════════════════════
def deduplicate(articles: list[dict]) -> list[dict]:
    seen_urls = set()
    seen_titles = set()
    unique = []

    for a in articles:
        url = a.get("url", "")
        title = (a.get("title", "") or "").strip().lower()
        title_sig = title[:50]

        if url in seen_urls or (title_sig and title_sig in seen_titles):
            continue

        seen_urls.add(url)
        if title_sig:
            seen_titles.add(title_sig)
        unique.append(a)

    log.info("[dedup] %d → %d فريد", len(articles), len(unique))
    return unique


# ═══════════════════════════════════════════════
# Smart Prefilter (الجديد!)
# ═══════════════════════════════════════════════
def smart_prefilter(
    articles: list[dict],
    max_count: int = PREFILTER_MAX,
    saudi_quota: int = 30,
) -> list[dict]:
    """
    يقلّص قائمة الأخبار قبل Groq:
    - يحجز quota للأخبار السعودية أولاً
    - يوازن المصادر (لا أكثر من 5 من نفس المصدر)
    - يتجاهل العناوين القصيرة
    """
    # تنظيف
    filtered = [a for a in articles if len(a.get("title", "")) >= 20]

    # افصل سعودي عن باقي
    saudi = [a for a in filtered if a.get("is_saudi") or is_saudi_news(a)]
    other = [a for a in filtered if not (a.get("is_saudi") or is_saudi_news(a))]

    # وازن المصادر داخل كل مجموعة
    def balance_sources(items: list[dict], max_per_src: int = 5) -> list[dict]:
        counts = {}
        result = []
        for a in items:
            src = a.get("source", "?")
            if counts.get(src, 0) >= max_per_src:
                continue
            counts[src] = counts.get(src, 0) + 1
            result.append(a)
        return result

    saudi_balanced = balance_sources(saudi)[:saudi_quota]
    other_quota = max_count - len(saudi_balanced)
    other_balanced = balance_sources(other)[:other_quota]

    result = saudi_balanced + other_balanced
    log.info(
        "[prefilter] %d → %d خبر (🇸🇦 %d + 🌍 %d)",
        len(articles), len(result), len(saudi_balanced), len(other_balanced),
    )
    return result


# ═══════════════════════════════════════════════
# واجهة موحدة لـ fahad-news-ai
# ═══════════════════════════════════════════════
def fetch_top_arabic_news(limit: int = 1) -> list[dict]:
    """واجهة لباقي المشاريع."""
    from groq_client import GroqClient

    raw = fetch_all_news()
    unique = deduplicate(raw)
    prefiltered = smart_prefilter(unique, max_count=60)

    try:
        groq = GroqClient()
        curated = groq.curate_news(prefiltered, max_final=max(limit, 5))
        rewritten = groq.rewrite_news(curated[:limit])

        return [
            {
                "title": a.get("title_ar") or a["title"],
                "content": a.get("summary_ar") or a.get("summary", ""),
                "source": a.get("source", ""),
                "url": a.get("url", ""),
            }
            for a in rewritten
        ]
    except Exception as e:
        log.error("[fetch_top] فشل: %s", e)
        return [
            {
                "title": a["title"],
                "content": a.get("summary", ""),
                "source": a.get("source", ""),
                "url": a.get("url", ""),
            }
            for a in unique[:limit]
        ]
