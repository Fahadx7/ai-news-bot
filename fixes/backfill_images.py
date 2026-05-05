"""
Backfill og:image for articles that have no image_url.

Usage:
    pip install httpx
    CLOUDFLARE_API_TOKEN=xxx ACCOUNT_ID=yyy DATABASE_ID=zzz python backfill_images.py

Or set the constants below directly.
"""

import os
import re
import time
import httpx

# ── Config ────────────────────────────────────────────────────────────────────
CF_API_TOKEN  = os.getenv("CLOUDFLARE_API_TOKEN", "")
ACCOUNT_ID    = os.getenv("ACCOUNT_ID", "1bc5df038fffdc6706a3423eba2d7718")
DATABASE_ID   = os.getenv("DATABASE_ID", "07c43f84-9f67-4878-9c90-38f334253d8d")
BATCH_LIMIT   = 50     # articles per run (stay under CF rate limits)
REQUEST_DELAY = 0.3    # seconds between HTTP requests
TIMEOUT       = 6      # seconds per request
# ──────────────────────────────────────────────────────────────────────────────

D1_URL = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/d1/database/{DATABASE_ID}/query"
HEADERS = {"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/json"}

SKIP_PATTERNS = [
    "news.google.com",
    "huggingface.co/papers",
]

OG_PATTERNS = [
    re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', re.I),
    re.compile(r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']', re.I),
]


def d1_query(sql: str, params: list = None):
    payload = {"sql": sql}
    if params:
        payload["params"] = params
    r = httpx.post(D1_URL, headers=HEADERS, json=payload, timeout=15)
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        raise RuntimeError(data)
    return data["result"][0]["results"]


def fetch_og_image(url: str) -> str | None:
    if not url or any(p in url for p in SKIP_PATTERNS):
        return None
    try:
        with httpx.stream(
            "GET", url, timeout=TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (compatible; fahadai-news/1.0)"},
            follow_redirects=True,
        ) as r:
            if not r.is_success:
                return None
            html = ""
            for chunk in r.iter_text():
                html += chunk
                if len(html) > 12_000:
                    break
        for pat in OG_PATTERNS:
            m = pat.search(html)
            if m:
                img = m.group(1).strip()
                if img.startswith("http"):
                    return img
    except Exception as e:
        print(f"  ⚠ {e}")
    return None


def main():
    rows = d1_query(
        "SELECT id, url FROM articles WHERE image_url IS NULL AND url NOT LIKE '%news.google.com%' "
        "ORDER BY published_at DESC LIMIT ?",
        [str(BATCH_LIMIT)],
    )
    print(f"Found {len(rows)} articles without images")

    updated = 0
    for row in rows:
        art_id, url = row["id"], row["url"]
        print(f"[{art_id}] {url[:80]}")
        img = fetch_og_image(url)
        if img:
            d1_query("UPDATE articles SET image_url = ? WHERE id = ?", [img, str(art_id)])
            print(f"  ✓ {img[:80]}")
            updated += 1
        else:
            print("  – no og:image")
        time.sleep(REQUEST_DELAY)

    print(f"\nDone: {updated}/{len(rows)} articles updated with real images")


if __name__ == "__main__":
    main()
