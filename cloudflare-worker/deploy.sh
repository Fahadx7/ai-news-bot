#!/bin/bash
# انشر الـ Worker بأمر واحد
# الاستخدام: CLOUDFLARE_API_TOKEN=xxx bash deploy.sh

export CLOUDFLARE_ACCOUNT_ID=1bc5df038fffdc6706a3423eba2d7718

cd "$(dirname "$0")"
npx wrangler deploy worker.js \
  --name fahadai-news \
  --compatibility-date 2024-01-01

echo "✅ تم النشر على https://fahadai-news.aboamran2013.workers.dev/"
