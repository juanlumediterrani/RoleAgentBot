#!/bin/bash

# Test script for YouTube cookies functionality
echo "🎵 Testing YouTube cookies setup..."

# Check if cookies.txt exists
if [ ! -f "cookies.txt" ]; then
    echo "❌ cookies.txt not found!"
    echo "📝 Please create cookies.txt file:"
    echo "   1. Install 'Get cookies.txt' browser extension"
    echo "   2. Login to YouTube"
    echo "   3. Export cookies as Netscape format"
    echo "   4. Save as cookies.txt"
    echo ""
    echo "📄 See cookies.txt.example for format reference"
    exit 1
fi

echo "✅ cookies.txt found"

# Check if cookies.txt has content
if [ ! -s "cookies.txt" ]; then
    echo "❌ cookies.txt is empty!"
    exit 1
fi

echo "✅ cookies.txt has content"

# Check if it's a valid Netscape format
if ! head -1 cookies.txt | grep -q "^#"; then
    echo "❌ Invalid cookie format! Should start with # (Netscape format)"
    exit 1
fi

echo "✅ Valid Netscape cookie format"

# Check for YouTube cookies
if ! grep -q "youtube.com" cookies.txt; then
    echo "❌ No YouTube cookies found!"
    echo "🔍 Make sure you export cookies from YouTube"
    exit 1
fi

echo "✅ YouTube cookies found"

# Count YouTube cookies
youtube_cookies=$(grep "youtube.com" cookies.txt | wc -l)
echo "📊 Found $youtube_cookies YouTube cookies"

echo ""
echo "🎉 Cookie file validation passed!"
echo ""
echo "🐳 To test with Docker:"
echo "   docker compose -f docker/docker-compose.dev.yml up --build"
echo ""
echo "🎵 To test cookies in Discord:"
echo "   !mc test_cookies"
