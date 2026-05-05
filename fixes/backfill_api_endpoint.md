# One-time backfill endpoint for missing images

Add this to `src/index.ts` inside `handleApi()` to fix existing articles.
Call it once with `POST /api/backfill-images`, then remove it.

```ts
// ── Temporary: backfill og:image for articles without images ─────────────
if (path === "/api/backfill-images" && request.method === "POST") {
  const authHeader = request.headers.get("authorization");
  if (authHeader !== `Bearer ${env.ADMIN_SECRET}`) {
    return json({ error: "Unauthorized" }, 401);
  }
  return handleBackfillImages(env);
}
```

Add the handler function:

```ts
async function handleBackfillImages(env: Env) {
  const rows = await env.DB.prepare(
    `SELECT id, url FROM articles
     WHERE image_url IS NULL
       AND url NOT LIKE '%news.google.com%'
       AND url NOT LIKE '%huggingface.co%'
     ORDER BY published_at DESC
     LIMIT 50`
  ).all();

  let updated = 0;
  const errors: string[] = [];

  for (const row of rows.results as { id: number; url: string }[]) {
    try {
      const img = await fetchOgImage(row.url);
      if (img) {
        await env.DB.prepare(
          `UPDATE articles SET image_url = ? WHERE id = ?`
        ).bind(img, row.id).run();
        updated++;
      }
    } catch (e) {
      errors.push(`${row.id}: ${e}`);
    }
  }

  return json({ ok: true, total: rows.results.length, updated, errors });
}
```

## Usage

```bash
curl -X POST https://fahadai-news.aboamran2013.workers.dev/api/backfill-images \
  -H "Authorization: Bearer YOUR_ADMIN_SECRET"
```

Run multiple times until updated count is 0 (50 articles per call).
Remove the endpoint after backfill is complete.
