# Kagi Small Web Browser Extension

A browser extension that brings the Small Web discovery experience directly to your browser, without iframes.

## Features

- **Direct Navigation**: Sites load directly in your browser tab - no iframe restrictions
- **Side Panel UI**: Compact, always-accessible panel for discovery
- **Session History**: Track visited sites during your browsing session
- **Multiple Modes**: Switch between Blogs, Videos, GitHub, and Comics
- **Keyboard Support**: Press Space or Enter to load the next post

## Installation

### Chrome

1. Open `chrome://extensions/`
2. Enable "Developer mode" (toggle in top right)
3. Click "Load unpacked"
4. Select the `extension` folder

### Firefox

Firefox requires manifest v2 with `sidebar_action`. A Firefox-compatible version would need:
- Change `manifest_version` to `2`
- Replace `side_panel` with `sidebar_action`
- Replace `chrome.*` APIs with `browser.*` APIs

## Usage

1. Click the extension icon to open the side panel
2. Click "NEXT POST" to navigate to a random blog/video/project
3. Use the mode buttons to switch content types
4. Your session history is saved locally for easy backtracking

## Why an Extension?

As Chris Coyier noted, the iframe approach has limitations:
- Some sites block iframing (X-Frame-Options/CSP)
- URLs aren't in the address bar (can't bookmark/share easily)
- Browser back/forward don't work as expected
- Sites can't be added to browsing history

This extension solves all of these by navigating directly to sites while providing a persistent UI panel.

## Privacy

- No user data is sent to any server
- Session history is stored locally in browser storage
- Reactions are currently local-only (future: sync with Kagi)
