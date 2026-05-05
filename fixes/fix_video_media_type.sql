-- Fix: articles with video_url were inserted without media_type = 'video'
-- The pipeline INSERT never set media_type, leaving it as the default 'article'
-- even when video_url was populated.
--
-- This updates all existing records to reflect the correct media_type.

UPDATE articles
SET media_type = 'video'
WHERE video_url IS NOT NULL
  AND (media_type IS NULL OR media_type != 'video');
