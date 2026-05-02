# 🤖 AI News Bot v7 — Newsroom Edition

بوت أخبار ذكي محسّن — يحل مشكلة `413 Payload Too Large` عبر:

1. ✅ **Multi-model fallback** — يجرّب `llama-3.3-70b-versatile` → `llama-3.1-8b-instant` → `gpt-oss-120b`
2. ✅ **Batching** — يقسم الأخبار على دفعات صغيرة (8 أخبار/دفعة) بدل 50
3. ✅ **Trimming** — يقصّر العناوين والملخصات قبل الإرسال
4. ✅ **Size guards** — يحسب حجم الـ payload قبل الإرسال ويقلصه لو لزم

---

## 📦 الهيكل

```
ai-news-bot/
├── config.py          # الإعدادات (مفاتيح، نماذج، جدول)
├── main.py            # نقطة الدخول + الجدولة
├── groq_client.py     # عميل Groq ذكي مع batching
├── news_fetcher.py    # جلب RSS + Google News بالتوازي
├── telegram_sender.py # إرسال لتيليقرام
├── requirements.txt
├── Procfile
└── .env.example
```

---

## 🚀 النشر على Railway

1. **اسحب كل الملفات** لمستودعك على GitHub
2. اربط Railway بالمستودع
3. أضف Environment Variables في Railway:
   ```
   GROQ_API_KEY        = gsk_...
   TELEGRAM_BOT_TOKEN  = ...
   TELEGRAM_CHAT_ID    = ...
   ```
4. Railway راح يبني ويشغّل تلقائياً

---

## 🧪 الاختبار المحلي

```bash
pip install -r requirements.txt

# Linux/Mac
export GROQ_API_KEY="gsk_..."
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
python main.py

# Windows PowerShell
$env:GROQ_API_KEY = "gsk_..."
$env:TELEGRAM_BOT_TOKEN = "..."
$env:TELEGRAM_CHAT_ID = "..."
python main.py
```

---

## ⚙️ التخصيص

كل الإعدادات في `config.py`:

```python
# نموذج Groq المفضل
GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", ...]

# حجم الدفعة (إذا 413 يرجع، قلّص هذا الرقم)
BATCH_SIZE = 8

# عدد الأخبار النهائية
MAX_FINAL_NEWS = 10

# الجدولة (الرياض)
SCHEDULE_HOURS = [8, 13, 18, 22]  # 4 دورات يومياً
DAILY_REPORT_HOUR = 23             # تقرير شامل 11م
```

---

## 🔌 الربط مع fahad-news-ai

البوت يصدّر دالة `fetch_top_arabic_news(limit)` للاستخدام من نظام fahad-news-ai:

```python
from news_fetcher import fetch_top_arabic_news
top = fetch_top_arabic_news(limit=1)
# [{"title": "...", "content": "...", "source": "...", "url": "..."}]
```

ضع هذا الملف في نفس مجلد `fahad-news-ai/scheduler.py`.

---

## 🆚 الفرق عن v6 القديم

| الميزة | v6 القديم | v7 الجديد |
|--------|----------|----------|
| النموذج الافتراضي | qwen3-32b (32K context) | llama-3.3-70b (128K context) |
| Fallback | نموذج واحد | chain من 3 نماذج |
| Batching | كل الأخبار دفعة وحدة | 8 أخبار/دفعة |
| Payload | full body من كل خبر | title + summary مختصر |
| Size guard | لا يوجد | يقصّر تلقائياً قبل الإرسال |

---

## 📝 ملاحظات

- لو رجعت مشاكل 413 ثانية، قلل `BATCH_SIZE` لـ 5
- لو تبي تستخدم qwen في الفترات قليلة الأخبار، أضف `qwen/qwen3-32b` في `GROQ_MODELS` بعد llama
- Telegram يحدد كل رسالة بـ 4096 حرف — البوت يقصّر تلقائياً
