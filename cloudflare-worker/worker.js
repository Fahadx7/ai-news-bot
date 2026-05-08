// fahadai-news worker — v9 (Pomelli Catalog UI)
// الواجهة الإخبارية الجديدة مدمجة مباشرة في الـ Worker

// ─── Utils ───────────────────────────────────────────────────────────────────

async function sha256(text) {
  const buffer = new TextEncoder().encode(text);
  const hash = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(hash)).map(b => b.toString(16).padStart(2, "0")).join("");
}

function stripHtml(text) {
  if (!text) return "";
  return text.replace(/<[^>]+>/g, " ").replace(/&nbsp;/g, " ").replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/\s+/g, " ").trim();
}

async function resolveRedirect(url) {
  if (!url.includes("news.google.com")) return url;
  try {
    const res = await fetch(url, { method: "HEAD", redirect: "follow", headers: { "User-Agent": "Mozilla/5.0 (compatible; fahadai-news/1.0)" } });
    return res.url || url;
  } catch { return url; }
}

function isCleanUrl(url) {
  if (!url || !url.startsWith("http")) return false;
  if (url.includes("news.google.com")) return false;
  if (url.length > 400) return false;
  return true;
}

function extractYoutubeId(url) {
  if (!url) return null;
  const match = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})/);
  return match ? match[1] : null;
}

function json(data, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "public, max-age=60, s-maxage=120", ...extraHeaders }
  });
}

function corsHeaders(origin) {
  const allowed = [
    "https://fahadai.news",
    "https://www.fahadai.news",
    "https://fahadai-news.aboamran2013.workers.dev",
  ];
  const allowedOrigin = allowed.includes(origin) ? origin : allowed[0];
  return {
    "access-control-allow-origin": allowedOrigin,
    "access-control-allow-methods": "GET, POST, OPTIONS",
    "access-control-allow-headers": "content-type",
    "access-control-max-age": "86400"
  };
}

async function fetchOgImage(url) {
  if (!url || url.includes("news.google.com") || url.includes("huggingface.co/papers")) return null;
  try {
    const res = await fetch(url, {
      method: "GET",
      headers: { "User-Agent": "Mozilla/5.0 (compatible; fahadai-news/1.0)", Accept: "text/html" },
      signal: AbortSignal.timeout(5000),
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
    const match = html.match(/<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']/i)
      || html.match(/<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:image["']/i)
      || html.match(/<meta[^>]+name=["']twitter:image["'][^>]+content=["']([^"']+)["']/i);
    const imageUrl = match ? match[1].trim() : null;
    if (!imageUrl || !imageUrl.startsWith("http")) return null;
    return imageUrl;
  } catch { return null; }
}

// ─── RSS ─────────────────────────────────────────────────────────────────────

async function fetchFeed(feed) {
  const headers = {
    "User-Agent": "Mozilla/5.0 (compatible; fahadai-news/1.0; +https://fahadai.news)",
    Accept: "application/rss+xml, application/atom+xml, application/xml, text/xml"
  };
  if (feed.etag) headers["If-None-Match"] = feed.etag;
  if (feed.last_modified) headers["If-Modified-Since"] = feed.last_modified;
  const response = await fetch(feed.url, { headers, cf: { cacheTtl: 300 } });
  if (response.status === 304) return { items: [], notModified: true };
  if (!response.ok) throw new Error(`${feed.name}: HTTP ${response.status}`);
  const xml = await response.text();
  return { items: parseXml(xml), etag: response.headers.get("etag"), lastModified: response.headers.get("last-modified") };
}

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
      items.push({ guid: guid || link, title: stripHtml(title).slice(0, 500), link: link.trim(), summary: stripHtml(description).slice(0, 2000), published: parseDate(pubDate), image });
    } catch {}
  }
  return items;
}

function extractTag(xml, tag) {
  const cdata = xml.match(new RegExp(`<${tag}[^>]*><!\\[CDATA\\[([\\s\\S]*?)\\]\\]></${tag}>`, "i"));
  if (cdata) return cdata[1].trim();
  const match = xml.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)</${tag}>`, "i"));
  return match ? match[1].trim() : null;
}

function extractAtomLink(xml) {
  const hrefMatch = xml.match(/<link[^>]+href=["']([^"']+)["'][^>]*\/?>/i);
  if (hrefMatch) return hrefMatch[1];
  const textMatch = xml.match(/<link[^>]*>([\s\S]*?)<\/link>/i);
  return textMatch ? textMatch[1].trim() : "";
}

function extractImage(xml) {
  return (xml.match(/<media:content[^>]+url=["']([^"']+)["']/i) ||
    xml.match(/<media:thumbnail[^>]+url=["']([^"']+)["']/i) ||
    xml.match(/<enclosure[^>]+url=["']([^"']+)["'][^>]+type=["']image\//i) ||
    xml.match(/<img[^>]+src=["']([^"']+)["']/i) || [])[1] || undefined;
}

function parseDate(dateStr) {
  if (!dateStr) return Math.floor(Date.now() / 1000);
  const d = new Date(dateStr);
  return isNaN(d.getTime()) ? Math.floor(Date.now() / 1000) : Math.floor(d.getTime() / 1000);
}

async function fetchAllFeeds(feeds, concurrency = 6) {
  const results = [];
  for (let i = 0; i < feeds.length; i += concurrency) {
    const batch = feeds.slice(i, i + concurrency);
    const batchResults = await Promise.all(batch.map(async feed => {
      try {
        const result = await fetchFeed(feed);
        return { feed, items: result.items, etag: result.etag, lastModified: result.lastModified };
      } catch (err) {
        return { feed, items: [], error: err instanceof Error ? err.message : String(err) };
      }
    }));
    results.push(...batchResults);
  }
  return results;
}

async function createGuidHash(feedId, item) {
  return sha256(`${feedId}|${item.guid}|${item.link}`);
}

// ─── Translate ────────────────────────────────────────────────────────────────

const GROQ_MODELS = ["llama-3.1-8b-instant"];

const SYSTEM_PROMPT = `أنت محرر قناة تقنية سعودية. ترجم أخبار التقنية من الإنجليزي للعربي بأسلوب المدونين السعوديين مثل السبع، أياد الحمود، فيصل سيف.

قواعد:
- لهجة سعودية معاصرة، تجنب الفصحى الجامدة
- المصطلحات التقنية تبقى بالإنجليزي: AI, API, GPU, LLM, chip, token, benchmark, open source, startup, funding, model
- جمل قصيرة مباشرة. لا حشو
- ممنوع: "إنّ"، "قد"، "لقد"، ثوري، مذهل
- الأرقام بالإنجليزي
- أرجع JSON فقط، بدون شرح`;

function categorize(title, summary, feedCategory) {
  const text = (title + " " + summary).toLowerCase();
  if (/saudi|سعود|kingdom|humain|sdaia|neom|aramco|pif|vision 2030|رؤية 2030|leap|سدايا|نيوم/i.test(text)) return "saudi";
  if (/funding|ipo|acquisition|valuation|billion|million|revenue|earnings|تمويل|استحواذ/i.test(text)) return "economy";
  return feedCategory || "ai";
}

async function translateArticle(item, feed, env) {
  const summary = item.summary.slice(0, 400);
  const userPrompt = `ترجم للعربي بأسلوب سعودي:

العنوان: ${item.title}
الملخص: ${summary}
المصدر: ${feed.name}

أرجع JSON بهذا الشكل:
{
  "title": "العنوان العربي القوي (50-85 حرف)",
  "summary": "ملخص سلس 3-4 جمل",
  "tweet": "تغريدة 200-240 حرف بأسلوب سعودي",
  "company": "الشركة الرئيسية",
  "region": "US أو EU أو China أو SA أو MENA أو Global",
  "hashtags": ["5 هاشتاقات"],
  "importance": 5
}`;

  for (const model of GROQ_MODELS) {
    try {
      const response = await fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "POST",
        headers: { Authorization: `Bearer ${env.GROQ_API_KEY}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          model,
          messages: [{ role: "system", content: SYSTEM_PROMPT }, { role: "user", content: userPrompt }],
          temperature: 0.7, max_tokens: 800, response_format: { type: "json_object" }
        })
      });
      if (!response.ok) { if (response.status === 401) return null; continue; }
      const data = await response.json();
      const content = data.choices?.[0]?.message?.content;
      if (!content) continue;
      const parsed = extractJson(content);
      if (!parsed) continue;
      return {
        title: String(parsed.title || item.title).slice(0, 200),
        summary: String(parsed.summary || "").slice(0, 800),
        tweet: String(parsed.tweet || "").slice(0, 280),
        company: parsed.company ? String(parsed.company).slice(0, 50) : undefined,
        region: parsed.region ? String(parsed.region).slice(0, 20) : undefined,
        hashtags: Array.isArray(parsed.hashtags) ? parsed.hashtags.slice(0, 7).map(String) : [],
        importance: typeof parsed.importance === "number" ? parsed.importance : parseInt(String(parsed.importance || "5"), 10) || 5
      };
    } catch { continue; }
  }
  return null;
}

function extractJson(text) {
  const cleaned = text.replace(/^```json\s*/i, "").replace(/^```\s*/, "").replace(/```\s*$/, "").trim();
  try { return JSON.parse(cleaned); } catch {
    const match = cleaned.match(/\{[\s\S]*\}/);
    if (match) { try { return JSON.parse(match[0]); } catch { return null; } }
    return null;
  }
}

// ─── Pipeline ─────────────────────────────────────────────────────────────────

async function runPipeline(env) {
  const stats = { fetched: 0, new: 0, translated: 0, inserted: 0, errors: 0 };
  const feedsResult = await env.DB.prepare(
    `SELECT id, name, url, category, region, priority, etag, last_modified, last_fetched_at, error_count, active FROM feeds WHERE active = 1 ORDER BY priority DESC, last_fetched_at ASC LIMIT 20`
  ).all();
  const feeds = feedsResult.results;
  if (!feeds.length) return stats;

  const fetchResults = await fetchAllFeeds(feeds, 6);
  stats.fetched = fetchResults.reduce((sum, r) => sum + r.items.length, 0);
  const now = Math.floor(Date.now() / 1000);

  const feedUpdates = feedResults => feedResults.map(result =>
    result.error
      ? env.DB.prepare(`UPDATE feeds SET error_count = error_count + 1 WHERE id = ?`).bind(result.feed.id)
      : env.DB.prepare(`UPDATE feeds SET last_fetched_at = ?, last_success_at = ?, error_count = 0 WHERE id = ?`).bind(now, now, result.feed.id)
  );

  try { await env.DB.batch(feedUpdates(fetchResults)); } catch {}

  const allItems = [];
  for (const result of fetchResults) {
    for (const item of result.items) {
      const guid_hash = await createGuidHash(result.feed.id, item);
      allItems.push({ feed: result.feed, item, guid_hash });
    }
  }
  if (!allItems.length) return stats;

  const hashes = allItems.map(i => i.guid_hash);
  const existingHashes = new Set();
  for (let i = 0; i < hashes.length; i += 100) {
    const batch = hashes.slice(i, i + 100);
    const existing = await env.DB.prepare(`SELECT guid_hash FROM articles WHERE guid_hash IN (${batch.map(() => "?").join(",")})`).bind(...batch).all();
    for (const row of existing.results) existingHashes.add(row.guid_hash);
  }

  const newItems = allItems.filter(i => !existingHashes.has(i.guid_hash));
  stats.new = newItems.length;
  if (!newItems.length) return stats;

  const feedCounts = {};
  const toTranslate = [];
  for (const item of newItems.sort((a, b) => b.feed.priority - a.feed.priority)) {
    const count = feedCounts[item.feed.id] || 0;
    if (count >= 2) continue;
    feedCounts[item.feed.id] = count + 1;
    toTranslate.push(item);
    if (toTranslate.length >= 6) break;
  }

  const translated = [];
  for (let i = 0; i < toTranslate.length; i += 2) {
    const batch = toTranslate.slice(i, i + 2);
    const results = await Promise.all(batch.map(async ({ feed, item, guid_hash }) => {
      try {
        const translation = await translateArticle(item, feed, env);
        if (!translation) return null;
        const cleanUrl = await resolveRedirect(item.link);
        let videoId = extractYoutubeId(item.link);
        let videoUrl;
        if (videoId) { videoUrl = item.link; } else {
          const ytMatch = item.summary.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
          if (ytMatch) { videoId = ytMatch[1]; videoUrl = `https://www.youtube.com/watch?v=${videoId}`; }
        }
        let image_url = (videoId ? `https://img.youtube.com/vi/${videoId}/maxresdefault.jpg` : null) || item.image || null;
        if (!image_url) image_url = await fetchOgImage(item.link);
        return {
          guid_hash, source: feed.name, source_url: feed.url,
          url: isCleanUrl(cleanUrl) ? cleanUrl : item.link,
          title: item.title, translated_title: translation.title,
          summary: item.summary.slice(0, 500), translated_summary: translation.summary,
          tweet_text: translation.tweet, image_url: image_url || undefined,
          video_url: videoUrl, media_type: videoUrl ? "video" : "article",
          category: categorize(item.title, item.summary, feed.category),
          region: translation.region || feed.region, company: translation.company,
          hashtags: JSON.stringify(translation.hashtags || []),
          importance: translation.importance || 5, published_at: item.published
        };
      } catch { return null; }
    }));
    for (const a of results) if (a) translated.push(a);
  }

  stats.translated = translated.length;
  if (translated.length > 0) {
    const stmts = translated.map(a =>
      env.DB.prepare(`INSERT OR IGNORE INTO articles (guid_hash, source, source_url, url, title, translated_title, summary, translated_summary, tweet_text, image_url, video_url, media_type, category, region, company, hashtags, importance, published_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
        .bind(a.guid_hash, a.source, a.source_url || null, a.url, a.title, a.translated_title || null, a.summary || null, a.translated_summary || null, a.tweet_text || null, a.image_url || null, a.video_url || null, a.media_type || "article", a.category, a.region || null, a.company || null, a.hashtags || null, a.importance || 5, a.published_at)
    );
    try {
      const results = await env.DB.batch(stmts);
      stats.inserted = results.filter(r => r.success).length;
    } catch (err) { stats.errors++; }
  }
  return stats;
}

// ─── HTML (Pomelli Catalog Style) ────────────────────────────────────────────
// See full HTML in the getHtml() function below
// Design: dark catalog grid, card-per-article, Twitter share, category filters

function getHtml() {
  return `<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>فهد AI نيوز — أخبار التقنية والذكاء الاصطناعي</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Arabic:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#07070f;--s1:#111120;--s2:#1a1a2e;--s3:#242440;--border:#2d2d50;--text:#f0f0ff;--text2:#8888bb;--text3:#5555aa;--cyan:#00e5ff;--green:#00e676;--purple:#bb86fc;--gold:#ffd600;--blue:#40c4ff;--red:#ff5252;--orange:#ff9100}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'IBM Plex Arabic',system-ui,sans-serif;background:var(--bg);color:var(--text);direction:rtl;min-height:100vh;overflow-x:hidden}
::-webkit-scrollbar{width:6px}::-webkit-scrollbar-track{background:var(--bg)}::-webkit-scrollbar-thumb{background:var(--s3);border-radius:3px}
.header{position:sticky;top:0;z-index:200;background:rgba(7,7,15,0.85);backdrop-filter:blur(24px) saturate(180%);border-bottom:1px solid var(--border)}
.header-inner{max-width:1440px;margin:0 auto;padding:0 1.5rem;display:flex;align-items:center;gap:1rem;height:64px}
.logo{display:flex;align-items:center;gap:0.6rem;text-decoration:none;flex-shrink:0}
.logo-mark{width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,var(--purple),var(--cyan));display:flex;align-items:center;justify-content:center;font-size:1.1rem;box-shadow:0 0 20px rgba(187,134,252,0.3)}
.logo-text{font-size:1.05rem;font-weight:700;color:var(--text)}
.logo-badge{font-size:0.6rem;font-weight:600;padding:0.1rem 0.4rem;border-radius:4px;background:rgba(187,134,252,0.15);color:var(--purple);border:1px solid rgba(187,134,252,0.3)}
.search-wrap{flex:1;max-width:420px;position:relative}
.search-input{width:100%;background:var(--s2);border:1px solid var(--border);border-radius:12px;padding:0.6rem 1rem 0.6rem 2.8rem;color:var(--text);font-family:inherit;font-size:0.88rem;outline:none;transition:border-color .2s,box-shadow .2s}
.search-input::placeholder{color:var(--text3)}
.search-input:focus{border-color:rgba(187,134,252,0.5);box-shadow:0 0 0 3px rgba(187,134,252,0.1)}
.search-icon{position:absolute;left:0.9rem;top:50%;transform:translateY(-50%);color:var(--text3);pointer-events:none}
.header-actions{display:flex;align-items:center;gap:0.75rem;margin-right:auto}
.live-badge{display:flex;align-items:center;gap:0.4rem;font-size:0.72rem;color:var(--text2);background:var(--s2);border:1px solid var(--border);border-radius:999px;padding:0.3rem 0.75rem}
.live-dot{width:7px;height:7px;border-radius:50%;background:var(--green);animation:livePulse 2s infinite}
@keyframes livePulse{0%,100%{opacity:1;box-shadow:0 0 0 0 rgba(0,230,118,0.4)}50%{opacity:.6;box-shadow:0 0 0 5px rgba(0,230,118,0)}}
.refresh-btn{width:34px;height:34px;border-radius:10px;border:1px solid var(--border);background:var(--s2);color:var(--text2);cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .2s}
.refresh-btn:hover{background:var(--s3);color:var(--text)}
.refresh-btn.spinning svg{animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.cat-nav{background:rgba(7,7,15,0.7);backdrop-filter:blur(12px);border-bottom:1px solid var(--border);position:sticky;top:64px;z-index:199}
.cat-inner{max-width:1440px;margin:0 auto;padding:0 1.5rem;display:flex;gap:0.25rem;overflow-x:auto;scrollbar-width:none;height:50px;align-items:center}
.cat-inner::-webkit-scrollbar{display:none}
.cat-btn{flex-shrink:0;display:flex;align-items:center;gap:0.4rem;padding:0.35rem 1rem;border-radius:999px;font-size:0.8rem;font-family:inherit;cursor:pointer;border:1px solid transparent;background:transparent;color:var(--text2);transition:all .2s;font-weight:500}
.cat-btn:hover{background:var(--s2);color:var(--text)}
.cat-btn.active{background:var(--s2);border-color:currentColor;font-weight:600}
.cat-btn[data-cat="all"].active{color:var(--cyan)}.cat-btn[data-cat="ai"].active{color:var(--purple)}.cat-btn[data-cat="saudi"].active{color:var(--green)}.cat-btn[data-cat="economy"].active{color:var(--gold)}.cat-btn[data-cat="global"].active{color:var(--blue)}.cat-btn[data-cat="historical"].active{color:var(--orange)}
.cat-count{font-size:0.65rem;background:rgba(255,255,255,0.08);padding:0.1rem 0.4rem;border-radius:999px}
.page{max-width:1440px;margin:0 auto;padding:1.5rem;display:grid;grid-template-columns:1fr 300px;gap:1.5rem}
@media(max-width:1100px){.page{grid-template-columns:1fr}.sidebar{display:none}}
@media(max-width:600px){.page{padding:1rem}}
.stats-hero{display:grid;grid-template-columns:repeat(3,1fr);gap:0.75rem;margin-bottom:1.5rem}
.stat-card{background:var(--s1);border:1px solid var(--border);border-radius:14px;padding:1rem;display:flex;align-items:center;gap:0.75rem}
.stat-icon{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:1.1rem;flex-shrink:0}
.stat-num{font-size:1.4rem;font-weight:700;background:linear-gradient(135deg,var(--cyan),var(--purple));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.stat-label{font-size:0.7rem;color:var(--text2);margin-top:1px}
.section-title{display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem}
.section-title h2{font-size:0.9rem;font-weight:600;color:var(--text2)}
.section-title-line{flex:1;height:1px;background:var(--border);margin-right:0.75rem}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem}
@media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:520px){.grid{grid-template-columns:1fr}}
.card{background:var(--s1);border:1px solid var(--border);border-radius:16px;overflow:hidden;display:flex;flex-direction:column;cursor:pointer;transition:transform .25s,border-color .25s,box-shadow .25s;animation:fadeUp .35s ease both}
.card:hover{transform:translateY(-4px);border-color:rgba(187,134,252,0.25);box-shadow:0 16px 48px rgba(0,0,0,0.5)}
@keyframes fadeUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
.card-img{position:relative;aspect-ratio:16/9;overflow:hidden;background:var(--s2);flex-shrink:0}
.card-img img{width:100%;height:100%;object-fit:cover;transition:transform .4s;display:block}
.card:hover .card-img img{transform:scale(1.06)}
.card-img-fallback{width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:2.8rem;background:linear-gradient(135deg,var(--s2),var(--s3))}
.img-gradient{position:absolute;inset:0;background:linear-gradient(to bottom,transparent 30%,rgba(7,7,15,.95) 100%)}
.card-badge{position:absolute;top:.75rem;right:.75rem;padding:.2rem .6rem;border-radius:999px;font-size:.65rem;font-weight:700;backdrop-filter:blur(8px)}
.b-ai{background:rgba(187,134,252,.15);color:var(--purple);border:1px solid rgba(187,134,252,.3)}
.b-saudi{background:rgba(0,230,118,.12);color:var(--green);border:1px solid rgba(0,230,118,.25)}
.b-economy{background:rgba(255,214,0,.12);color:var(--gold);border:1px solid rgba(255,214,0,.25)}
.b-global{background:rgba(64,196,255,.12);color:var(--blue);border:1px solid rgba(64,196,255,.25)}
.b-historical{background:rgba(255,145,0,.12);color:var(--orange);border:1px solid rgba(255,145,0,.25)}
.importance-badge{position:absolute;bottom:.75rem;left:.75rem;display:flex;gap:2px}
.imp-dot{width:5px;height:5px;border-radius:50%;background:rgba(255,255,255,.2)}
.imp-dot.on{background:var(--cyan)}
.card-body{padding:.9rem;flex:1;display:flex;flex-direction:column;gap:.5rem}
.card-title{font-size:.88rem;font-weight:600;line-height:1.55;color:var(--text);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card-summary{font-size:.76rem;color:var(--text2);line-height:1.65;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;flex:1}
.card-meta{display:flex;align-items:center;justify-content:space-between;font-size:.68rem;color:var(--text3);padding-top:.5rem;border-top:1px solid rgba(45,45,80,.6)}
.company-tag{background:var(--s2);padding:.15rem .5rem;border-radius:999px;font-size:.65rem;color:var(--text2);border:1px solid var(--border)}
.card-actions{display:flex;gap:.5rem;padding:.65rem .9rem;border-top:1px solid rgba(45,45,80,.5)}
.action-btn{flex:1;padding:.45rem .5rem;border-radius:8px;border:1px solid var(--border);background:transparent;color:var(--text2);font-family:inherit;font-size:.72rem;cursor:pointer;transition:all .2s;display:flex;align-items:center;justify-content:center;gap:.3rem;font-weight:500}
.action-btn:hover{background:var(--s2);color:var(--text)}
.btn-x{color:#1d9bf0;border-color:rgba(29,155,240,.2)}.btn-x:hover{background:rgba(29,155,240,.08)}
.btn-read{color:var(--cyan);border-color:rgba(0,229,255,.2)}.btn-read:hover{background:rgba(0,229,255,.06)}
.skeleton{background:linear-gradient(90deg,var(--s1) 25%,var(--s2) 50%,var(--s1) 75%);background-size:200% 100%;animation:shimmer 1.8s infinite;border-radius:8px}
@keyframes shimmer{0%{background-position:-200% 0}100%{background-position:200% 0}}
.sk-card{background:var(--s1);border:1px solid var(--border);border-radius:16px;overflow:hidden}
.sk-img{aspect-ratio:16/9}.sk-body{padding:.9rem;display:flex;flex-direction:column;gap:.7rem}
.sk-line{height:11px}.sk-full{width:100%}.sk-3q{width:75%}.sk-half{width:50%}
.empty-state{grid-column:1/-1;text-align:center;padding:5rem 2rem;color:var(--text2)}
.empty-icon{font-size:3.5rem;margin-bottom:1.25rem;opacity:.7}
.empty-state h3{font-size:1.1rem;color:var(--text);margin-bottom:.5rem}
.load-more-wrap{grid-column:1/-1;display:flex;justify-content:center;padding:1.25rem 0}
.load-more-btn{display:flex;align-items:center;gap:.5rem;padding:.7rem 2.5rem;border-radius:12px;border:1px solid var(--border);background:var(--s1);color:var(--text2);font-family:inherit;font-size:.85rem;cursor:pointer;transition:all .2s}
.load-more-btn:hover{background:var(--s2);border-color:rgba(187,134,252,.3);color:var(--text)}
.card.featured{grid-column:span 2}.card.featured .card-img{aspect-ratio:2/1}.card.featured .card-title{font-size:1.05rem;-webkit-line-clamp:3}
@media(max-width:900px){.card.featured{grid-column:span 1}}
.sidebar{display:flex;flex-direction:column;gap:1rem}
.widget{background:var(--s1);border:1px solid var(--border);border-radius:16px;overflow:hidden}
.widget-head{padding:.9rem 1rem;border-bottom:1px solid var(--border);font-size:.82rem;font-weight:600;display:flex;align-items:center;justify-content:space-between}
.widget-head span{color:var(--text2);font-weight:400;font-size:.72rem}
.tr-item{display:flex;align-items:flex-start;gap:.75rem;padding:.75rem 1rem;border-bottom:1px solid rgba(45,45,80,.5);cursor:pointer;transition:background .15s}
.tr-item:last-child{border-bottom:none}.tr-item:hover{background:var(--s2)}
.tr-num{font-size:1.15rem;font-weight:800;width:22px;flex-shrink:0;line-height:1;opacity:.3}
.tr-item:nth-child(1) .tr-num{opacity:1;color:var(--gold)}.tr-item:nth-child(2) .tr-num{opacity:.8;color:var(--text2)}.tr-item:nth-child(3) .tr-num{opacity:.6}
.tr-title{font-size:.78rem;line-height:1.45;color:var(--text);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.tr-meta{font-size:.65rem;color:var(--text3);margin-top:.25rem}
.tweet-box{padding:.9rem 1rem}
.tweet-placeholder{font-size:.78rem;color:var(--text2);line-height:1.6;text-align:center;padding:1rem 0}
.tweet-text{font-size:.78rem;line-height:1.7;background:var(--s2);border:1px solid var(--border);border-radius:10px;padding:.75rem;margin-bottom:.75rem;white-space:pre-wrap;word-break:break-word;color:var(--text)}
.tweet-chars{font-size:.67rem;color:var(--text3);margin-bottom:.6rem;text-align:left}
.tweet-chars span{font-weight:600;color:var(--text2)}
.copy-btn{width:100%;padding:.55rem;border-radius:8px;border:1px solid rgba(29,155,240,.25);background:rgba(29,155,240,.06);color:#1d9bf0;font-family:inherit;font-size:.75rem;cursor:pointer;transition:all .2s;display:flex;align-items:center;justify-content:center;gap:.4rem;font-weight:600}
.copy-btn:hover{background:rgba(29,155,240,.12)}
.toast{position:fixed;bottom:1.5rem;left:50%;transform:translateX(-50%) translateY(80px);background:var(--s2);border:1px solid var(--border);border-radius:12px;padding:.65rem 1.5rem;font-size:.82rem;z-index:999;transition:transform .3s cubic-bezier(.175,.885,.32,1.275);white-space:nowrap;box-shadow:0 8px 32px rgba(0,0,0,.4)}
.toast.show{transform:translateX(-50%) translateY(0)}
</style>
</head>
<body>
<header class="header">
  <div class="header-inner">
    <a class="logo" href="/">
      <div class="logo-mark">🤖</div>
      <div><div class="logo-text">فهد AI نيوز</div><div class="logo-badge">BETA</div></div>
    </a>
    <div class="search-wrap">
      <span class="search-icon">🔍</span>
      <input class="search-input" id="searchInput" type="search" placeholder="ابحث في الأخبار...">
    </div>
    <div class="header-actions">
      <div class="live-badge"><span class="live-dot"></span><span id="liveText">مباشر</span></div>
      <button class="refresh-btn" id="refreshBtn" onclick="refreshAll()" title="تحديث">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
      </button>
    </div>
  </div>
</header>
<nav class="cat-nav">
  <div class="cat-inner" id="catNav">
    <button class="cat-btn active" data-cat="all">🌐 الكل <span class="cat-count" id="cnt-all"></span></button>
    <button class="cat-btn" data-cat="ai">🤖 ذكاء اصطناعي <span class="cat-count" id="cnt-ai"></span></button>
    <button class="cat-btn" data-cat="saudi">🇸🇦 سعودي <span class="cat-count" id="cnt-saudi"></span></button>
    <button class="cat-btn" data-cat="economy">💰 اقتصاد <span class="cat-count" id="cnt-economy"></span></button>
    <button class="cat-btn" data-cat="global">🌍 عالمي <span class="cat-count" id="cnt-global"></span></button>
    <button class="cat-btn" data-cat="historical">📜 تاريخي <span class="cat-count" id="cnt-historical"></span></button>
  </div>
</nav>
<div class="page">
  <main>
    <div class="stats-hero">
      <div class="stat-card"><div class="stat-icon" style="background:rgba(187,134,252,.1)">📰</div><div><div class="stat-num" id="s-total">—</div><div class="stat-label">إجمالي الأخبار</div></div></div>
      <div class="stat-card"><div class="stat-icon" style="background:rgba(0,229,255,.08)">⚡</div><div><div class="stat-num" id="s-24h">—</div><div class="stat-label">آخر 24 ساعة</div></div></div>
      <div class="stat-card"><div class="stat-icon" style="background:rgba(0,230,118,.08)">📡</div><div><div class="stat-num" id="s-feeds">—</div><div class="stat-label">مصدر نشط</div></div></div>
    </div>
    <div class="section-title"><h2 id="sectionTitle">🗞️ آخر الأخبار</h2><div class="section-title-line"></div></div>
    <div class="grid" id="grid"></div>
  </main>
  <aside class="sidebar">
    <div class="widget"><div class="widget-head">🔥 الأكثر أهمية <span id="tr-updated"></span></div><div id="trendingList"></div></div>
    <div class="widget"><div class="widget-head">𝕏 نسخة تويتر جاهزة</div><div class="tweet-box" id="tweetBox"><p class="tweet-placeholder">اضغط زر "شارك" على أي خبر لتظهر نسخته الجاهزة هنا</p></div></div>
  </aside>
</div>
<div id="toast" class="toast"></div>
<script>
const CAT={ai:{label:'ذكاء اصطناعي',emoji:'🤖',cls:'b-ai'},saudi:{label:'سعودي',emoji:'🇸🇦',cls:'b-saudi'},economy:{label:'اقتصاد',emoji:'💰',cls:'b-economy'},global:{label:'عالمي',emoji:'🌍',cls:'b-global'},historical:{label:'تاريخي',emoji:'📜',cls:'b-historical'}};
function catInfo(c){return CAT[c]||{label:c||'أخبار',emoji:'📰',cls:''}}
let state={cat:'all',q:'',page:1,loading:false,hasMore:true};
function esc(t){if(!t)return'';return String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function ago(ts){const d=Math.floor(Date.now()/1000)-ts;if(d<60)return'الآن';if(d<3600)return Math.floor(d/60)+' د';if(d<86400)return Math.floor(d/3600)+' س';return Math.floor(d/86400)+' ي';}
function impDots(n){n=Math.min(10,Math.max(1,n||5));const f=Math.round(n/2);return Array.from({length:5},(_,i)=>'<span class="imp-dot'+(i<f?' on':'')+'"></span>').join('');}
function skeletonCards(n=6){return Array(n).fill(0).map(()=>'<div class="sk-card"><div class="skeleton sk-img"></div><div class="sk-body"><div class="skeleton sk-line sk-full"></div><div class="skeleton sk-line sk-3q"></div><div class="skeleton sk-line sk-half"></div></div></div>').join('');}
function renderCard(a,idx){const c=catInfo(a.category);const title=esc(a.translated_title||a.title);const summary=esc(a.translated_summary||a.summary||'');const featured=idx===0&&state.page===1&&state.cat==='all'&&!state.q;const imgHtml=a.image_url?'<img src="'+esc(a.image_url)+'" alt="" loading="lazy" onerror="this.parentNode.querySelector(\'.card-img-fallback\').style.display=\'flex\';this.style.display=\'none\'">':"";return '<div class="card'+(featured?' featured':'')+'" onclick="openArt(\''+esc(a.url)+'\','+a.id+')" data-id="'+a.id+'">'
+'<div class="card-img">'+imgHtml+'<div class="card-img-fallback" style="display:'+(a.image_url?'none':'flex')+'">'+c.emoji+'</div><div class="img-gradient"></div><span class="card-badge '+c.cls+'">'+c.emoji+' '+c.label+'</span><div class="importance-badge">'+impDots(a.importance)+'</div></div>'
+'<div class="card-body"><div class="card-title">'+title+'</div>'+(summary?'<div class="card-summary">'+summary+'</div>':'')+'<div class="card-meta">'+(a.company?'<span class="company-tag">🏢 '+esc(a.company)+'</span>':'<span style="font-size:.67rem">📌 '+esc(a.source)+'</span>')+'<span>'+ago(a.published_at)+'</span></div></div>'
+'<div class="card-actions"><button class="action-btn btn-x" onclick="shareX(event,'+a.id+')">𝕏 شارك</button><button class="action-btn btn-read" onclick="openArt(\''+esc(a.url)+'\','+a.id+',event)">📖 اقرأ</button></div></div>';}
async function loadNews(reset=false){if(state.loading)return;state.loading=true;const grid=document.getElementById('grid');const btn=document.getElementById('refreshBtn');btn.classList.add('spinning');if(reset){state.page=1;state.hasMore=true;grid.innerHTML=skeletonCards();}try{let url='/api/news?limit=12&page='+state.page;if(state.cat!=='all')url+='&cat='+state.cat;if(state.q)url+='&q='+encodeURIComponent(state.q);const res=await fetch(url);const data=await res.json();const arts=data.articles||[];state.hasMore=!!data.hasMore;if(reset)grid.innerHTML='';const oldBtn=grid.querySelector('.load-more-wrap');if(oldBtn)oldBtn.remove();if(!arts.length&&state.page===1){grid.innerHTML='<div class="empty-state"><div class="empty-icon">🔍</div><h3>لا توجد أخبار</h3><p>جرّب فئة أخرى</p></div>';}else{arts.forEach((a,i)=>{const div=document.createElement('div');div.innerHTML=renderCard(a,i+(state.page-1)*12);grid.appendChild(div.firstElementChild);});if(state.hasMore){const w=document.createElement('div');w.className='load-more-wrap';w.innerHTML='<button class="load-more-btn" onclick="loadMore()">⬇️ تحميل المزيد</button>';grid.appendChild(w);}}
document.getElementById('liveText').textContent=arts.length+' خبر';}catch(e){if(reset)grid.innerHTML='<div class="empty-state"><div class="empty-icon">⚠️</div><h3>خطأ في الاتصال</h3></div>';}
state.loading=false;btn.classList.remove('spinning');}
function loadMore(){state.page++;loadNews(false);}
async function loadTrending(){try{const res=await fetch('/api/trending');const data=await res.json();const list=document.getElementById('trendingList');const arts=data.articles||[];if(!arts.length){list.innerHTML='<div style="padding:1rem;font-size:.78rem;color:var(--text2)">لا توجد أخبار رائجة</div>';return;}list.innerHTML=arts.slice(0,7).map((a,i)=>'<div class="tr-item" onclick="openArt(\''+esc(a.url)+'\','+a.id+')"><span class="tr-num">'+(i+1)+'</span><div><div class="tr-title">'+esc(a.translated_title||a.title)+'</div><div class="tr-meta">'+catInfo(a.category).emoji+' '+ago(a.published_at)+'</div></div></div>').join('');document.getElementById('tr-updated').textContent='محدّث الآن';}catch(e){}}
async function loadStats(){try{const[sR,cR]=await Promise.all([fetch('/api/stats'),fetch('/api/categories')]);const s=await sR.json();const cats=await cR.json();document.getElementById('s-total').textContent=(s.total_articles||0).toLocaleString('ar-SA');document.getElementById('s-24h').textContent=(s.last_24h||0).toLocaleString('ar-SA');document.getElementById('s-feeds').textContent=(s.active_feeds||0).toLocaleString('ar-SA');(cats.categories||[]).forEach(c=>{const el=document.getElementById('cnt-'+c.id);if(el&&c.count>0)el.textContent=c.count;});}catch(e){}}
async function shareX(event,id){event.stopPropagation();try{const res=await fetch('/api/share/'+id,{method:'POST'});const data=await res.json();if(data.intent_url){fetch('/api/news/'+id).then(r=>r.json()).then(d=>{if(d.article?.tweet_text)showTweetWidget(d.article);}).catch(()=>{});window.open(data.intent_url,'_blank','noopener');showToast('✅ فُتح تويتر للنشر');}}catch(e){showToast('❌ خطأ: '+e.message);}}
function showTweetWidget(a){const tweet=a.tweet_text||'';const box=document.getElementById('tweetBox');box.innerHTML='<div class="tweet-text">'+esc(tweet)+'</div><div class="tweet-chars"><span>'+tweet.length+'</span>/280 حرف</div><button class="copy-btn" onclick="copyTweet('+JSON.stringify(esc(tweet))+')" >📋 نسخ النص</button>';}
function copyTweet(txt){const raw=txt.replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"');navigator.clipboard.writeText(raw).then(()=>showToast('✅ تم النسخ!')).catch(()=>showToast('❌ تعذّر النسخ'));}
function openArt(url,id,event){if(event)event.stopPropagation();if(url)window.open(url,'_blank','noopener');}
function showToast(msg){const t=document.getElementById('toast');t.textContent=msg;t.classList.add('show');clearTimeout(t._timer);t._timer=setTimeout(()=>t.classList.remove('show'),3000);}
function refreshAll(){loadNews(true);loadTrending();loadStats();}
document.getElementById('catNav').addEventListener('click',e=>{const btn=e.target.closest('.cat-btn');if(!btn)return;document.querySelectorAll('.cat-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');state.cat=btn.dataset.cat;state.q='';document.getElementById('searchInput').value='';const titles={all:'🗞️ آخر الأخبار',ai:'🤖 أخبار الذكاء الاصطناعي',saudi:'🇸🇦 الأخبار السعودية',economy:'💰 أخبار الاقتصاد',global:'🌍 الأخبار العالمية',historical:'📜 أحداث تاريخية'};document.getElementById('sectionTitle').textContent=titles[state.cat]||'🗞️ آخر الأخبار';loadNews(true);});
let searchTimer;document.getElementById('searchInput').addEventListener('input',e=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{state.q=e.target.value.trim();state.cat='all';document.querySelectorAll('.cat-btn').forEach(b=>b.classList.remove('active'));document.querySelector('[data-cat="all"]').classList.add('active');document.getElementById('sectionTitle').textContent=state.q?'🔍 نتائج: '+state.q:'🗞️ آخر الأخبار';loadNews(true);},450);});
loadNews(true);loadTrending();loadStats();
setInterval(refreshAll,5*60*1000);
</script>
</body>
</html>`;
}

// ─── API Handlers ─────────────────────────────────────────────────────────────

async function handleApi(request, env, url) {
  const path = url.pathname;
  if (path === "/api/news" && request.method === "GET") return handleGetNews(request, env, url);
  const newsMatch = path.match(/^\/api\/news\/(\d+)$/);
  if (newsMatch && request.method === "GET") return handleGetSingleNews(parseInt(newsMatch[1]), env);
  const shareMatch = path.match(/^\/api\/share\/(\d+)$/);
  if (shareMatch && request.method === "POST") return handleShareNews(parseInt(shareMatch[1]), env);
  if (path === "/api/historical/today" && request.method === "GET") return handleHistoricalToday(env);
  if (path === "/api/categories" && request.method === "GET") return handleCategories(env);
  if (path === "/api/trending" && request.method === "GET") return handleTrending(env);
  if (path === "/api/pipeline/run" && request.method === "POST") { const stats = await runPipeline(env); return json({ ok: true, stats }); }
  if (path === "/api/backfill-images" && request.method === "POST") return handleBackfillImages(env);
  if (path === "/api/stats" && request.method === "GET") return handleStats(env);
  return json({ error: "Not found" }, 404);
}

async function handleGetNews(request, env, url) {
  const category = url.searchParams.get("cat") || "all";
  const region = url.searchParams.get("region");
  const query = url.searchParams.get("q")?.trim();
  const page = Math.max(1, parseInt(url.searchParams.get("page") || "1"));
  const perPage = Math.min(30, Math.max(5, parseInt(url.searchParams.get("limit") || "20")));
  const offset = (page - 1) * perPage;
  let sql = "", params = [];
  if (query) {
    sql = `SELECT a.id, a.source, a.source_url, a.url, a.title, a.translated_title, a.summary, a.translated_summary, a.tweet_text, a.image_url, a.video_url, a.category, a.region, a.company, a.hashtags, a.importance, a.published_at, a.created_at, a.views, a.shares FROM articles_fts fts JOIN articles a ON a.id = fts.rowid WHERE articles_fts MATCH ?`;
    params.push(query + "*");
    if (category !== "all") { if (category === "global") { sql += " AND a.category NOT IN ('saudi', 'historical')"; } else { sql += " AND a.category = ?"; params.push(category); } }
    if (region) { sql += " AND a.region = ?"; params.push(region); }
    sql += " ORDER BY a.published_at DESC LIMIT ? OFFSET ?";
  } else {
    sql = `SELECT id, source, source_url, url, title, translated_title, summary, translated_summary, tweet_text, image_url, video_url, category, region, company, hashtags, importance, published_at, created_at, views, shares FROM articles WHERE 1=1`;
    if (category !== "all") { if (category === "global") { sql += " AND category NOT IN ('saudi', 'historical')"; } else { sql += " AND category = ?"; params.push(category); } }
    if (region) { sql += " AND region = ?"; params.push(region); }
    sql += " ORDER BY published_at DESC LIMIT ? OFFSET ?";
  }
  params.push(perPage, offset);
  const result = await env.DB.prepare(sql).bind(...params).all();
  const articles = result.results.map(a => ({ ...a, hashtags: a.hashtags ? safeJsonParse(a.hashtags, []) : [] }));
  return json({ articles, page, perPage, hasMore: articles.length === perPage });
}

async function handleGetSingleNews(id, env) {
  const article = await env.DB.prepare(`SELECT * FROM articles WHERE id = ? LIMIT 1`).bind(id).first();
  if (!article) return json({ error: "Not found" }, 404);
  await env.DB.prepare(`UPDATE articles SET views = views + 1 WHERE id = ?`).bind(id).run();
  return json({ article: { ...article, hashtags: article.hashtags ? safeJsonParse(article.hashtags, []) : [] } });
}

async function handleShareNews(id, env) {
  const article = await env.DB.prepare(`SELECT tweet_text, url, hashtags FROM articles WHERE id = ? LIMIT 1`).bind(id).first();
  if (!article) return json({ error: "Not found" }, 404);
  await env.DB.prepare(`UPDATE articles SET shares = shares + 1 WHERE id = ?`).bind(id).run();
  const hashtags = safeJsonParse(article.hashtags || "[]", []).map(t => t.replace(/^#/, "")).slice(0, 5).join(",");
  const intentUrl = new URL("https://twitter.com/intent/tweet");
  intentUrl.searchParams.set("text", article.tweet_text || "");
  if (article.url) intentUrl.searchParams.set("url", article.url);
  if (hashtags) intentUrl.searchParams.set("hashtags", hashtags);
  return json({ ok: true, intent_url: intentUrl.toString() });
}

async function handleHistoricalToday(env) {
  const now = new Date();
  const dateKey = `${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const result = await env.DB.prepare(`SELECT id, event_date, event_year, title_ar, description_ar, image_url, category, source_url FROM historical_events WHERE event_date = ? ORDER BY event_year DESC`).bind(dateKey).all();
  return json({ date: dateKey, events: result.results });
}

async function handleCategories(env) {
  const result = await env.DB.prepare(`SELECT category, COUNT(*) as count FROM articles WHERE published_at > ? GROUP BY category`).bind(Math.floor(Date.now() / 1000) - 86400 * 7).all();
  return json({ categories: [{ id: "all", name: "الكل", count: 0 },{ id: "ai", name: "AI", count: 0 },{ id: "saudi", name: "Saudi", count: 0 },{ id: "economy", name: "Economy", count: 0 },{ id: "global", name: "Global", count: 0 },{ id: "historical", name: "Historical", count: 0 }].map(cat => { const found = result.results.find(r => r.category === cat.id); return { ...cat, count: found?.count || 0 }; }) });
}

async function handleTrending(env) {
  const result = await env.DB.prepare(`SELECT id, source, url, title, translated_title, translated_summary, tweet_text, image_url, category, region, company, hashtags, importance, published_at, views, shares FROM articles WHERE published_at > ? ORDER BY importance DESC, views DESC LIMIT 10`).bind(Math.floor(Date.now() / 1000) - 86400).all();
  return json({ articles: result.results.map(a => ({ ...a, hashtags: a.hashtags ? safeJsonParse(a.hashtags, []) : [] })) });
}

async function handleStats(env) {
  const [total, last24h, feeds, lastUpdate] = await Promise.all([
    env.DB.prepare(`SELECT COUNT(*) as count FROM articles`).first(),
    env.DB.prepare(`SELECT COUNT(*) as count FROM articles WHERE created_at > ?`).bind(Math.floor(Date.now() / 1000) - 86400).first(),
    env.DB.prepare(`SELECT COUNT(*) as count FROM feeds WHERE active = 1`).first(),
    env.DB.prepare(`SELECT MAX(created_at) as last_update FROM articles`).first()
  ]);
  return json({ total_articles: total?.count || 0, last_24h: last24h?.count || 0, active_feeds: feeds?.count || 0, last_update: lastUpdate?.last_update || null, server_time: new Date().toISOString() });
}

async function handleBackfillImages(env) {
  const rows = await env.DB.prepare(`SELECT id, url FROM articles WHERE image_url IS NULL AND url NOT LIKE '%news.google.com%' AND url NOT LIKE '%huggingface.co%' ORDER BY published_at DESC LIMIT 50`).all();
  let updated = 0, errors = [];
  for (const row of rows.results) {
    try { const img = await fetchOgImage(row.url); if (img) { await env.DB.prepare(`UPDATE articles SET image_url = ? WHERE id = ?`).bind(img, row.id).run(); updated++; } }
    catch (e) { errors.push(`${row.id}: ${e}`); }
  }
  return json({ ok: true, total: rows.results.length, updated, errors });
}

function safeJsonParse(text, fallback) {
  try { return JSON.parse(text); } catch { return fallback; }
}

// ─── Worker Entry ─────────────────────────────────────────────────────────────

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const origin = request.headers.get("origin") || "";
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }
    if (url.pathname === "/" || url.pathname === "/index.html" || url.pathname === "") {
      return new Response(getHtml(), {
        headers: { "content-type": "text/html; charset=utf-8", "cache-control": "public, max-age=300, s-maxage=600", "x-content-type-options": "nosniff" }
      });
    }
    if (url.pathname.startsWith("/api/")) {
      try {
        const rateLimitResult = await env.API_LIMITER.limit({ key: request.headers.get("cf-connecting-ip") || "unknown" });
        if (!rateLimitResult.success) return json({ error: "Too many requests" }, 429, corsHeaders(origin));
      } catch {}
      const response = await handleApi(request, env, url);
      const newHeaders = new Headers(response.headers);
      Object.entries(corsHeaders(origin)).forEach(([k, v]) => newHeaders.set(k, v));
      return new Response(response.body, { status: response.status, headers: newHeaders });
    }
    if (env.ASSETS) return env.ASSETS.fetch(request);
    return new Response("Not found", { status: 404 });
  },
  async scheduled(event, env, ctx) {
    console.log(`[cron] ${new Date().toISOString()} — بدء الجلب`);
    try { const stats = await runPipeline(env); console.log("[cron] انتهى:", stats); }
    catch (err) { console.error("[cron] خطأ:", err); }
  }
};
