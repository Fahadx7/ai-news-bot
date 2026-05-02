"""
groq_client.py — عميل Groq محسّن
يحل مشكلة 413 Payload Too Large عبر:
    1. تقسيم الأخبار على دفعات صغيرة (batching)
    2. تقصير المحتوى (title + summary فقط، لا full body)
    3. multi-model fallback (لو فشل نموذج، يجرّب الثاني)
    4. حساب حجم الـ payload قبل الإرسال
"""

import json
import logging
import re
import time
from typing import Optional

import requests

from config import (
    BATCH_SIZE,
    GROQ_API_KEY,
    GROQ_MODELS,
    MAX_FINAL_NEWS,
    MAX_FINAL_VIDEOS,
    MAX_PAYLOAD_KB,
    MAX_SUMMARY_LEN,
    MAX_TITLE_LEN,
)

log = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


# ═══════════════════════════════════════════════
# تنظيف وتقصير
# ═══════════════════════════════════════════════
def trim_text(text: str, max_len: int) -> str:
    """يقطع النص عند آخر مسافة قبل الحد."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(" ", 1)[0]
    return cut + "…"


def slim_article(article: dict) -> dict:
    """يحوّل خبر كامل إلى نسخة مختصرة للإرسال لـ Groq."""
    return {
        "i": article.get("id") or article.get("url", "")[-12:],  # ID قصير
        "t": trim_text(article.get("title", ""), MAX_TITLE_LEN),
        "s": trim_text(
            article.get("summary") or article.get("description", ""),
            MAX_SUMMARY_LEN,
        ),
        "src": article.get("source", ""),
    }


def slim_video(video: dict) -> dict:
    return {
        "i": video.get("id", ""),
        "t": trim_text(video.get("title", ""), MAX_TITLE_LEN),
        "ch": video.get("channel", ""),
    }


def payload_size_kb(data) -> float:
    return len(json.dumps(data, ensure_ascii=False).encode("utf-8")) / 1024


# ═══════════════════════════════════════════════
# Prompts
# ═══════════════════════════════════════════════
CURATION_SYSTEM = """أنت محرّر أخبار محترف. مهمتك اختيار أهم الأخبار من قائمة.

المعايير بالأولوية:
1. الأهمية الإخبارية (تأثير عالمي/إقليمي)
2. حداثة الخبر
3. صلته بالتقنية والأعمال والذكاء الاصطناعي والشأن السعودي
4. تجنّب التكرار

ترجع JSON فقط بهذا الشكل:
{"selected": ["id1", "id2", ...]}

ما تكتب أي شيء قبل أو بعد الـ JSON. لا backticks. JSON خام."""


SUMMARY_SYSTEM = """أنت محرر أخبار. اكتب ملخصاً عربياً مختصراً للأخبار المختارة.

لكل خبر:
- عنوان جذاب < 80 حرف
- ملخص 2-3 أسطر
- إيموجي مناسب في البداية

ترجع JSON بهذا الشكل:
{
  "items": [
    {"id": "id1", "title": "...", "summary": "...", "emoji": "🚀"},
    ...
  ]
}

JSON خام فقط. لا backticks."""


# ═══════════════════════════════════════════════
# الكلاس الرئيسي
# ═══════════════════════════════════════════════
class GroqClient:
    """عميل Groq ذكي مع batching و fallback."""

    def __init__(self, timeout: int = 30):
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY مطلوب في environment")
        self.timeout = timeout
        self.last_used_model: Optional[str] = None

    # ─────────────────────────────────────────
    # استدعاء واحد لـ Groq مع fallback
    # ─────────────────────────────────────────
    def _call(
        self,
        system: str,
        user: str,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> Optional[str]:
        """يحاول كل النماذج بالترتيب — أول واحد ينجح يرجع نتيجته."""
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }

        for model in GROQ_MODELS:
            body = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            }

            size = payload_size_kb(body)

            try:
                r = requests.post(
                    GROQ_URL, headers=headers, json=body, timeout=self.timeout
                )
                if r.status_code == 200:
                    self.last_used_model = model
                    log.info("[groq] ✅ %s نجح (size=%.1fKB)", model, size)
                    return r.json()["choices"][0]["message"]["content"]
                elif r.status_code == 413:
                    log.warning(
                        "[groq] ❌ %s — 413 Payload Too Large (size=%.1fKB)",
                        model, size,
                    )
                    continue  # جرّب نموذج ثاني (نفس الـ payload لكن بنموذج context أكبر)
                elif r.status_code == 429:
                    log.warning("[groq] ⏸ %s — Rate limited، انتظر 5ث", model)
                    time.sleep(5)
                    continue
                else:
                    log.warning(
                        "[groq] ❌ %s — HTTP %s: %s",
                        model, r.status_code, r.text[:200],
                    )
                    continue
            except requests.exceptions.RequestException as e:
                log.warning("[groq] ❌ %s — Exception: %s", model, e)
                continue

        log.error("[groq] ❌ كل النماذج فشلت")
        return None

    # ─────────────────────────────────────────
    # Curation — اختيار أهم الأخبار
    # ─────────────────────────────────────────
    def curate_news(
        self,
        articles: list[dict],
        max_final: int = MAX_FINAL_NEWS,
    ) -> list[dict]:
        """
        يختار أهم max_final خبر من قائمة كبيرة.
        يقسم الأخبار على دفعات صغيرة (BATCH_SIZE) لتجنب الـ 413.
        """
        if not articles:
            return []

        if len(articles) <= max_final:
            log.info("[curate] %d أخبار أقل من الحد، نرجعهم كلهم", len(articles))
            return articles

        # ابني خريطة id → article كاملة
        slim_articles = [slim_article(a) for a in articles]
        id_to_article = {sa["i"]: a for sa, a in zip(slim_articles, articles)}

        # قسّم على دفعات
        batches = [
            slim_articles[i : i + BATCH_SIZE]
            for i in range(0, len(slim_articles), BATCH_SIZE)
        ]
        log.info(
            "[curate] %d خبر → %d دفعة × %d خبر",
            len(articles), len(batches), BATCH_SIZE,
        )

        # اختر من كل دفعة top-3
        per_batch_keep = max(2, max_final // len(batches) + 1)
        selected_ids: list[str] = []

        for idx, batch in enumerate(batches, 1):
            user_prompt = (
                f"اختر أهم {per_batch_keep} أخبار من هذي القائمة:\n\n"
                f"{json.dumps(batch, ensure_ascii=False)}"
            )

            # تحقق من الحجم
            test_size = payload_size_kb(
                {"system": CURATION_SYSTEM, "user": user_prompt}
            )
            if test_size > MAX_PAYLOAD_KB:
                log.warning(
                    "[curate] دفعة %d/%d حجمها %.1fKB > الحد، نقلصها",
                    idx, len(batches), test_size,
                )
                # قلل الـ summary أكثر
                for item in batch:
                    item["s"] = trim_text(item["s"], 100)
                user_prompt = (
                    f"اختر أهم {per_batch_keep} أخبار:\n\n"
                    f"{json.dumps(batch, ensure_ascii=False)}"
                )

            raw = self._call(
                CURATION_SYSTEM,
                user_prompt,
                max_tokens=400,  # JSON مختصر فقط
            )

            if not raw:
                log.warning("[curate] دفعة %d/%d فشلت — نتخطاها", idx, len(batches))
                continue

            try:
                data = self._parse_json(raw)
                ids = data.get("selected", [])
                if isinstance(ids, list):
                    selected_ids.extend(str(i) for i in ids)
                    log.info(
                        "[curate] دفعة %d/%d ✅ اختار %d",
                        idx, len(batches), len(ids),
                    )
            except Exception as e:
                log.error("[curate] دفعة %d/%d parse error: %s", idx, len(batches), e)

        # رجّع المقالات الكاملة بناءً على الـ IDs
        final = []
        seen = set()
        for sid in selected_ids:
            if sid in id_to_article and sid not in seen:
                final.append(id_to_article[sid])
                seen.add(sid)
                if len(final) >= max_final:
                    break

        # لو ما حصلنا الكفاية، نملأ من البقية
        if len(final) < max_final:
            for a in articles:
                if a not in final:
                    final.append(a)
                    if len(final) >= max_final:
                        break

        log.info("[curate] ✅ النتيجة النهائية: %d خبر", len(final))
        return final

    # ─────────────────────────────────────────
    # Summarize — كتابة ملخصات للأخبار
    # ─────────────────────────────────────────
    def summarize_news(self, articles: list[dict]) -> list[dict]:
        """يضيف عنوان جذاب وملخص مكثف لكل خبر."""
        if not articles:
            return []

        slim = [slim_article(a) for a in articles]
        id_to_article = {sa["i"]: a for sa, a in zip(slim, articles)}

        user_prompt = (
            f"اكتب عناوين وملخصات عربية للأخبار التالية:\n\n"
            f"{json.dumps(slim, ensure_ascii=False)}"
        )

        size = payload_size_kb({"sys": SUMMARY_SYSTEM, "usr": user_prompt})
        if size > MAX_PAYLOAD_KB:
            # قسّمهم
            log.info("[summary] حجم %.1fKB > الحد، نقسم", size)
            half = len(slim) // 2
            return self.summarize_news(articles[:half]) + self.summarize_news(articles[half:])

        raw = self._call(SUMMARY_SYSTEM, user_prompt, max_tokens=1500)
        if not raw:
            log.warning("[summary] فشل — نرجع الأخبار بدون تلخيص")
            return articles

        try:
            data = self._parse_json(raw)
            items = data.get("items", [])
            result = []
            for item in items:
                aid = str(item.get("id", ""))
                if aid in id_to_article:
                    enriched = dict(id_to_article[aid])
                    enriched["title_ar"] = item.get("title", enriched.get("title", ""))
                    enriched["summary_ar"] = item.get("summary", "")
                    enriched["emoji"] = item.get("emoji", "📰")
                    result.append(enriched)
            log.info("[summary] ✅ لخّص %d خبر", len(result))
            return result if result else articles
        except Exception as e:
            log.error("[summary] parse error: %s", e)
            return articles

    # ─────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────
    @staticmethod
    def _parse_json(raw: str) -> dict:
        clean = raw.strip()
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean)
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", clean)
            if match:
                return json.loads(match.group(0))
            raise ValueError(f"رد غير صالح كـ JSON: {raw[:200]}")

    # ─────────────────────────────────────────
    # Health Check
    # ─────────────────────────────────────────
    def health_check(self) -> bool:
        """يفحص أول نموذج في القائمة."""
        log.info("[health] فحص النماذج المتاحة...")
        for model in GROQ_MODELS:
            try:
                r = requests.post(
                    GROQ_URL,
                    headers={
                        "Authorization": f"Bearer {GROQ_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 5,
                    },
                    timeout=10,
                )
                if r.status_code == 200:
                    log.info("[health] ✅ %s يعمل", model)
                    return True
                else:
                    log.warning("[health] ⚠️ %s — HTTP %s", model, r.status_code)
            except Exception as e:
                log.warning("[health] ⚠️ %s — %s", model, e)
        log.error("[health] ❌ كل النماذج فشلت")
        return False
