# Bug: Videos tab shows 0 videos

## Root cause

In `src/pipeline.ts`, the article object built during the pipeline run never sets
`media_type`. The INSERT statement also omits `media_type`, so every article
lands in the DB with the column's default value (`'article'`), including ones
that have a `video_url`.

The `/api/videos` endpoint queries:
```sql
WHERE media_type = 'video' AND video_url IS NOT NULL
```
Because `media_type` is always `'article'`, it returns 0 rows.

## Fix in pipeline.ts

Add `media_type` to the article object:
```diff
 const article = {
   guid_hash,
   source: feed.name,
+  media_type: videoUrl ? 'video' : 'article',
   ...
   video_url: videoUrl,
```

Add `media_type` to the INSERT statement:
```diff
 `INSERT OR IGNORE INTO articles (
-   guid_hash, source, source_url, url, title, translated_title,
+   guid_hash, source, source_url, url, title, translated_title, media_type,
    summary, translated_summary, why_matters, tweet_text,
    image_url, video_url, category, region, company, hashtags,
    importance, published_at, is_saudi
- ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
+ ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
```
And bind `a.media_type` in the correct position in the `.bind()` call.

## Data fix applied

The SQL in `fix_video_media_type.sql` was already executed against the
production D1 database, correcting all 14 existing video articles.
