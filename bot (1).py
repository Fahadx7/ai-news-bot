import os, json, feedparser, requests, random
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import time
import tweepy

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Credentials ──────────────────────────────────────────
TELEGRAM_TOKEN          = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID        = os.environ.get("TELEGRAM_CHAT_ID")
GROQ_API_KEY            = os.environ.get("GROQ_API_KEY")
TWITTER_CONSUMER_KEY    = os.environ.get("TWITTER_CONSUMER_KEY")
TWITTER_CONSUMER_SECRET = os.environ.get("TWITTER_CONSUMER_SECRET")
TWITTER_ACCESS_TOKEN    = os.environ.get("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET   = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")

NEWS_COUNT    = 5   # أخبار عادية
THREAD_COUNT  = 1   # خبر واحد يتحول لـ thread
MAX_TWEET_LEN = 270

# ── مصادر متنوعة (33 مصدر) ────────────────────────────
RSS_FEEDS = [
    # الشركات الكبرى
    {"name": "Anthropic",          "url": "https://www.anthropic.com/rss.xml",                            "type": "company"},
    {"name": "OpenAI",             "url": "https://openai.com/blog/rss.xml",                              "type": "company"},
    {"name": "Google DeepMind",    "url": "https://deepmind.google/blog/rss.xml",                         "type": "company"},
    {"name": "Google AI",          "url": "https://blog.google/technology/ai/rss/",                       "type": "company"},
    {"name": "Meta AI",            "url": "https://ai.meta.com/blog/rss/",                                "type": "company"},
    {"name": "Microsoft AI",       "url": "https://blogs.microsoft.com/ai/feed/",                         "type": "company"},
    {"name": "Mistral AI",         "url": "https://mistral.ai/news/rss.xml",                              "type": "company"},
    {"name": "Hugging Face",       "url": "https://huggingface.co/blog/feed.xml",                         "type": "research"},
    {"name": "Cohere",             "url": "https://cohere.com/blog/rss",                                  "type": "company"},
    # مواقع عالمية
    {"name": "The Verge AI",       "url": "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml","type": "media"},
    {"name": "TechCrunch AI",      "url": "https://techcrunch.com/category/artificial-intelligence/feed/",    "type": "media"},
    {"name": "MIT Tech Review",    "url": "https://www.technologyreview.com/feed/",                           "type": "media"},
    {"name": "VentureBeat AI",     "url": "https://venturebeat.com/ai/feed/",                                 "type": "media"},
    {"name": "Wired AI",           "url": "https://www.wired.com/feed/tag/artificial-intelligence/latest/rss","type": "media"},
    {"name": "Ars Technica",       "url": "https://feeds.arstechnica.com/arstechnica/technology-lab",         "type": "media"},
    {"name": "ZDNet AI",           "url": "https://www.zdnet.com/topic/artificial-intelligence/rss.xml",      "type": "media"},
    {"name": "IEEE Spectrum AI",   "url": "https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss","type": "media"},
    # أبحاث
    {"name": "ArXiv AI",           "url": "https://rss.arxiv.org/rss/cs.AI",          "type": "research"},
    {"name": "ArXiv LLM",          "url": "https://rss.arxiv.org/rss/cs.CL",          "type": "research"},
    {"name": "Papers With Code",   "url": "https://paperswithcode.com/latest.rss",     "type": "research"},
    # مصادر عربية متنوعة
    {"name": "عالم التقنية",           "url": "https://www.3alam.net/feed",                               "type": "arabic"},
    {"name": "أرابيان بزنس تك",        "url": "https://www.arabianbusiness.com/taxonomy/term/25803/rss.xml","type": "arabic"},
    {"name": "مجلة رواد الأعمال",      "url": "https://rowadalaamal.com/feed/",                           "type": "arabic"},
    {"name": "Forbes Middle East",     "url": "https://www.forbesmiddleeast.com/feed",                    "type": "arabic"},
    {"name": "Gulf Business Tech",     "url": "https://gulfbusiness.com/category/technology/feed/",       "type": "arabic"},
    {"name": "Wamda",                  "url": "https://www.wamda.com/feed",                               "type": "arabic"},
    {"name": "Arab News Tech",         "url": "https://www.arabnews.com/taxonomy/term/17936/rss.xml",     "type": "arabic"},
    {"name": "Saudi Gazette Tech",     "url": "https://saudigazette.com.sa/rss/technology.xml",           "type": "arabic"},
    # مدونات AI متخصصة
    {"name": "The Batch DL.AI",    "url": "https://www.deeplearning.ai/the-batch/rss/", "type": "ai_blog"},
    {"name": "Last Week in AI",    "url": "https://lastweekin.ai/feed",                  "type": "ai_blog"},
    {"name": "AI Business",        "url": "https://aibusiness.com/rss.xml",              "type": "ai_blog"},
    {"name": "Towards AI",         "url": "https://pub.towardsai.net/feed",              "type": "ai_blog"},
    {"name": "Import AI",          "url": "https://importai.substack.com/feed",          "type": "ai_blog"},
]

# هاشتاقات متنوعة — تتغير كل دورة
HASHTAG_POOLS = [
    "#ذكاء_اصطناعي #AI #تقنية",
    "#ChatGPT #مستقبل_التقنية #تكنولوجيا",
    "#تقنية_سعودية #AI #رؤية2030",
    "#ذكاء_اصطناعي #OpenAI #تقنية",
    "#MachineLearning #ذكاء_اصطناعي #ابتكار",
    "#LLM #تقنية #مستقبل",
    "#تقنية #AI #ريادة_أعمال",
    "#ذكاء_اصطناعي #تعلم_آلي #مستقبل_التقنية",
    "#رؤية2030 #تقنية_سعودية #ذكاء_اصطناعي",
    "#GenAI #ذكاء_اصطناعي #تقنية",
]

# روابط YouTube حسب الشركة
YOUTUBE_REFS = {
    "openai":     "https://youtube.com/@OpenAI",
    "google":     "https://youtube.com/@Google",
    "anthropic":  "https://youtube.com/@AnthropicAI",
    "meta":       "https://youtube.com/@MetaAI",
    "microsoft":  "https://youtube.com/@Microsoft",
    "deepmind":   "https://youtube.com/@GoogleDeepMind",
    "default":    "https://youtube.com/@TwoMinutePapers",
}

# ────────────────────────────────────────────────────────

def fetch_news():
    all_news = []
    cutoff = datetime.now() - timedelta(hours=4)
    for source in RSS_FEEDS:
        try:
            feed = feedparser.parse(source["url"])
            for entry in feed.entries[:3]:
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub = datetime(*entry.published_parsed[:6])
                    if pub < cutoff:
                        continue
                summary = getattr(entry, "summary", getattr(entry, "description", ""))[:400]
                all_news.append({
                    "title":   entry.get("title", ""),
                    "summary": summary,
                    "link":    entry.get("link", ""),
                    "source":  source["name"],
                    "type":    source.get("type", "media"),
                })
        except Exception as e:
            print(f"⚠️ {source['name']}: {e}")
    print(f"📡 جُلب {len(all_news)} خبر من {len(RSS_FEEDS)} مصدر")
    return all_news


def groq_call(prompt, max_tokens=3000):
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.4,
        }
    )
    text = resp.json()["choices"][0]["message"]["content"].strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def select_news(news_list):
    news_text = "\n".join(
        f"{i+1}. [{n['source']}|{n['type']}] {n['title']}\n{n['summary'][:200]}\n{n['link']}"
        for i, n in enumerate(news_list[:50])
    )
    prompt = f"""أنت محرر أخبار ذكاء اصطناعي سعودي محترف.

اختر {NEWS_COUNT + THREAD_COUNT} خبر من القائمة:
- {NEWS_COUNT} خبر عادي (news)
- {THREAD_COUNT} خبر مهم للـ thread — يكون خبر حقيقي واضح وليس بحث أكاديمي

قواعد الاختيار الصارمة:
✅ أولوية قصوى: إعلانات منتجات جديدة، تحديثات ChatGPT/Gemini/Claude، صفقات شركات، إطلاقات
✅ ثانياً: أخبار تأثير على الناس العاديين (تطبيقات، أدوات، تغييرات في الخدمات)
✅ ثالثاً: أبحاث لها تطبيق عملي واضح وفوري
❌ تجنب: أبحاث أكاديمية جافة بدون تطبيق (ArXiv مجرد نظريات)
❌ تجنب: أخبار قديمة أو مكررة
❌ لا خبرين من نفس الشركة
❌ لا تختار خبر النوع thread إذا كان بحث أكاديمي — اختر خبر شركة أو منتج

{news_text}

رد بـ JSON فقط بدون أي نص آخر:
[{{
  "title_ar": "عنوان جذاب باللهجة السعودية — مباشر وواضح",
  "body_ar": "شرح الخبر في 2-3 جمل بالعربي — ايش الجديد وليش يهم",
  "tweet_main": "تغريدة باللهجة السعودية — خبر مباشر جذاب — أقل من 220 حرف — بدون هاشتاقات",
  "source": "اسم المصدر",
  "source_key": "openai أو google أو anthropic أو meta أو microsoft أو deepmind أو default",
  "link": "رابط الخبر",
  "emoji": "إيموجي مناسب",
  "content_type": "news أو thread"
}}]

الخبر الأخير (thread) يكون خبر شركة أو منتج مهم — ليس بحث أكاديمي."""

    return groq_call(prompt)


def build_thread_parts(item):
    prompt = f"""أنت صانع محتوى تقني سعودي محترف.

الخبر: {item['title_ar']}
التفاصيل: {item['body_ar']}
المصدر: {item['source']}

اكتب thread تويتر مقنع باللهجة السعودية — 4 تغريدات:
🧵 1: سؤال أو موقف جذاب يشد القارئ
📰 2: ايش صار بالتحديد؟
💡 3: ليش يهمك؟ ايش الفايدة العملية؟
🔮 4: توقعك الشخصي أو سؤال للتفاعل

كل تغريدة أقل من 230 حرف. لا هاشتاقات.

رد بـ JSON فقط — مصفوفة من 4 نصوص:
["التغريدة 1", "التغريدة 2", "التغريدة 3", "التغريدة 4"]"""

    try:
        return groq_call(prompt)
    except Exception as e:
        print(f"⚠️ Thread build error: {e}")
        return [item["tweet_main"]]


def tg_send(text, parse_mode="Markdown"):
    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text,
              "parse_mode": parse_mode, "disable_web_page_preview": True}
    )
    if not r.ok:
        print(f"⚠️ TG: {r.text[:120]}")


def post_tweet(text):
    try:
        client = tweepy.Client(
            consumer_key=TWITTER_CONSUMER_KEY,
            consumer_secret=TWITTER_CONSUMER_SECRET,
            access_token=TWITTER_ACCESS_TOKEN,
            access_token_secret=TWITTER_ACCESS_SECRET
        )
        resp = client.create_tweet(text=text[:280])
        tweet_id = resp.data["id"]
        print(f"✅ X: {text[:70]}...")
        return tweet_id
    except Exception as e:
        print(f"⚠️ X Error: {e}")
        return None


def post_thread(parts, hashtags, link, youtube_url=None):
    try:
        client = tweepy.Client(
            consumer_key=TWITTER_CONSUMER_KEY,
            consumer_secret=TWITTER_CONSUMER_SECRET,
            access_token=TWITTER_ACCESS_TOKEN,
            access_token_secret=TWITTER_ACCESS_SECRET
        )
        total   = len(parts)
        last_id = None

        for i, part in enumerate(parts):
            num = f"{i+1}/{total}"
            if i == total - 1:
                suffix = f"\n\n{hashtags}\n🔗 {link}"
                if youtube_url:
                    suffix += f"\n📺 {youtube_url}"
                tweet_text = f"{num} {part}{suffix}"
            else:
                tweet_text = f"{num} {part}"

            tweet_text = tweet_text[:280]
            if last_id:
                resp = client.create_tweet(text=tweet_text, in_reply_to_tweet_id=last_id)
            else:
                resp = client.create_tweet(text=tweet_text)

            last_id = resp.data["id"]
            print(f"✅ Thread {num}")
            time.sleep(2)

        return last_id
    except Exception as e:
        print(f"⚠️ Thread Error: {e}")
        return None


def run():
    print(f"\n{'='*45}")
    print(f"🚀 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*45}")

    news = fetch_news()
    if not news:
        tg_send("⚠️ ما لقيت أخبار جديدة في آخر 4 ساعات")
        return

    try:
        selected = select_news(news)
    except Exception as e:
        print(f"⚠️ Groq Error: {e}")
        tg_send(f"⚠️ خطأ في معالجة الأخبار: {str(e)[:100]}")
        return

    print(f"✅ {len(selected)} خبر مختار")

    now_str = datetime.now().strftime("%d/%m/%Y — %H:%M")
    tg_send(f"🤖 *أخبار الذكاء الاصطناعي*\n📅 {now_str}\n{'─'*30}")

    for idx, item in enumerate(selected):
        is_thread = item.get("content_type") == "thread"
        hashtags  = random.choice(HASHTAG_POOLS)
        src_key   = item.get("source_key", "default").lower()
        youtube   = YOUTUBE_REFS.get(src_key, YOUTUBE_REFS["default"])

        # ── Telegram: بطاقة الخبر ──────────────────
        tg_msg = (
            f"{item['emoji']} *{item['title_ar']}*\n\n"
            f"{item['body_ar']}\n\n"
            f"📌 {item['source']}\n"
            f"🔗 [اقرأ المزيد]({item['link']})"
        )
        tg_send(tg_msg)

        # ── X + معاينة ─────────────────────────────
        if is_thread:
            parts = build_thread_parts(item)
            post_thread(parts, hashtags, item["link"], youtube)

            # التغريدة الأساسية
            main_preview = f"{item['emoji']} {parts[0]}"
            tg_send(
                f"{'─'*28}\n"
                f"🐦 *التغريدة الأساسية:*\n\n"
                f"`{main_preview[:250]}`"
            )
            # التغريدات الإضافية
            if len(parts) > 1:
                extras = "\n\n".join(
                    f"➕ *إضافية {i+1}:*\n`{p[:200]}`"
                    for i, p in enumerate(parts[1:])
                )
                tg_send(extras)
        else:
            tweet = f"{item['emoji']} {item['tweet_main']}\n\n{hashtags}\n\n🔗 {item['link']}"
            post_tweet(tweet[:280])

            # التغريدة الأساسية فقط
            tg_send(
                f"{'─'*28}\n"
                f"🐦 *التغريدة الأساسية:*\n\n"
                f"`{tweet[:280]}`"
            )

        time.sleep(3)

    print("✅ الدورة اكتملت!")
    tg_send(f"✅ *انتهت دورة {datetime.now().strftime('%H:%M')} — {len(selected)} خبر*")


if __name__ == "__main__":
    print("🤖 AI News Bot v2 — Saudi Edition")
    print(f"📡 {len(RSS_FEEDS)} مصدر | ⏰ كل 4 ساعات\n")
    run()
    scheduler = BackgroundScheduler()
    scheduler.add_job(run, "interval", hours=4)
    scheduler.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        scheduler.shutdown()
        print("\n✋ تم إيقاف البوت")
