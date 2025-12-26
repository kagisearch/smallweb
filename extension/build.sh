#!/bin/bash
# Build script for Kagi Small Web Browser Extension
# Generates both Chrome and Firefox versions

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Clean previous builds
rm -rf dist
mkdir -p dist/chrome dist/firefox

# Common files for both browsers
COMMON_FILES=(
  "background.js"
  "sidepanel.html"
  "sidepanel.css"
  "sidepanel.js"
  "icons"
)

echo "Building Chrome extension..."
# Chrome uses manifest.json directly
cp manifest.json dist/chrome/
for file in "${COMMON_FILES[@]}"; do
  cp -r "$file" dist/chrome/
done

echo "Building Firefox extension..."
# Firefox uses manifest.firefox.json renamed to manifest.json
cp manifest.firefox.json dist/firefox/manifest.json
# Firefox needs the browser polyfill
cp browser-polyfill.js dist/firefox/
for file in "${COMMON_FILES[@]}"; do
  cp -r "$file" dist/firefox/
done

# Update Firefox sidepanel.html to include polyfill
sed -i '' 's|<script src="sidepanel.js"></script>|<script src="browser-polyfill.js"></script>\n  <script src="sidepanel.js"></script>|' dist/firefox/sidepanel.html

echo ""
echo "Build complete!"
echo "  Chrome: dist/chrome/"
echo "  Firefox: dist/firefox/"
echo ""
echo "To install:"
echo "  Chrome: chrome://extensions -> Load unpacked -> select dist/chrome"
echo "  Firefox: about:debugging -> This Firefox -> Load Temporary Add-on -> select dist/firefox/manifest.json"
echo ""

# Create zip files for distribution
if command -v zip &> /dev/null; then
  echo "Creating distribution packages..."
  cd dist/chrome && zip -r ../smallweb-chrome.zip . -x "*.DS_Store" && cd ../..
  cd dist/firefox && zip -r ../smallweb-firefox.zip . -x "*.DS_Store" && cd ../..
  echo "  dist/smallweb-chrome.zip"
  echo "  dist/smallweb-firefox.zip"
fi
