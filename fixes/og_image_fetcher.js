/**
 * Add this function to src/utils.ts in the Cloudflare Worker project.
 *
 * Fetches the og:image from an article URL when no image was found in RSS.
 * Uses Cloudflare's cache to avoid re-fetching the same page.
 */
export async function fetchOgImage(url) {
  if (!url || url.includes("news.google.com") || url.includes("huggingface.co/papers")) {
    return null;
  }
  try {
    const res = await fetch(url, {
      method: "GET",
      headers: {
        "User-Agent": "Mozilla/5.0 (compatible; fahadai-news/1.0; +https://fahadai.news)",
        Accept: "text/html",
      },
      signal: AbortSignal.timeout(5000),
      cf: { cacheTtl: 86400, cacheEverything: true },
    });
    if (!res.ok) return null;
    // Read only the first 8KB — og:image is always in <head>
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
