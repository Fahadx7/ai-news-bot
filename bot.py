import os, json, feedparser, requests
from datetime import datetime, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GROQ_API_KEY     = os.environ.get("GROQ_API_KEY")
NEWS_COUNT       = 7

RSS_FEEDS = [
    # ── الشركات الكبرى ──────────────────────────────
    {"name": "Anthropic",        "url": "https://www.anthropic.com/rss.xml"},
    {"name": "OpenAI",           "url": "https://openai.com/blog/rss.xml"},
    {"name": "Google DeepMind",  "url": "https://deepmind.google/blog/rss.xml"},
    {"name": "Google AI",        "url": "https://blog.google/technology/ai/rss/"},
    {"name": "Meta AI",          "url": "https://ai.meta.com/blog/rss/"},
    {"name": "Microsoft AI",     "url": "https://blogs.microsoft.com/ai/feed/"},
    {"name": "Mistral AI",       "url": "https://mistral.ai/news/rss.xml"},
    {"name": "Hugging Face",     "url": "https://huggingface.co/blog/feed.xml"},

    # ── المواقع التقنية العالمية ─────────────────────
    {"name": "The Verge AI",     "url": "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml"},
    {"name": "TechCrunch AI",    "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"name": "MIT Tech Review",  "url": "https://www.technologyreview.com/feed/"},
    {"name": "VentureBeat AI",   "url": "https://venturebeat.com/ai/feed/"},
    {"name": "Wired AI",         "url": "https://www.wired.com/feed/tag/artificial-intelligence/latest/rss"},
    {"name": "Ars Technica AI",  "url": "https://feeds.arstechnica.com/arstechnica/technology-lab"},
    {"name": "ZDNet AI",         "url": "https://www.zdnet.com/topic/artificial-intelligence/rss.xml"},

    # ── أبحاث ومستجدات علمية ────────────────────────
    {"name": "ArXiv AI",         "url": "https://rss.arxiv.org/rss/cs.AI"},
    {"name": "Papers With Code", "url": "https://paperswithcode.com/latest.rss"},

    # ── مصادر عربية ─────────────────────────────────
    {"name": "عالم التقنية",     "url": "https://www.3alam.net/feed"},
    {"name": "أرابيان بزنس تك",  "url": "https://www.arabianbusiness.com/taxonomy/term/25803/rss.xml"},
    {"name": "مجلة رواد الأعمال","url": "https://rowadalaamal.com/feed/"},
]

HASHTAGS = "#ذكاء_اصطناعي #AI #تقنية #ChatGPT #مستقبل_التقنية"

def fetch_news():
    all_news = []
    cutoff = datetime.now() - timedelta(hours=24)  # آخر 24 ساعة فقط
    for source in RSS_FEEDS:
        try:
            feed = feedparser.parse(source["url"])
            for entry in feed.entries[:3]:
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    if datetime(*entry.published_parsed[:6]) < cutoff:
                        continue
                summary = getattr(entry, "summary", getattr(entry, "description", ""))[:400]
                all_news.append({
                    "title": entry.get("title",""),
                    "summary": summary,
                    "link": entry.get("link",""),
                    "source": source["name"],
                })
        except Exception as e:
            print(f"⚠️ {source['name']}: {e}")
    return all_news

def select_and_translate(news_list):
    news_text = "\n".join(
        f"{i+1}. [{n['source']}] {n['title']}\n{n['summary'][:200]}\n{n['link']}"
        for i, n in enumerate(news_list[:35])
    )
    prompt = f"""اختر {NEWS_COUNT} أخبار الأهم من القائمة وترجمها للعربي.
معايير: منتجات جديدة، إعلانات كبرى، أبحاث مهمة، تأثير على المستخدم العربي.
تجنب الأخبار المكررة أو الأقل أهمية.

{news_text}

رد بـ JSON فقط بدون أي نص آخر:
[{{
  "title_ar": "عنوان جذاب بالعربي",
  "body_ar": "شرح الخبر في 2-3 جمل بالعربي",
  "tweet": "تغريدة عربية جذابة تشرح الخبر في جملة أو جملتين — أقل من 180 حرف — بدون هاشتاقات ورابط",
  "source": "اسم المصدر",
  "link": "رابط الخبر",
  "emoji": "إيموجي مناسب"
}}]"""

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2000,
            "temperature": 0.3,
        }
    )
    text = resp.json()["choices"][0]["message"]["content"].strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"): text = text[4:]
    return json.loads(text.strip())

def tg_send(text, parse_mode="Markdown"):
    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text,
              "parse_mode": parse_mode, "disable_web_page_preview": True}
    )
    if not r.ok: print(f"⚠️ TG: {r.text}")

def run():
    print(f"🚀 {datetime.now()}")
    news = fetch_news()
    print(f"📡 {len(news)} خبر")
    if not news:
        tg_send("⚠️ لا توجد أخبار اليوم")
        return

    selected = select_and_translate(news)
    print(f"✅ {len(selected)} خبر مختار")

    today = datetime.now().strftime("%d/%m/%Y")
    tg_send(f"🤖 *أخبار الذكاء الاصطناعي — {today}*\n{'─'*28}")

    for item in selected:
        tg_send(
            f"{item['emoji']} *{item['title_ar']}*\n\n"
            f"{item['body_ar']}\n\n"
            f"📌 {item['source']}\n"
            f"🔗 [اقرأ المزيد]({item['link']})"
        )
        tweet = f"{item['emoji']} {item['tweet']}\n\n{HASHTAGS}\n\n🔗 {item['link']}"
        tg_send(
            f"──────────────\n"
            f"📋 *انسخ والصق في X:*\n\n"
            f"`{tweet}`"
        )

    print("✅ تم!")

if __name__ == "__main__":
    run()
