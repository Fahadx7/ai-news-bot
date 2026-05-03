"""
main.py v8 — البوت الرئيسي
الجديد:
    - دورات الأخبار + Telegram Bot Listener
    - أوامر فورية: /picks /saudi /tech /help
    - كل خبر مع نسخة Twitter-ready + زر مشاركة
    - تصنيف سعودي ذكي
"""

import logging
import sys
import time
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import (
    DAILY_REPORT_HOUR,
    GROQ_API_KEY,
    MAX_FINAL_NEWS,
    PREFILTER_MAX,
    RIYADH_TZ,
    SCHEDULE_HOURS,
    TELEGRAM_BOT_TOKEN,
)
from groq_client import GroqClient
from news_fetcher import deduplicate, fetch_all_news, smart_prefilter
from telegram_bot import start_bot_in_background, update_news_cache
from telegram_sender import send_message, send_news_digest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════
# دورة أخبار كاملة
# ═══════════════════════════════════════════════
def run_news_cycle(cycle_name: str = "نشرة") -> None:
    now = datetime.now(RIYADH_TZ)
    log.info("━" * 50)
    log.info("[news-cycle] %s — %s", cycle_name, now.strftime("%Y-%m-%d %H:%M"))
    log.info("━" * 50)

    # 1. جلب
    articles = fetch_all_news()
    if not articles:
        log.warning("لا توجد أخبار")
        return

    # 2. dedup
    unique = deduplicate(articles)

    # 3. prefilter ذكي
    prefiltered = smart_prefilter(unique, max_count=PREFILTER_MAX)

    # حدّث cache للبوت (للأوامر السريعة)
    update_news_cache(prefiltered)

    # 4. Curation
    try:
        groq = GroqClient()
        curated = groq.curate_news(prefiltered, max_final=MAX_FINAL_NEWS, prefer_saudi=True)

        # 5. Rewrite — صياغة احترافية + Twitter-ready
        log.info("[rewrite] جاري صياغة %d خبر...", len(curated))
        final = groq.rewrite_news(curated)
    except Exception as e:
        log.error("Groq pipeline فشل: %s", e)
        final = prefiltered[:MAX_FINAL_NEWS]

    # 6. تيليقرام
    if final:
        sent = send_news_digest(final, cycle_name=cycle_name, show_twitter_versions=True)
        log.info("✅ اكتملت الدورة — %d خبر مرسل", sent)
    else:
        log.warning("لا توجد أخبار نهائية")


def run_daily_report() -> None:
    log.info("━" * 50)
    log.info("[daily-report] التقرير اليومي الشامل")
    log.info("━" * 50)

    articles = fetch_all_news()
    if not articles:
        return

    unique = deduplicate(articles)
    prefiltered = smart_prefilter(unique, max_count=120)
    update_news_cache(prefiltered)

    try:
        groq = GroqClient()
        curated = groq.curate_news(prefiltered, max_final=MAX_FINAL_NEWS * 2)
        final = groq.rewrite_news(curated)
    except Exception as e:
        log.error("فشل: %s", e)
        final = prefiltered[: MAX_FINAL_NEWS * 2]

    if final:
        send_news_digest(
            final,
            cycle_name="📊 التقرير اليومي الشامل",
            show_twitter_versions=True,
        )


# ═══════════════════════════════════════════════
# نقطة الدخول
# ═══════════════════════════════════════════════
def main():
    log.info("━" * 50)
    log.info("  AI News Bot v8 — Saudi-First + Twitter-Ready")
    log.info("━" * 50)

    if not GROQ_API_KEY:
        log.error("❌ GROQ_API_KEY مفقود")
        sys.exit(1)
    if not TELEGRAM_BOT_TOKEN:
        log.error("❌ TELEGRAM_BOT_TOKEN مفقود")
        sys.exit(1)

    log.info("✅ كل المتغيرات محمّلة")

    # Health check
    groq = GroqClient()
    if not groq.health_check():
        log.error("❌ كل نماذج Groq لا تعمل")
        sys.exit(1)

    log.info("📅 المواعيد المجدولة:")
    log.info("   📰 أخبار: %s", " · ".join(f"{h}:00" for h in SCHEDULE_HOURS))
    log.info("   📊 تقرير يومي: %d:00", DAILY_REPORT_HOUR)
    log.info("⏰ الوقت الحالي: %s (الرياض)",
             datetime.now(RIYADH_TZ).strftime("%Y-%m-%d %H:%M"))

    # رسالة بدء
    send_message(
        "🚀 <b>AI News Bot v8 بدأ التشغيل</b>\n\n"
        "✨ الميزات الجديدة:\n"
        "🇸🇦 تيوب سعودي مخصص\n"
        "🐦 نسخة Twitter-ready لكل خبر\n"
        "⚡ أوامر فورية: /picks /saudi /tech\n\n"
        "اكتب /help للتفاصيل."
    )

    # ابدأ Telegram Bot Listener في thread خلفي
    start_bot_in_background()

    # ابدأ Scheduler
    scheduler = BackgroundScheduler(timezone=RIYADH_TZ)

    for hour in SCHEDULE_HOURS:
        scheduler.add_job(
            lambda h=hour: run_news_cycle(f"نشرة {h}:00"),
            CronTrigger(hour=hour, minute=0, timezone=RIYADH_TZ),
            id=f"news_{hour}",
            name=f"نشرة {hour}:00",
        )

    scheduler.add_job(
        run_daily_report,
        CronTrigger(hour=DAILY_REPORT_HOUR, minute=0, timezone=RIYADH_TZ),
        id="daily_report",
        name="التقرير اليومي",
    )

    scheduler.start()

    # دورة فورية للاختبار
    log.info("\n▶️ تشغيل دورة فورية للاختبار...\n")
    try:
        run_news_cycle("نشرة فورية (اختبار)")
    except Exception as e:
        log.error("فشلت الدورة الفورية: %s", e)

    log.info("\n⏰ كل شيء شغّال — البوت في انتظار الأوامر والمواعيد...")

    # حافظ على البرنامج شغّالاً
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        log.info("إيقاف البوت...")
        scheduler.shutdown()


if __name__ == "__main__":
    main()
