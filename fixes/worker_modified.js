var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// src/utils.ts
async function sha256(text) {
  const buffer = new TextEncoder().encode(text);
  const hash = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(hash)).map((b) => b.toString(16).padStart(2, "0")).join("");
}
__name(sha256, "sha256");
function stripHtml(text) {
  if (!text) return "";
  return text.replace(/<[^>]+>/g, " ").replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/\s+/g, " ").trim();
}
__name(stripHtml, "stripHtml");
async function resolveRedirect(url) {
  if (!url.includes("news.google.com")) return url;
  try {
    const res = await fetch(url, {
      method: "HEAD",
      redirect: "follow",
      headers: { "User-Agent": "Mozilla/5.0 (compatible; fahadai-news/1.0)" }
    });
    return res.url || url;
  } catch {
    return url;
  }
}
__name(resolveRedirect, "resolveRedirect");
function isCleanUrl(url) {
  if (!url || !url.startsWith("http")) return false;
  if (url.includes("news.google.com")) return false;
  if (url.length > 400) return false;
  return true;
}
__name(isCleanUrl, "isCleanUrl");

async function fetchOgImage(url) {
  if (!url || url.includes("news.google.com") || url.includes("huggingface.co/papers")) return null;
  try {
    const res = await fetch(url, {
      method: "GET",
      headers: { "User-Agent": "Mozilla/5.0 (compatible; fahadai-news/2.0; +https://fahadai.news)", Accept: "text/html" },
      signal: AbortSignal.timeout(5e3),
      cf: { cacheTtl: 86400, cacheEverything: true }
    });
    if (!res.ok) return null;
    const reader = res.body.getReader();
    let html = "";
    while (html.length < 8192) {
      const { done, value } = await reader.read();
      if (done) break;
      html += new TextDecoder().decode(value);
    }
    reader.cancel();
    const match =
      html.match(/<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']/i) ||
      html.match(/<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:image["']/i) ||
      html.match(/<meta[^>]+name=["']twitter:image["'][^>]+content=["']([^"']+)["']/i);
    const imageUrl = match ? match[1].trim() : null;
    if (!imageUrl || !imageUrl.startsWith("http")) return null;
    return imageUrl;
  } catch {
    return null;
  }
}
__name(fetchOgImage, "fetchOgImage");

function extractYoutubeId(url) {
  if (!url) return null;
  const match = url.match(
    /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})/
  );
  return match ? match[1] : null;
}
__name(extractYoutubeId, "extractYoutubeId");
function json(data, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "public, max-age=60, s-maxage=120",
      ...extraHeaders
    }
  });
}
__name(json, "json");
function corsHeaders(origin) {
  const allowed = ["https://fahadai.news", "https://www.fahadai.news"];
  const allowedOrigin = allowed.includes(origin) ? origin : allowed[0];
  return {
    "access-control-allow-origin": allowedOrigin,
    "access-control-allow-methods": "GET, POST, OPTIONS",
    "access-control-allow-headers": "content-type",
    "access-control-max-age": "86400"
  };
}
__name(corsHeaders, "corsHeaders");
function safeJsonParse(text, fallback) {
  try {
    return JSON.parse(text);
  } catch {
    return fallback;
  }
}
__name(safeJsonParse, "safeJsonParse");

// src/rss.ts
async function fetchFeed(feed, env) {
  const headers = {
    "User-Agent": "Mozilla/5.0 (compatible; fahadai-news/2.0; +https://fahadai.news)",
    Accept: "application/rss+xml, application/atom+xml, application/xml, text/xml"
  };
  if (feed.etag) headers["If-None-Match"] = feed.etag;
  if (feed.last_modified) headers["If-Modified-Since"] = feed.last_modified;
  const response = await fetch(feed.url, {
    headers,
    cf: { cacheTtl: 300 }
  });
  if (response.status === 304) {
    return { items: [], notModified: true };
  }
  if (!response.ok) {
    throw new Error(`${feed.name}: HTTP ${response.status}`);
  }
  const xml = await response.text();
  const items = parseXml(xml);
  return {
    items,
    etag: response.headers.get("etag") || void 0,
    lastModified: response.headers.get("last-modified") || void 0
  };
}
__name(fetchFeed, "fetchFeed");
function parseXml(xml) {
  const items = [];
  const itemPattern = /<(item|entry)[\s\S]*?<\/\1>/gi;
  const matches = xml.match(itemPattern) || [];
  for (const match of matches.slice(0, 30)) {
    try {
      const isAtom = match.startsWith("<entry");
      const title = extractTag(match, "title") || "";
      const link = isAtom ? extractAtomLink(match) : extractTag(match, "link") || "";
      const description = extractTag(match, "description") || extractTag(match, "summary") || extractTag(match, "content") || extractTag(match, "content:encoded") || "";
      const pubDate = extractTag(match, "pubDate") || extractTag(match, "published") || extractTag(match, "updated") || extractTag(match, "dc:date") || "";
      const guid = extractTag(match, "guid") || extractTag(match, "id") || link;
      const image = extractImage(match);
      if (!title || !link) continue;
      items.push({
        guid: guid || link,
        title: stripHtml(title).slice(0, 500),
        link: link.trim(),
        summary: stripHtml(description).slice(0, 2e3),
        published: parseDate(pubDate),
        image
      });
    } catch {
    }
  }
  return items;
}
__name(parseXml, "parseXml");
function extractTag(xml, tag) {
  const cdataPattern = new RegExp(
    `<${tag}[^>]*><!\\[CDATA\\[([\\s\\S]*?)\\]\\]></${tag}>`,
    "i"
  );
  const cdata = xml.match(cdataPattern);
  if (cdata) return cdata[1].trim();
  const pattern = new RegExp(`<${tag}[^>]*>([\\s\\S]*?)</${tag}>`, "i");
  const match = xml.match(pattern);
  return match ? match[1].trim() : null;
}
__name(extractTag, "extractTag");
function extractAtomLink(xml) {
  const hrefMatch = xml.match(/<link[^>]+href=["']([^"']+)["'][^>]*\/?>/i);
  if (hrefMatch) return hrefMatch[1];
  const textMatch = xml.match(/<link[^>]*>([\s\S]*?)<\/link>/i);
  return textMatch ? textMatch[1].trim() : "";
}
__name(extractAtomLink, "extractAtomLink");
function extractImage(xml) {
  const mediaContent = xml.match(/<media:content[^>]+url=["']([^"']+)["']/i);
  if (mediaContent) return mediaContent[1];
  const mediaThumb = xml.match(/<media:thumbnail[^>]+url=["']([^"']+)["']/i);
  if (mediaThumb) return mediaThumb[1];
  const enclosure = xml.match(
    /<enclosure[^>]+url=["']([^"']+)["'][^>]+type=["']image\//i
  );
  if (enclosure) return enclosure[1];
  const imgInHtml = xml.match(/<img[^>]+src=["']([^"']+)["']/i);
  if (imgInHtml) return imgInHtml[1];
  return void 0;
}
__name(extractImage, "extractImage");
function parseDate(dateStr) {
  if (!dateStr) return Math.floor(Date.now() / 1e3);
  const d = new Date(dateStr);
  return isNaN(d.getTime()) ? Math.floor(Date.now() / 1e3) : Math.floor(d.getTime() / 1e3);
}
__name(parseDate, "parseDate");
async function fetchAllFeeds(feeds, env, concurrency = 8) {
  const results = [];
  for (let i = 0; i < feeds.length; i += concurrency) {
    const batch = feeds.slice(i, i + concurrency);
    const batchResults = await Promise.all(
      batch.map(async (feed) => {
        try {
          const result = await fetchFeed(feed, env);
          return {
            feed,
            items: result.items,
            etag: result.etag,
            lastModified: result.lastModified
          };
        } catch (err) {
          return {
            feed,
            items: [],
            error: err instanceof Error ? err.message : String(err)
          };
        }
      })
    );
    results.push(...batchResults);
  }
  return results;
}
__name(fetchAllFeeds, "fetchAllFeeds");
async function createGuidHash(feedId, item) {
  const signature = `${feedId}|${item.guid}|${item.link}`;
  return sha256(signature);
}
__name(createGuidHash, "createGuidHash");

// src/saudi.ts
var SAUDI_KEYWORDS = [
  // أسماء البلد والمدن
  "السعودية",
  "المملكة",
  "المملكة العربية",
  "Saudi",
  "KSA",
  "الرياض",
  "Riyadh",
  "جدة",
  "Jeddah",
  "مكة",
  "Mecca",
  "Makkah",
  "المدينة المنورة",
  "Medina",
  "الدمام",
  "Dammam",
  "الخبر",
  "Khobar",
  "الطائف",
  "تبوك",
  "أبها",
  "حائل",
  "نجران",
  "جازان",
  // المشاريع الكبرى ورؤية 2030
  "نيوم",
  "NEOM",
  "أرامكو",
  "Aramco",
  "سابك",
  "SABIC",
  "صندوق الاستثمارات العامة",
  "PIF",
  "Public Investment Fund",
  "رؤية 2030",
  "Vision 2030",
  "ولي العهد",
  "المملكة 2030",
  "إكسبو 2030",
  "Expo 2030",
  // المشاريع التطويرية
  "روشن",
  "Roshn",
  "القدية",
  "Qiddiya",
  "الدرعية",
  "Diriyah",
  "البحر الأحمر",
  "Red Sea",
  "أمالا",
  "AMAALA",
  "ذا لاين",
  "The Line",
  "تروجينا",
  "Trojena",
  "أوكساجون",
  "Oxagon",
  "سدير",
  "السودة",
  "السلمانية",
  // الجهات الحكومية والشركات السعودية
  "هيئة الذكاء الاصطناعي",
  "SDAIA",
  "سدايا",
  "هيئة المحتوى الرقمي",
  "DCO",
  "وزارة الاتصالات",
  "موسم الرياض",
  "Riyadh Season",
  "جدة الموسم",
  "stc",
  "زين",
  "موبايلي",
  "علم",
  "Elm",
  "humain",
  "هيومين",
  // الأحداث
  "leap",
  "ليب"
];
function isSaudiNews(title, summary) {
  const text = (title + " " + summary).toLowerCase();
  return SAUDI_KEYWORDS.some((kw) => text.includes(kw.toLowerCase()));
}
__name(isSaudiNews, "isSaudiNews");
function categorize(title, summary, feedCategory) {
  const text = (title + " " + summary).toLowerCase();
  if (isSaudiNews(title, summary)) {
    return "saudi";
  }
  if (/funding|ipo|acquisition|valuation|billion|million|revenue|earnings|stocks|nasdaq|dow|تمويل|استحواذ|أسهم|بورصة|إيرادات/i.test(
    text
  )) {
    return "economy";
  }
  if (/\bai\b|gpt|llm|machine learning|deep learning|neural|openai|anthropic|claude|gemini|ذكاء اصطناعي|نموذج لغوي/i.test(
    text
  )) {
    return "ai";
  }
  return feedCategory || "tech";
}
__name(categorize, "categorize");

// src/prefilter.ts
function smartPrefilter(items, options = {}) {
  const {
    maxTotal = 15,
    // ✨ زدناه من 12 إلى 15
    saudiQuota = 6,
    // ✨ زدناه من 5 إلى 6
    maxPerSource = 4,
    // ✨ زدناه من 2 إلى 4 (لو في 30 خبر من مصدر، خذ 4 أحسن)
    minTitleLen = 25
  } = options;
  const cleaned = items.filter((i) => i.item.title.length >= minTitleLen);
  const enriched = cleaned.map((i) => ({
    ...i,
    isSaudi: i.isSaudi || isSaudiNews(i.item.title, i.item.summary)
  }));
  enriched.sort((a, b) => {
    if (a.isSaudi !== b.isSaudi) return a.isSaudi ? -1 : 1;
    if (a.feed.priority !== b.feed.priority) {
      return b.feed.priority - a.feed.priority;
    }
    return b.item.published - a.item.published;
  });
  const sourceCounts = {};
  const saudiSelected = [];
  const otherSelected = [];
  for (const item of enriched) {
    const count = sourceCounts[item.feed.id] || 0;
    if (count >= maxPerSource) continue;
    sourceCounts[item.feed.id] = count + 1;
    if (item.isSaudi) {
      saudiSelected.push(item);
    } else {
      otherSelected.push(item);
    }
  }
  const finalSaudi = saudiSelected.slice(0, Math.min(saudiQuota, maxTotal));
  const remainingSlots = maxTotal - finalSaudi.length;
  const finalOther = otherSelected.slice(0, remainingSlots);
  const selected = [...finalSaudi, ...finalOther];
  console.log(
    `[prefilter] ${items.length} → ${selected.length} (\u{1F1F8}\u{1F1E6} ${finalSaudi.length} + \u{1F30D} ${finalOther.length})`
  );
  return selected;
}
__name(smartPrefilter, "smartPrefilter");

// src/translate.ts
var MODELS = [
  "llama-3.3-70b-versatile",
  // ✅ context كبير، جودة أعلى
  "llama-3.1-8b-instant",
  // سريع كـ backup
  "openai/gpt-oss-120b"
  // كبير جداً
];
var SYSTEM_PROMPT = `أنت محرر أخبار محترف لمنصة "FahadAI News" — قناة إخبارية تقنية سعودية.

أسلوبك: مدوّن سعودي عصري (مثل السبع، أياد الحمود، فيصل سيف، نواف).

**قواعد الصياغة:**

1. **العنوان (50-85 حرف):**
   - مباشر، يلفت الانتباه
   - بدون كلمات مكررة في الأخبار: "ثوري"، "مذهل"، "إن"، "قد"، "لقد"
   - تجنب المبالغات

2. **الملخص (2-3 جمل قصيرة):**
   - الجملة الأولى: Hook (رقم، حقيقة صادمة، مفاجأة)
   - الجملة الثانية: السياق المهم
   - الجملة الثالثة (اختيارية): التأثير

3. **"ليه يهمك" (سطر واحد فقط — 60-100 حرف):**
   - يجاوب: ليش هذا الخبر يخصني (كمطور/مستثمر/مهتم بالتقنية)؟
   - مباشر، بدون مصطلحات معقدة

4. **التغريدة (200-260 حرف):**
   - تبدأ بإيموجي مناسب
   - عنوان قوي + سطر ملخص
   - **3-4 هاشتاقات منفصلة بمسافات** (مثل: #ذكاء_اصطناعي #OpenAI #تقنية)
   - كل هاشتاق كلمة واحدة (لو كلمتين استخدم _ بينهم: #رؤية_2030)
   - لا تذكر "اقرأ المزيد" أو "تفاصيل في الرابط"

5. **عام:**
   - المصطلحات التقنية بالإنجليزي تبقى: AI, API, GPU, LLM, chip, token, benchmark, open source, startup, funding, model, embedding, fine-tune
   - الأرقام بالإنجليزي
   - تجنب الفصحى الجامدة، استخدم العربية الحديثة
   - لا حشو، لا مقدمات طويلة

**أرجع JSON خام فقط، بدون شرح أو backticks.**`;
function buildUserPrompt(item, feed) {
  const summary = item.summary.slice(0, 500);
  return `صُغ هذا الخبر بأسلوبك:

**العنوان الأصلي:** ${item.title}

**الملخص الأصلي:** ${summary}

**المصدر:** ${feed.name}

أرجع JSON بهذا الشكل بالضبط:
{
  "title": "العنوان العربي القوي (50-85 حرف)",
  "summary": "الجملة 1 (Hook). الجملة 2 (سياق). الجملة 3 اختياري (تأثير).",
  "why_matters": "ليه هذا يهمك في سطر واحد (60-100 حرف)",
  "tweet": "\u{1F680} العنوان القوي\\n\\nسطر ملخص جذاب يكمل المعنى.\\n\\n#هاشتاق1 #هاشتاق2 #هاشتاق3",
  "company": "اسم الشركة الرئيسية أو null",
  "region": "US أو EU أو China أو SA أو MENA أو Global",
  "hashtags": ["3-5 هاشتاقات بدون # وبدون مسافات داخلية - استخدم _ بدل المسافة لو كلمتين"],
  "importance": 5,
  "is_saudi": false
}

**ملاحظة:** is_saudi=true فقط إذا كان الخبر يخص السعودية مباشرة (شركة سعودية، مشروع سعودي، حدث في المملكة).`;
}
__name(buildUserPrompt, "buildUserPrompt");
async function callGroq(systemPrompt, userPrompt, apiKey) {
  for (const model of MODELS) {
    try {
      const startTime = Date.now();
      const response = await fetch(
        "https://api.groq.com/openai/v1/chat/completions",
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${apiKey}`,
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            model,
            messages: [
              { role: "system", content: systemPrompt },
              { role: "user", content: userPrompt }
            ],
            temperature: 0.65,
            max_tokens: 900,
            response_format: { type: "json_object" }
          })
        }
      );
      const latency = Date.now() - startTime;
      if (!response.ok) {
        const errorBody = await response.text();
        console.error(
          `[groq] ${model} ${response.status}: ${errorBody.slice(0, 200)}`
        );
        if (response.status === 401) return null;
        continue;
      }
      const data = await response.json();
      const content = data.choices?.[0]?.message?.content;
      if (!content) {
        console.error(`[groq] ${model} empty content`);
        continue;
      }
      console.log(
        `[groq] ✅ ${model} ${latency}ms ${data.usage?.completion_tokens || 0}tok`
      );
      return { content, model, latency };
    } catch (err) {
      console.error(`[groq] ${model} exception:`, err);
      continue;
    }
  }
  return null;
}
__name(callGroq, "callGroq");
function extractJson(text) {
  const cleaned = text.replace(/^```json\s*/i, "").replace(/^```\s*/, "").replace(/```\s*$/, "").trim();
  try {
    return JSON.parse(cleaned);
  } catch {
    const match = cleaned.match(/\{[\s\S]*\}/);
    if (match) {
      try {
        return JSON.parse(match[0]);
      } catch {
        return null;
      }
    }
    return null;
  }
}
__name(extractJson, "extractJson");
async function translateArticle(item, feed, env) {
  const userPrompt = buildUserPrompt(item, feed);
  const result = await callGroq(SYSTEM_PROMPT, userPrompt, env.GROQ_API_KEY);
  if (!result) return null;
  const parsed = extractJson(result.content);
  if (!parsed) {
    console.error(`[translate] bad JSON: ${result.content.slice(0, 150)}`);
    return null;
  }
  const isSaudiByKeywords = isSaudiNews(item.title, item.summary);
  const isSaudiByModel = parsed.is_saudi === true;
  const isSaudi = isSaudiByKeywords || isSaudiByModel;
  return {
    title: String(parsed.title || item.title).slice(0, 200),
    summary: String(parsed.summary || "").slice(0, 800),
    why_matters: String(parsed.why_matters || "").slice(0, 200),
    tweet: String(parsed.tweet || "").slice(0, 280),
    company: parsed.company ? String(parsed.company).slice(0, 50) : void 0,
    region: parsed.region ? String(parsed.region).slice(0, 20) : void 0,
    hashtags: Array.isArray(parsed.hashtags) ? parsed.hashtags.slice(0, 7).map(String) : [],
    importance: typeof parsed.importance === "number" ? parsed.importance : parseInt(String(parsed.importance || "5"), 10) || 5,
    is_saudi: isSaudi
  };
}
__name(translateArticle, "translateArticle");

// src/pipeline.ts
async function runPipeline(env) {
  const stats = {
    fetched: 0,
    new: 0,
    prefiltered: 0,
    translated: 0,
    inserted: 0,
    saudi_inserted: 0,
    errors: 0
  };
  const feedsResult = await env.DB.prepare(
    `SELECT id, name, url, category, region, priority, etag, last_modified,
            last_fetched_at, error_count, active
     FROM feeds
     WHERE active = 1
     ORDER BY priority DESC, last_fetched_at ASC
     LIMIT 35`
  ).all();
  const feeds = feedsResult.results;
  if (!feeds.length) {
    console.log("[pipeline] لا يوجد مصادر نشطة");
    return stats;
  }
  console.log(`[pipeline] بدء: ${feeds.length} مصدر`);
  const fetchResults = await fetchAllFeeds(feeds, env, 8);
  stats.fetched = fetchResults.reduce((sum, r) => sum + r.items.length, 0);
  const now = Math.floor(Date.now() / 1e3);
  const feedUpdates = [];
  for (const result of fetchResults) {
    if (result.error) {
      stats.errors++;
      feedUpdates.push(
        env.DB.prepare(
          `UPDATE feeds SET error_count = error_count + 1 WHERE id = ?`
        ).bind(result.feed.id)
      );
    } else {
      feedUpdates.push(
        env.DB.prepare(
          `UPDATE feeds
           SET last_fetched_at = ?, last_success_at = ?, error_count = 0
           WHERE id = ?`
        ).bind(now, now, result.feed.id)
      );
    }
  }
  if (feedUpdates.length > 0) {
    try {
      await env.DB.batch(feedUpdates);
    } catch {
    }
  }
  const allItems = [];
  for (const result of fetchResults) {
    for (const item of result.items) {
      const guid_hash = await createGuidHash(result.feed.id, item);
      const isSaudi = isSaudiNews(item.title, item.summary);
      allItems.push({
        feed: result.feed,
        item,
        guid_hash,
        isSaudi
      });
    }
  }
  if (!allItems.length) {
    console.log("[pipeline] لا يوجد مقالات");
    return stats;
  }
  const hashes = allItems.map((i) => i.guid_hash);
  const batchSize = 100;
  const existingHashes = /* @__PURE__ */ new Set();
  for (let i = 0; i < hashes.length; i += batchSize) {
    const batch = hashes.slice(i, i + batchSize);
    const placeholders = batch.map(() => "?").join(",");
    const existing = await env.DB.prepare(
      `SELECT guid_hash FROM articles WHERE guid_hash IN (${placeholders})`
    ).bind(...batch).all();
    for (const row of existing.results) {
      existingHashes.add(row.guid_hash);
    }
  }
  const newItems = allItems.filter((i) => !existingHashes.has(i.guid_hash));
  stats.new = newItems.length;
  console.log(
    `[pipeline] ${stats.fetched} فُحصت \xB7 ${stats.new} جديدة \xB7 ${newItems.filter((i) => i.isSaudi).length} سعودية`
  );
  if (!newItems.length) {
    return stats;
  }
  const toTranslate = smartPrefilter(newItems, {
    maxTotal: 12,
    saudiQuota: 5,
    maxPerSource: 2,
    minTitleLen: 25
  });
  stats.prefiltered = toTranslate.length;
  const translated = [];
  const concurrency = 3;
  for (let i = 0; i < toTranslate.length; i += concurrency) {
    const batch = toTranslate.slice(i, i + concurrency);
    const results = await Promise.all(
      batch.map(async ({ feed, item, guid_hash, isSaudi }) => {
        try {
          const translation = await translateArticle(item, feed, env);
          if (!translation) return null;
          const cleanUrl = await resolveRedirect(item.link);
          let videoId = extractYoutubeId(item.link);
          let videoUrl;
          if (videoId) {
            videoUrl = item.link;
          } else {
            const ytMatch = item.summary.match(
              /(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})/
            );
            if (ytMatch) {
              videoId = ytMatch[1];
              videoUrl = `https://www.youtube.com/watch?v=${videoId}`;
            }
          }
          let image_url = (videoId ? `https://img.youtube.com/vi/${videoId}/maxresdefault.jpg` : null) || item.image || null;
          if (!image_url) {
            image_url = await fetchOgImage(isCleanUrl(cleanUrl) ? cleanUrl : item.link);
          }
          const isSaudiFinal = isSaudiNews(item.title, item.summary) || isSaudiNews(translation.title, translation.summary);
          const category = isSaudiFinal ? "saudi" : categorize(item.title, item.summary);
          const article = {
            guid_hash,
            source: feed.name,
            source_url: feed.url,
            url: isCleanUrl(cleanUrl) ? cleanUrl : item.link,
            title: item.title,
            translated_title: translation.title,
            summary: item.summary.slice(0, 500),
            translated_summary: translation.summary,
            why_matters: translation.why_matters,
            tweet_text: translation.tweet,
            image_url: image_url || void 0,
            video_url: videoUrl,
            media_type: videoUrl ? "video" : "article",
            category,
            region: translation.region || feed.region,
            company: translation.company,
            hashtags: JSON.stringify(translation.hashtags || []),
            importance: translation.importance || 5,
            published_at: item.published,
            is_saudi: isSaudiFinal ? 1 : 0
          };
          return article;
        } catch (err) {
          console.error(`[translate] error:`, err);
          return null;
        }
      })
    );
    for (const article of results) {
      if (article) translated.push(article);
    }
  }
  stats.translated = translated.length;
  stats.saudi_inserted = translated.filter((a) => a.is_saudi === 1).length;
  if (translated.length > 0) {
    const stmts = translated.map(
      (a) => env.DB.prepare(
        `INSERT OR IGNORE INTO articles (
          guid_hash, source, source_url, url, title, translated_title,
          summary, translated_summary, why_matters, tweet_text,
          image_url, video_url, media_type, category, region, company, hashtags,
          importance, published_at, is_saudi
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
      ).bind(
        a.guid_hash,
        a.source,
        a.source_url || null,
        a.url,
        a.title,
        a.translated_title || null,
        a.summary || null,
        a.translated_summary || null,
        a.why_matters || null,
        a.tweet_text || null,
        a.image_url || null,
        a.video_url || null,
        a.media_type || "article",
        a.category,
        a.region || null,
        a.company || null,
        a.hashtags || null,
        a.importance || 5,
        a.published_at,
        a.is_saudi || 0
      )
    );
    try {
      const results = await env.DB.batch(stmts);
      stats.inserted = results.filter((r) => r.success).length;
    } catch (err) {
      console.error("[pipeline] insert error:", err);
      stats.errors++;
    }
  }
  if (env.CACHE && stats.inserted > 0) {
    try {
      await env.CACHE.put(
        "last_pipeline_run",
        JSON.stringify({
          timestamp: Date.now(),
          stats
        }),
        { expirationTtl: 86400 }
        // 24 ساعة
      );
      await env.CACHE.delete("news_cache_all");
      await env.CACHE.delete("news_cache_saudi");
    } catch (err) {
      console.error("[pipeline] cache error:", err);
    }
  }
  if (env.TELEGRAM_TOKEN && env.TELEGRAM_CHAT_ID && translated.length > 0) {
    try {
      const { sendToTelegram } = await import("./telegram");
      await sendToTelegram(translated, env);
      console.log(`[telegram] ✅ أرسلت ${Math.min(translated.length, 5)} خبر للقناة`);
    } catch (err) {
      console.error("[telegram] فشل الإرسال:", err);
    }
  }
  console.log(
    `[pipeline] ✅ ${stats.inserted} مقال جديد (\u{1F1F8}\u{1F1E6} ${stats.saudi_inserted} سعودي \xB7 \u{1F30D} ${stats.inserted - stats.saudi_inserted} عالمي)`
  );
  return stats;
}
__name(runPipeline, "runPipeline");

// src/index.ts
var index_default = {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const origin = request.headers.get("origin") || "";
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }
    if (url.pathname.startsWith("/api/")) {
      try {
        const ip = request.headers.get("cf-connecting-ip") || "unknown";
        const rateLimitResult = await env.API_LIMITER.limit({ key: ip });
        if (!rateLimitResult.success) {
          return json({ error: "Too many requests" }, 429, corsHeaders(origin));
        }
      } catch {
      }
      const response = await handleApi(request, env, url);
      const newHeaders = new Headers(response.headers);
      Object.entries(corsHeaders(origin)).forEach(
        ([k, v]) => newHeaders.set(k, v)
      );
      return new Response(response.body, {
        status: response.status,
        headers: newHeaders
      });
    }
    return env.ASSETS.fetch(request);
  },
  async scheduled(event, env, ctx) {
    console.log(`[cron] ${(/* @__PURE__ */ new Date()).toISOString()} - بدء الجلب`);
    try {
      const stats = await runPipeline(env);
      console.log(`[cron] انتهى:`, stats);
    } catch (err) {
      console.error("[cron] خطأ:", err);
    }
  }
};
async function handleApi(request, env, url) {
  const path = url.pathname;
  if (path === "/api/news" && request.method === "GET") {
    return handleGetNews(request, env, url);
  }
  if (path === "/api/videos" && request.method === "GET") {
    return handleGetVideos(request, env, url);
  }
  if (path === "/api/hashtags" && request.method === "GET") {
    return handleTrendingHashtags(env);
  }
  const newsMatch = path.match(/^\/api\/news\/(\d+)$/);
  if (newsMatch && request.method === "GET") {
    return handleGetSingleNews(parseInt(newsMatch[1]), env);
  }
  const shareMatch = path.match(/^\/api\/share\/(\d+)$/);
  if (shareMatch && request.method === "POST") {
    return handleShareNews(parseInt(shareMatch[1]), env);
  }
  if (path === "/api/categories" && request.method === "GET") {
    return handleCategories(env);
  }
  if (path === "/api/trending" && request.method === "GET") {
    return handleTrending(env);
  }
  if (path === "/api/pipeline/run" && request.method === "POST") {
    const stats = await runPipeline(env);
    return json({ ok: true, stats });
  }
  if (path === "/api/stats" && request.method === "GET") {
    return handleStats(env);
  }
  return json({ error: "Not found" }, 404);
}
__name(handleApi, "handleApi");
async function handleGetNews(request, env, url) {
  const category = url.searchParams.get("cat") || "all";
  const region = url.searchParams.get("region");
  const mediaType = url.searchParams.get("media");
  const page = Math.max(1, parseInt(url.searchParams.get("page") || "1"));
  const perPage = Math.min(
    30,
    Math.max(5, parseInt(url.searchParams.get("limit") || "20"))
  );
  const offset = (page - 1) * perPage;
  let sql = `
    SELECT id, source, source_url, url, title, translated_title,
           summary, translated_summary, why_matters, tweet_text,
           image_url, video_url, media_type, duration,
           category, region, company, hashtags,
           importance, is_saudi,
           published_at, created_at, views, shares
    FROM articles
    WHERE 1=1
  `;
  const params = [];
  if (category !== "all") {
    if (category === "saudi") {
      sql += " AND is_saudi = 1";
    } else if (category === "global") {
      sql += " AND is_saudi = 0 AND category NOT IN ('historical')";
    } else {
      sql += " AND category = ?";
      params.push(category);
    }
  }
  if (region) {
    sql += " AND region = ?";
    params.push(region);
  }
  if (mediaType) {
    sql += " AND media_type = ?";
    params.push(mediaType);
  }
  sql += " ORDER BY published_at DESC LIMIT ? OFFSET ?";
  params.push(perPage, offset);
  const result = await env.DB.prepare(sql).bind(...params).all();
  const articles = result.results.map((a) => ({
    ...a,
    hashtags: a.hashtags ? safeJsonParse(a.hashtags, []) : []
  }));
  return json({
    articles,
    page,
    perPage,
    hasMore: articles.length === perPage
  });
}
__name(handleGetNews, "handleGetNews");
async function handleGetVideos(request, env, url) {
  const limit = Math.min(30, parseInt(url.searchParams.get("limit") || "20"));
  const category = url.searchParams.get("cat");
  let sql = `
    SELECT id, source, source_url, url, title, translated_title,
           summary, translated_summary, why_matters, tweet_text,
           image_url, video_url, media_type, duration,
           category, region, company, hashtags, importance, is_saudi,
           published_at, created_at, views, shares
    FROM articles
    WHERE media_type = 'video' AND video_url IS NOT NULL
  `;
  const params = [];
  if (category && category !== "all") {
    sql += " AND category = ?";
    params.push(category);
  }
  sql += " ORDER BY published_at DESC LIMIT ?";
  params.push(limit);
  const result = await env.DB.prepare(sql).bind(...params).all();
  const videos = result.results.map((a) => ({
    ...a,
    hashtags: a.hashtags ? safeJsonParse(a.hashtags, []) : []
  }));
  return json({ videos, articles: videos, total: videos.length });
}
__name(handleGetVideos, "handleGetVideos");
async function handleTrendingHashtags(env) {
  const result = await env.DB.prepare(
    `SELECT hashtags FROM articles
     WHERE published_at > ? AND hashtags IS NOT NULL
     LIMIT 200`
  ).bind(Math.floor(Date.now() / 1e3) - 86400 * 7).all();
  const counts = {};
  for (const row of result.results) {
    try {
      const tags = JSON.parse(row.hashtags);
      for (const tag of tags) {
        const clean = tag.replace(/^#/, "").trim();
        if (clean.length > 1 && clean.length < 40) {
          counts[clean] = (counts[clean] || 0) + 1;
        }
      }
    } catch {
    }
  }
  const trending = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 20).map(([tag, count]) => ({ tag, count }));
  return json({ hashtags: trending });
}
__name(handleTrendingHashtags, "handleTrendingHashtags");
async function handleGetSingleNews(id, env) {
  const article = await env.DB.prepare(
    `SELECT * FROM articles WHERE id = ? LIMIT 1`
  ).bind(id).first();
  if (!article) {
    return json({ error: "Not found" }, 404);
  }
  await env.DB.prepare(`UPDATE articles SET views = views + 1 WHERE id = ?`).bind(id).run();
  return json({
    article: {
      ...article,
      hashtags: article.hashtags ? safeJsonParse(article.hashtags, []) : []
    }
  });
}
__name(handleGetSingleNews, "handleGetSingleNews");
async function handleShareNews(id, env) {
  const article = await env.DB.prepare(
    `SELECT tweet_text, url, hashtags FROM articles WHERE id = ? LIMIT 1`
  ).bind(id).first();
  if (!article) {
    return json({ error: "Not found" }, 404);
  }
  await env.DB.prepare(`UPDATE articles SET shares = shares + 1 WHERE id = ?`).bind(id).run();
  const hashtags = safeJsonParse(article.hashtags || "[]", []).map((t) => t.replace(/^#/, "")).slice(0, 5).join(",");
  const intentUrl = new URL("https://twitter.com/intent/tweet");
  intentUrl.searchParams.set("text", article.tweet_text || "");
  if (article.url) intentUrl.searchParams.set("url", article.url);
  if (hashtags) intentUrl.searchParams.set("hashtags", hashtags);
  return json({
    ok: true,
    intent_url: intentUrl.toString()
  });
}
__name(handleShareNews, "handleShareNews");
async function handleCategories(env) {
  const result = await env.DB.prepare(
    `SELECT
      CASE WHEN is_saudi = 1 THEN 'saudi' ELSE category END as cat,
      COUNT(*) as count
     FROM articles
     WHERE published_at > ?
     GROUP BY cat`
  ).bind(Math.floor(Date.now() / 1e3) - 86400 * 7).all();
  const videosCount = await env.DB.prepare(
    `SELECT COUNT(*) as count FROM articles
     WHERE media_type = 'video' AND published_at > ?`
  ).bind(Math.floor(Date.now() / 1e3) - 86400 * 7).first();
  return json({
    categories: [
      { id: "all", name: "الكل", ar: "الكل", count: 0 },
      { id: "saudi", name: "Saudi", ar: "\u{1F1F8}\u{1F1E6} سعودي", count: 0 },
      { id: "videos", name: "Videos", ar: "\u{1F4F9} فيديوهات", count: videosCount?.count || 0 },
      { id: "ai", name: "AI", ar: "ذكاء اصطناعي", count: 0 },
      { id: "economy", name: "Economy", ar: "اقتصاد", count: 0 },
      { id: "tech", name: "Tech", ar: "تقنية", count: 0 },
      { id: "global", name: "Global", ar: "عالمي", count: 0 }
    ].map((cat) => {
      if (cat.id === "videos") return cat;
      const found = result.results.find((r) => r.cat === cat.id);
      return { ...cat, count: found?.count || 0 };
    })
  });
}
__name(handleCategories, "handleCategories");
async function handleTrending(env) {
  const result = await env.DB.prepare(
    `SELECT id, source, url, title, translated_title, translated_summary,
            why_matters, tweet_text, image_url, video_url, media_type,
            category, region, company, hashtags, importance, is_saudi,
            published_at, views, shares
     FROM articles
     WHERE published_at > ?
     ORDER BY
       CASE WHEN is_saudi = 1 THEN 0 ELSE 1 END,
       importance DESC,
       views DESC
     LIMIT 10`
  ).bind(Math.floor(Date.now() / 1e3) - 86400).all();
  const articles = result.results.map((a) => ({
    ...a,
    hashtags: a.hashtags ? safeJsonParse(a.hashtags, []) : []
  }));
  return json({ articles });
}
__name(handleTrending, "handleTrending");
async function handleStats(env) {
  const total = await env.DB.prepare(
    `SELECT COUNT(*) as count FROM articles`
  ).first();
  const last24h = await env.DB.prepare(
    `SELECT COUNT(*) as count FROM articles WHERE created_at > ?`
  ).bind(Math.floor(Date.now() / 1e3) - 86400).first();
  const saudiToday = await env.DB.prepare(
    `SELECT COUNT(*) as count FROM articles WHERE is_saudi = 1 AND created_at > ?`
  ).bind(Math.floor(Date.now() / 1e3) - 86400).first();
  const videosToday = await env.DB.prepare(
    `SELECT COUNT(*) as count FROM articles
     WHERE media_type = 'video' AND created_at > ?`
  ).bind(Math.floor(Date.now() / 1e3) - 86400).first();
  const feeds = await env.DB.prepare(
    `SELECT COUNT(*) as count FROM feeds WHERE active = 1`
  ).first();
  const lastUpdate = await env.DB.prepare(
    `SELECT MAX(created_at) as last_update FROM articles`
  ).first();
  return json({
    total_articles: total?.count || 0,
    last_24h: last24h?.count || 0,
    saudi_24h: saudiToday?.count || 0,
    videos_24h: videosToday?.count || 0,
    active_feeds: feeds?.count || 0,
    last_update: lastUpdate?.last_update || null,
    server_time: (/* @__PURE__ */ new Date()).toISOString(),
    version: "v9.2"
  });
}
__name(handleStats, "handleStats");
export {
  index_default as default
};
//# sourceMappingURL=index.js.map
