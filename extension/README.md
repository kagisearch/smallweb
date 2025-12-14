# Kagi Small Web Browser Extension

Discover the indie web directly in your browser. Random posts from personal blogs, YouTube creators, GitHub projects, and webcomics.

## Features

- **Discover**: Random posts from curated indie content
- **Multiple Modes**: Blogs, Appreciated, Videos, Code, Comics, Saved
- **Reader Mode**: Clean reading experience with optional dyslexia-friendly font
- **Text-to-Speech**: Listen to articles hands-free
- **Save for Later**: Bookmark posts to your local collection
- **Appreciate**: Send appreciation to content creators
- **History**: Per-mode browsing history
- **Keyboard Shortcuts**:
  - `Space` - Discover next post
  - `R` - Toggle reader mode
  - `S` - Save/unsave post
  - `T` - Toggle text-to-speech
  - `D` - Toggle dyslexia font

## Installation

### Chrome

1. Download `smallweb-chrome.zip` from dist/
2. Unzip the file
3. Open `chrome://extensions/`
4. Enable "Developer mode" (toggle in top right)
5. Click "Load unpacked"
6. Select the unzipped folder

### Firefox

1. Download `smallweb-firefox.zip` from dist/
2. Open `about:debugging#/runtime/this-firefox`
3. Click "Load Temporary Add-on"
4. Select the zip file or manifest.json inside

## Building from Source

```bash
cd extension
./build.sh
```

Outputs:
- `dist/chrome/` - Chrome extension
- `dist/firefox/` - Firefox extension
- `dist/smallweb-chrome.zip` - Chrome distribution
- `dist/smallweb-firefox.zip` - Firefox distribution

## Usage

1. Click the extension icon to open the side panel
2. Click "Discover" to navigate to a random post
3. Use mode tabs to switch content types (hover for item counts)
4. Enable Reader Mode for distraction-free reading
5. Save posts you want to revisit later

## Privacy

- All data stored locally in browser storage
- No tracking or analytics
- Referrer set to kagi.com/smallweb for proper attribution
