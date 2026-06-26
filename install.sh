#!/bin/bash
set -e

echo "=============================="
echo "  Installing dependencies..."
echo "=============================="

pip install \
    "python-telegram-bot[rate-limiter]==20.8" \
    "openai>=1.40.0,<2.0.0" \
    "tiktoken>=0.7.0" \
    "PyYAML==6.0.2" \
    "pymongo==4.6.3" \
    "python-dotenv==1.2.2"

echo ""
echo "=============================="
echo "  Setting up MongoDB..."
echo "=============================="

mkdir -p /home/runner/mongodb_data

echo ""
echo "=============================="
echo "  Checking environment vars..."
echo "=============================="

MISSING=0
for VAR in TELEGRAM_TOKEN OPENAI_API_KEY MONGODB_URI OPENAI_API_BASE MONGODB_DATABASE; do
    if [ -z "${!VAR}" ]; then
        echo "  [MISSING] $VAR"
        MISSING=1
    else
        echo "  [OK]      $VAR"
    fi
done

if [ "$MISSING" -eq 1 ]; then
    echo ""
    echo "WARNING: Ada env var yang belum diisi. Set dulu sebelum jalankan bot."
else
    echo ""
    echo "Semua env var lengkap."
fi

echo ""
echo "=============================="
echo "  Install selesai!"
echo "  Jalankan: bash start.sh"
echo "=============================="
