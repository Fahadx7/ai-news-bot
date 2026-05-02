"""
main.py — البوت الرئيسي
يجلب الأخبار → ينقّي بـ Groq → يرسل لتيليقرام
"""

import logging
import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import (
    DAILY_REPORT_HOUR,
    GROQ_API_KEY,
    MAX_FINAL_NEWS,
    RIYADH_TZ,
    SCHEDULE_HOURS,
)
from groq_client import GroqClient
from news_fetcher import deduplicate, fetch_all_news
from telegram_sender import format_news_digest, send_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════
# الدورة الرئيسية
# ═══════════════════════════════════════════════
def run_news_cycle(cycle_name: str = "نشرة") -> None:
    """دورة كاملة: جلب → curation → ملخص → تيليقرام."""
    now = datetime.now(RIYADH_TZ)
    log.info("━" * 50)
    log.info("[news-cycle] %s — %s", cycle_name, now.strftime("%Y-%m-%d %H:%M"))
    log.info("━" * 50)

    # 1. جلب
    articles = fetch_all_news()
    if not articles:
        log.warning("لا توجد أخبار للجلب")
        return

    # 2. dedup
    unique = deduplicate(articles)

    # 3. Curation (الإصلاح الرئيسي)
    try:
        groq = GroqClient()
        curated = groq.curate_news(unique, max_final=MAX_FINAL_NEWS)

        # 4. تلخيص بالعربي
        final = groq.summarize_news(curated)
    except Exception as e:
        log.error("فشل في Groq pipeline: %s — نرسل بدون curation", e)
        final = unique[:MAX_FINAL_NEWS]

    # 5. تيليقرام
    if final:
        text = format_news_digest(final, cycle_name)
        send_message(text)
        log.info("✅ اكتملت الدورة — %d خبر", len(final))
    else:
        log.warning("لا توجد أخبار نهائية للنشر")


def run_daily_report() -> None:
    """تقرير يومي شامل في 11م."""
    log.info("━" * 50)
    log.info("[daily-report] تقرير يومي شامل")
    log.info("━" * 50)

    articles = fetch_all_news()
    if not articles:
        return

    unique = deduplicate(articles)
    try:
        groq = GroqClient()
        # في التقرير اليومي ناخذ ضعف العدد العادي
        curated = groq.curate_news(unique, max_final=MAX_FINAL_NEWS * 2)
        final = groq.summarize_news(curated)
    except Exception as e:
        log.error("فشل: %s", e)
        final = unique[: MAX_FINAL_NEWS * 2]

    if final:
        text = format_news_digest(final, "📊 التقرير اليومي الشامل")
        send_message(text)


# ═══════════════════════════════════════════════
# نقطة الدخول
# ═══════════════════════════════════════════════
def main():
    log.info("━" * 50)
    log.info("  AI News Bot v7 — Newsroom Edition")
    log.info("━" * 50)

    # تحقق من المتغيرات
    if not GROQ_API_KEY:
        log.error("❌ GROQ_API_KEY مفقود")
        sys.exit(1)

    log.info("✅ كل المتغيرات محمّلة")

    # Health check
    groq = GroqClient()
    if not groq.health_check():
        log.error("❌ كل نماذج Groq لا تعمل")
        sys.exit(1)

    log.info("📅 المواعيد المجدولة:")
    log.info(
        "   📰 أخبار: %s",
        " · ".join(f"{h}:00" for h in SCHEDULE_HOURS),
    )
    log.info("   📊 تقرير يومي: %d:00", DAILY_REPORT_HOUR)
    log.info("⏰ الوقت الحالي: %s (الرياض)", datetime.now(RIYADH_TZ).strftime("%Y-%m-%d %H:%M"))

    # ركّب الجدول
    scheduler = BlockingScheduler(timezone=RIYADH_TZ)

    # دورات الأخبار
    for hour in SCHEDULE_HOURS:
        scheduler.add_job(
            lambda h=hour: run_news_cycle(f"نشرة {h}:00"),
            CronTrigger(hour=hour, minute=0, timezone=RIYADH_TZ),
            id=f"news_{hour}",
            name=f"نشرة {hour}:00",
        )

    # التقرير اليومي
    scheduler.add_job(
        run_daily_report,
        CronTrigger(hour=DAILY_REPORT_HOUR, minute=0, timezone=RIYADH_TZ),
        id="daily_report",
        name="التقرير اليومي",
    )

    # تشغيل دورة فورية للاختبار
    log.info("\n▶️ تشغيل دورة فورية للاختبار...\n")
    try:
        run_news_cycle("نشرة فورية (اختبار)")
    except Exception as e:
        log.error("فشلت الدورة الفورية: %s", e)

    log.info("\n⏰ الجدولة شغّالة — في انتظار المواعيد...")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("إيقاف البوت...")


if __name__ == "__main__":
    main()
