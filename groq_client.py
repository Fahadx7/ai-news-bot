"""
groq_client.py v8 — عميل Groq محسّن
الجديد:
    1. صياغة احترافية بنبرة سعودية (مو ترجمة حرفية)
    2. توليد نسخة Twitter-ready لكل خبر (≤ 280 حرف)
    3. تصنيف ذكي للأخبار السعودية
    4. كل ما سبق + multi-model fallback + batching
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
    MAX_PAYLOAD_KB,
    MAX_SUMMARY_LEN,
    MAX_TITLE_LEN,
    is_saudi_news,
)

log = logging.getLogger(__name__)
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


# ═══════════════════════════════════════════════
# أدوات
# ═══════════════════════════════════════════════
def trim_text(text: str, max_len: int) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(" ", 1)[0]
    return cut + "…"


def slim_article(article: dict) -> dict:
    return {
        "i": article.get("id") or article.get("url", "")[-12:],
        "t": trim_text(article.get("title", ""), MAX_TITLE_LEN),
        "s": trim_text(
            article.get("summary") or article.get("description", ""),
            MAX_SUMMARY_LEN,
        ),
        "src": article.get("source", ""),
    }


def payload_size_kb(data) -> float:
    return len(json.dumps(data, ensure_ascii=False).encode("utf-8")) / 1024


# ═══════════════════════════════════════════════
# Prompts الجديدة v8
# ═══════════════════════════════════════════════

CURATION_SYSTEM = """أنت محرر أخبار محترف لجمهور سعودي/خليجي.

اختر أهم الأخبار بهذا الترتيب:
1. أخبار سعودية مهمة (اقتصاد/سياسة/تقنية/اجتماعية)
2. أخبار خليجية مؤثرة على السعودية
3. أخبار تقنية وذكاء اصطناعي عالمية مهمة
4. تجنب التكرار وتجنب الأخبار الترفيهية السطحية

ترجع JSON فقط:
{"selected": ["id1", "id2", ...]}

لا backticks. JSON خام."""


REWRITE_SYSTEM = """أنت كاتب محتوى محترف لمنصات التواصل العربية.
مهمتك: إعادة صياغة الخبر بنبرة جذابة وعربية فصيحة.

لكل خبر، أنتج:
1. عنوان عربي قوي (6-12 كلمة)
2. ملخص (سطرين فقط — Hook + معلومة)
3. جملة "ليه يهمك" (سطر واحد فقط)
4. تصنيف: ["سعودي", "اقتصاد", "تقنية", "سياسة", "ذكاء اصطناعي", "علوم", "ترفيه"]
5. إيموجي مناسب
6. نسخة Twitter جاهزة (أقل من 250 حرف، تجمع كل شيء)

قواعد الصياغة:
- نبرة عربية طبيعية (مو ترجمة آلية)
- لو الخبر سعودي، استخدم 🇸🇦 في الإيموجي
- نسخة Twitter: تبدأ بإيموجي + عنوان قوي + 1-2 سطر + هاشتاق واحد فقط
- ممنوع كلام مبهم زي "في تطور مهم..." — بدلها بأرقام/أسماء/تواريخ محددة

ترجع JSON فقط:
{
  "items": [
    {
      "id": "id1",
      "title": "عنوان جذاب",
      "summary": "السطر الأول. السطر الثاني.",
      "why_matters": "ليه يهمك في سطر واحد",
      "category": "سعودي|اقتصاد|تقنية|...",
      "emoji": "🇸🇦",
      "twitter_text": "🇸🇦 العنوان القوي\\n\\nالملخص في سطر أو اثنين.\\n\\n#السعودية"
    },
    ...
  ]
}

JSON خام فقط. لا backticks. لا تتجاوز 250 حرف في twitter_text."""


# ═══════════════════════════════════════════════
# الكلاس الرئيسي
# ═══════════════════════════════════════════════
class GroqClient:
    def __init__(self, timeout: int = 30):
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY مطلوب")
        self.timeout = timeout
        self.last_used_model: Optional[str] = None

    def _call(
        self,
        system: str,
        user: str,
        max_tokens: int = 2000,
        temperature: float = 0.4,
    ) -> Optional[str]:
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
                    log.warning("[groq] ❌ %s — 413 (size=%.1fKB)", model, size)
                    continue
                elif r.status_code == 429:
                    log.warning("[groq] ⏸ %s — Rate limited 5s", model)
                    time.sleep(5)
                    continue
                else:
                    log.warning("[groq] ❌ %s — HTTP %s", model, r.status_code)
                    continue
            except requests.exceptions.RequestException as e:
                log.warning("[groq] ❌ %s — Exception: %s", model, e)
                continue

        log.error("[groq] ❌ كل النماذج فشلت")
        return None

    # ─────────────────────────────────────────
    # Curation
    # ─────────────────────────────────────────
    def curate_news(
        self,
        articles: list[dict],
        max_final: int = MAX_FINAL_NEWS,
        prefer_saudi: bool = True,
    ) -> list[dict]:
        if not articles:
            return []
        if len(articles) <= max_final:
            return articles

        # ترتيب: السعودية أولاً
        if prefer_saudi:
            saudi = [a for a in articles if a.get("is_saudi") or is_saudi_news(a)]
            non_saudi = [a for a in articles if not (a.get("is_saudi") or is_saudi_news(a))]
            articles = saudi + non_saudi
            log.info("[curate] 🇸🇦 %d أخبار سعودية في الأولوية", len(saudi))

        slim_arts = [slim_article(a) for a in articles]
        id_to_art = {sa["i"]: a for sa, a in zip(slim_arts, articles)}

        batches = [
            slim_arts[i : i + BATCH_SIZE]
            for i in range(0, len(slim_arts), BATCH_SIZE)
        ]
        log.info("[curate] %d خبر → %d دفعة", len(articles), len(batches))

        per_batch = max(2, max_final // len(batches) + 1)
        selected_ids: list[str] = []

        for idx, batch in enumerate(batches, 1):
            user_prompt = (
                f"اختر أهم {per_batch} أخبار:\n\n"
                f"{json.dumps(batch, ensure_ascii=False)}"
            )
            test_size = payload_size_kb(
                {"system": CURATION_SYSTEM, "user": user_prompt}
            )
            if test_size > MAX_PAYLOAD_KB:
                for item in batch:
                    item["s"] = trim_text(item["s"], 100)
                user_prompt = (
                    f"اختر أهم {per_batch} أخبار:\n\n"
                    f"{json.dumps(batch, ensure_ascii=False)}"
                )

            raw = self._call(CURATION_SYSTEM, user_prompt, max_tokens=400)
            if not raw:
                continue

            try:
                data = self._parse_json(raw)
                ids = data.get("selected", [])
                if isinstance(ids, list):
                    selected_ids.extend(str(i) for i in ids)
                    log.info("[curate] دفعة %d/%d ✅ اختار %d", idx, len(batches), len(ids))
            except Exception as e:
                log.error("[curate] دفعة %d parse error: %s", idx, e)

        # رجّع الأصلية بناءً على IDs
        final = []
        seen = set()
        for sid in selected_ids:
            if sid in id_to_art and sid not in seen:
                final.append(id_to_art[sid])
                seen.add(sid)
                if len(final) >= max_final:
                    break

        if len(final) < max_final:
            for a in articles:
                if a not in final:
                    final.append(a)
                    if len(final) >= max_final:
                        break

        log.info("[curate] ✅ النهائي: %d خبر", len(final))
        return final

    # ─────────────────────────────────────────
    # Rewrite — صياغة احترافية + Twitter-ready (الجديد!)
    # ─────────────────────────────────────────
    def rewrite_news(self, articles: list[dict]) -> list[dict]:
        """
        يعيد صياغة كل خبر بنبرة جذابة + نسخة Twitter-ready.
        يضيف: title_ar, summary_ar, why_matters, category, emoji, twitter_text
        """
        if not articles:
            return []

        # نقسم على دفعات لتجنب 413
        batch_size = 4  # 4 أخبار/دفعة (تقليل أكثر للحصول على جودة أعلى)
        batches = [
            articles[i : i + batch_size]
            for i in range(0, len(articles), batch_size)
        ]

        all_rewritten = []
        for idx, batch in enumerate(batches, 1):
            slim = [slim_article(a) for a in batch]
            id_to_art = {sa["i"]: a for sa, a in zip(slim, batch)}

            user_prompt = (
                f"أعد صياغة الأخبار التالية مع نسخة Twitter لكل واحد:\n\n"
                f"{json.dumps(slim, ensure_ascii=False)}"
            )

            raw = self._call(
                REWRITE_SYSTEM, user_prompt, max_tokens=2000, temperature=0.5
            )
            if not raw:
                log.warning("[rewrite] دفعة %d فشلت", idx)
                # رجّع الأخبار كما هي بدون rewrite
                for a in batch:
                    enriched = dict(a)
                    enriched["title_ar"] = a.get("title", "")
                    enriched["summary_ar"] = a.get("summary", "")
                    enriched["why_matters"] = ""
                    enriched["category"] = "أخبار"
                    enriched["emoji"] = "📰"
                    enriched["twitter_text"] = (
                        f"📰 {trim_text(a.get('title', ''), 200)}"
                    )
                    all_rewritten.append(enriched)
                continue

            try:
                data = self._parse_json(raw)
                items = data.get("items", [])
                for item in items:
                    aid = str(item.get("id", ""))
                    if aid in id_to_art:
                        original = id_to_art[aid]
                        enriched = dict(original)
                        enriched["title_ar"] = item.get("title", original.get("title", ""))
                        enriched["summary_ar"] = item.get("summary", "")
                        enriched["why_matters"] = item.get("why_matters", "")
                        enriched["category"] = item.get("category", "أخبار")
                        enriched["emoji"] = item.get("emoji", "📰")
                        # تأكد من حد Twitter
                        twitter_text = item.get("twitter_text", "")
                        if len(twitter_text) > 280:
                            twitter_text = twitter_text[:270].rsplit(" ", 1)[0] + "…"
                        enriched["twitter_text"] = twitter_text
                        all_rewritten.append(enriched)
                log.info("[rewrite] دفعة %d/%d ✅ %d خبر", idx, len(batches), len(items))
            except Exception as e:
                log.error("[rewrite] دفعة %d parse error: %s", idx, e)

        return all_rewritten

    # ─────────────────────────────────────────
    # Generate top picks (للأمر /picks)
    # ─────────────────────────────────────────
    def generate_picks(self, articles: list[dict], count: int = 5) -> list[dict]:
        """يختار أفضل N أخبار اليوم بصيغة Twitter-ready."""
        # curate ثم rewrite
        curated = self.curate_news(articles, max_final=count)
        return self.rewrite_news(curated)

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
            raise ValueError(f"رد غير صالح: {raw[:200]}")

    def health_check(self) -> bool:
        log.info("[health] فحص النماذج...")
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
            except Exception:
                pass
        log.error("[health] ❌ كل النماذج فشلت")
        return False
