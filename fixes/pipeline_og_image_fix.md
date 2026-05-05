# Fix: Articles showing emoji placeholders instead of real images

## Problem

68% of articles (440/647) have no `image_url`. The main offenders:

| Source                      | Articles | Images |
|-----------------------------|----------|--------|
| Google News - السعودية      | 132      | 0      |
| HuggingFace Papers          | 80       | 0      |
| TechCrunch                  | 74       | 0      |
| TechCrunch AI               | 59       | 0      |
| Google News - الاقتصاد      | 27       | 0      |

Google News and many RSS feeds strip images. The article pages themselves
have `og:image` meta tags with real images.

## Fix in src/pipeline.ts

### Step 1 — Import the helper

Add `fetchOgImage` to `src/utils.ts` (see `og_image_fetcher.js`),
then import it at the top of `src/pipeline.ts`:

```ts
import { fetchOgImage } from "./utils";
```

### Step 2 — Use it during article processing

Find the block that builds `image_url` (~line where `videoId` is used):

```diff
-const image_url =
-  (videoId ? `https://img.youtube.com/vi/${videoId}/maxresdefault.jpg` : null) ||
-  item.image ||
-  null;
+let image_url =
+  (videoId ? `https://img.youtube.com/vi/${videoId}/maxresdefault.jpg` : null) ||
+  item.image ||
+  null;
+
+// Fetch og:image when RSS provides no image
+if (!image_url) {
+  image_url = await fetchOgImage(isCleanUrl(cleanUrl) ? cleanUrl : item.link);
+}
```

### Why this works

- `fetchOgImage` reads only the first 8 KB of the page (og:image is in <head>)
- Uses Cloudflare's edge cache (`cacheTtl: 86400`) so the same URL is only
  fetched once per day even across multiple pipeline runs
- Skips Google News URLs (unresolvable without browser) and HuggingFace Papers
  (no og:image)
- Falls back gracefully (returns null) on timeout or error

### Performance impact

The pipeline already calls `resolveRedirect` and `translateArticle` per article,
so one extra cached fetch per article is acceptable. Set a 5-second timeout to
avoid blocking the pipeline.
