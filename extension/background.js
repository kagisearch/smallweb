// Kagi Small Web - Background Service Worker / Script
// Works with both Chrome (Manifest V3) and Firefox (Manifest V2)

const IS_FIREFOX = typeof browser !== 'undefined' && browser.runtime?.getBrowserInfo;
const api = typeof browser !== 'undefined' ? browser : chrome;

const API_BASE = 'https://kagi.com/api/v1/smallweb/feed/';
const SMALLWEB_BASE = 'https://kagi.com/smallweb';
const SMALLWEB_REFERRER = 'https://kagi.com/smallweb/';
const CACHE_DURATION = 3 * 60 * 60 * 1000; // 3 hours
const REFRESH_INTERVAL = 60 * 60 * 1000; // 1 hour
const READER_ID = 'smallweb-reader-mode';

// Track URLs for referrer modification
const pendingNavigations = new Set();
let nextRuleId = 1;

// Track tabs needing reader mode after navigation
const pendingReaderMode = new Map(); // tabId -> { dyslexia: boolean, attempts: number }

// Feed cache
let cache = {
  blogs: { entries: [], lastFetch: 0 },
  youtube: { entries: [], lastFetch: 0 },
  github: { entries: [], lastFetch: 0 },
  comics: { entries: [], lastFetch: 0 },
  appreciated: { entries: [], lastFetch: 0 },
  saved: { entries: [], lastFetch: 0 }
};

// Next post queue
let nextQueue = {
  blogs: null,
  youtube: null,
  github: null,
  comics: null,
  appreciated: null,
  saved: null
};

// Track ongoing fetches
const fetchingModes = new Map();

// ═══════════════════════════════════════
// SAVED POSTS
// ═══════════════════════════════════════

async function loadSavedPosts() {
  const result = await api.storage.local.get(['savedPosts']);
  cache.saved.entries = result.savedPosts || [];
  prepareNext('saved');
}

async function savePost(post) {
  await loadSavedPosts();
  if (cache.saved.entries.some(p => p.link === post.link)) {
    return { success: true, alreadySaved: true };
  }
  cache.saved.entries.unshift({ ...post, savedAt: Date.now() });
  cache.saved.entries = cache.saved.entries.slice(0, 100);
  await api.storage.local.set({ savedPosts: cache.saved.entries });
  prepareNext('saved');
  return { success: true, alreadySaved: false };
}

async function unsavePost(url) {
  await loadSavedPosts();
  cache.saved.entries = cache.saved.entries.filter(p => p.link !== url);
  await api.storage.local.set({ savedPosts: cache.saved.entries });
  prepareNext('saved');
  return { success: true };
}

async function isPostSaved(url) {
  await loadSavedPosts();
  return cache.saved.entries.some(p => p.link === url);
}

// ═══════════════════════════════════════
// FEED PARSING & FETCHING
// ═══════════════════════════════════════

function parseFeed(text) {
  const entries = [];
  const entryRegex = /<entry[^>]*>([\s\S]*?)<\/entry>/g;
  let match;

  while ((match = entryRegex.exec(text)) !== null) {
    const xml = match[1];
    const title = xml.match(/<title[^>]*>([^<]*)<\/title>/)?.[1] || 'Untitled';
    const link = xml.match(/<link[^>]*href="([^"]+)"/)?.[1] || '';
    const author = xml.match(/<author>\s*<name>([^<]*)<\/name>/)?.[1] || '';

    if (link?.startsWith('https://')) {
      try {
        const domain = new URL(link).hostname.replace(/^www\./, '');
        entries.push({ title: decodeXml(title), link, author: decodeXml(author), domain });
      } catch (e) {}
    }
  }
  return entries;
}

function decodeXml(text) {
  return text
    .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&#8217;/g, "'")
    .replace(/&#8211;/g, "–").replace(/&#(\d+);/g, (_, n) => String.fromCharCode(+n));
}

const FEED_URLS = {
  blogs: API_BASE + '?nso',
  youtube: API_BASE + '?yt',
  github: API_BASE + '?gh',
  comics: API_BASE + '?comic',
  appreciated: SMALLWEB_BASE + '/appreciated'
};

function fetchFeed(mode) {
  if (mode === 'saved') return Promise.resolve();
  if (fetchingModes.has(mode)) return fetchingModes.get(mode);

  const promise = (async () => {
    try {
      const response = await fetch(FEED_URLS[mode]);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      let entries = parseFeed(await response.text());
      if (mode === 'youtube') entries = entries.filter(e => !e.link.includes('/shorts/'));
      cache[mode] = { entries, lastFetch: Date.now() };
      prepareNext(mode);
    } catch (e) {
      console.error(`[Feed] ${mode}:`, e.message);
    } finally {
      fetchingModes.delete(mode);
    }
  })();

  fetchingModes.set(mode, promise);
  return promise;
}

function refreshIfStale(mode) {
  if (mode !== 'saved' && Date.now() - cache[mode].lastFetch > CACHE_DURATION) {
    fetchFeed(mode);
  }
}

async function ensureFeedLoaded(mode) {
  if (mode === 'saved') {
    await loadSavedPosts();
    return cache.saved.entries;
  }
  if (cache[mode].entries.length > 0) {
    refreshIfStale(mode);
    return cache[mode].entries;
  }
  await fetchFeed(mode);
  return cache[mode].entries;
}

// Background refresh
setInterval(() => {
  Object.keys(FEED_URLS).forEach(refreshIfStale);
}, REFRESH_INTERVAL);

// ═══════════════════════════════════════
// POST QUEUE
// ═══════════════════════════════════════

function pickRandom(mode) {
  const entries = cache[mode].entries;
  return entries.length ? entries[Math.floor(Math.random() * entries.length)] : null;
}

function prepareNext(mode) {
  nextQueue[mode] = pickRandom(mode);
}

function getNextPost(mode) {
  const post = nextQueue[mode] || pickRandom(mode);
  prepareNext(mode);
  return post;
}

function getPreloadUrl(mode) {
  return nextQueue[mode]?.link || null;
}

// ═══════════════════════════════════════
// APPRECIATE
// ═══════════════════════════════════════

async function appreciatePost(url) {
  try {
    const formData = new FormData();
    formData.append('url', url);
    formData.append('emoji', '👍');
    const response = await fetch(SMALLWEB_BASE + '/favorite', {
      method: 'POST', body: formData, credentials: 'include'
    });
    cache.appreciated.lastFetch = 0;
    return response.ok;
  } catch (e) {
    return false;
  }
}

// ═══════════════════════════════════════
// TAB SCRIPT INJECTION
// ═══════════════════════════════════════

async function runInTab(tabId, func, args = []) {
  try {
    if (IS_FIREFOX) {
      const code = `(${func.toString()})(${args.map(a => JSON.stringify(a)).join(',')})`;
      const results = await api.tabs.executeScript(tabId, { code });
      return results[0];
    } else {
      const results = await chrome.scripting.executeScript({
        target: { tabId }, func, args
      });
      return results[0]?.result;
    }
  } catch (e) {
    return null;
  }
}

// ═══════════════════════════════════════
// REFERRER ATTRIBUTION
// ═══════════════════════════════════════

async function setReferrerForUrl(url) {
  if (!url) return;

  if (IS_FIREFOX) {
    pendingNavigations.add(url);
    setTimeout(() => pendingNavigations.delete(url), 30000);
  } else {
    const ruleId = nextRuleId++;
    try {
      await chrome.declarativeNetRequest.updateDynamicRules({
        addRules: [{
          id: ruleId, priority: 1,
          action: { type: 'modifyHeaders', requestHeaders: [{ header: 'Referer', operation: 'set', value: SMALLWEB_REFERRER }] },
          condition: { urlFilter: url, resourceTypes: ['main_frame'] }
        }],
        removeRuleIds: []
      });
      setTimeout(async () => {
        try { await chrome.declarativeNetRequest.updateDynamicRules({ removeRuleIds: [ruleId] }); } catch (e) {}
      }, 30000);
    } catch (e) {}
  }
}

if (IS_FIREFOX) {
  api.webRequest.onBeforeSendHeaders.addListener(
    (details) => {
      if (details.type !== 'main_frame' || !pendingNavigations.has(details.url)) {
        return { requestHeaders: details.requestHeaders };
      }
      pendingNavigations.delete(details.url);
      let found = false;
      for (const h of details.requestHeaders) {
        if (h.name.toLowerCase() === 'referer') { h.value = SMALLWEB_REFERRER; found = true; break; }
      }
      if (!found) details.requestHeaders.push({ name: 'Referer', value: SMALLWEB_REFERRER });
      return { requestHeaders: details.requestHeaders };
    },
    { urls: ['<all_urls>'] },
    ['blocking', 'requestHeaders']
  );
}

// ═══════════════════════════════════════
// READER MODE (consolidated)
// ═══════════════════════════════════════

// Single reader mode function to inject - handles all cases
const readerModeScript = (dyslexia, hideFirst, removeOnly) => {
  const READER_ID = 'smallweb-reader-mode';
  const HIDE_ID = 'smallweb-reader-hide';

  // Remove existing
  const existing = document.getElementById(READER_ID);
  if (existing) {
    existing.remove();
    if (removeOnly) return { enabled: false };
  }

  // If just removing (toggle off), we're done
  if (removeOnly) return { enabled: false };

  // Hide body first if requested (prevents flash)
  if (hideFirst) {
    const hide = document.createElement('style');
    hide.id = HIDE_ID;
    hide.textContent = 'body { visibility: hidden !important; }';
    document.documentElement.appendChild(hide);
  }

  // Check readability
  const isReadable = () => {
    const results = {};
    for (const sel of ['article', 'main', '.post', '.content', '.entry', '[role="main"]']) {
      const el = document.querySelector(sel);
      if (el) {
        const len = el.innerText.trim().length;
        results[sel] = len;
        if (len > 200) return { readable: true, selector: sel, length: len };
      }
    }
    const bodyLen = (document.body.innerText || '').trim().length;
    results.body = bodyLen;
    if (bodyLen > 500) return { readable: true, selector: 'body', length: bodyLen };
    return { readable: false, results };
  };

  const readableCheck = isReadable();
  console.log('[SmallWeb] isReadable check:', readableCheck);

  if (!readableCheck.readable) {
    const h = document.getElementById(HIDE_ID);
    if (h) h.remove();
    return { enabled: false, notReadable: true, debug: readableCheck };
  }

  // Generate CSS
  const fontFace = dyslexia ? `
    @font-face { font-family: 'OpenDyslexic'; src: url('https://cdn.jsdelivr.net/npm/open-dyslexic@1.0.3/woff/OpenDyslexic-Regular.woff') format('woff'); font-weight: normal; }
    @font-face { font-family: 'OpenDyslexic'; src: url('https://cdn.jsdelivr.net/npm/open-dyslexic@1.0.3/woff/OpenDyslexic-Bold.woff') format('woff'); font-weight: bold; }
  ` : '';
  const font = dyslexia ? "'OpenDyslexic', Georgia, serif" : "Georgia, 'Times New Roman', serif";
  const headingFont = dyslexia ? "'OpenDyslexic', sans-serif" : "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";

  const style = document.createElement('style');
  style.id = READER_ID;
  style.textContent = `
    ${fontFace}
    body {
      max-width: 700px !important; margin: 0 auto !important; padding: 20px 24px !important;
      font-family: ${font} !important; font-size: 19px !important; line-height: 1.8 !important;
      color: #333 !important; background: #fafafa !important;
      letter-spacing: ${dyslexia ? '0.05em' : 'normal'} !important;
      word-spacing: ${dyslexia ? '0.1em' : 'normal'} !important;
      visibility: visible !important;
    }
    img { max-width: 100% !important; height: auto !important; }
    pre, code { font-size: 14px !important; overflow-x: auto !important; }
    nav, header, footer, aside, .sidebar, .nav, .menu, .ads, .advertisement,
    .social-share, .comments, .related-posts, [class*="sidebar"], [class*="widget"],
    [class*="banner"], [class*="popup"], [class*="modal"], [id*="sidebar"],
    [id*="nav"], [id*="menu"], [id*="footer"] { display: none !important; }
    a { color: #ea580c !important; }
    h1, h2, h3, h4, h5, h6 { font-family: ${headingFont} !important; line-height: 1.4 !important; margin-top: 1.5em !important; }
    p, li { margin-bottom: 1.2em !important; }
  `;
  document.head.appendChild(style);

  // Remove hide style
  const h = document.getElementById(HIDE_ID);
  if (h) h.remove();

  return { enabled: true };
};

// ═══════════════════════════════════════
// TOOLBAR BUTTON
// ═══════════════════════════════════════

if (IS_FIREFOX) {
  api.browserAction.onClicked.addListener(() => api.sidebarAction.toggle());
} else {
  chrome.action.onClicked.addListener((tab) => chrome.sidePanel.open({ windowId: tab.windowId }));
}

// ═══════════════════════════════════════
// MESSAGE HANDLER
// ═══════════════════════════════════════

async function handleMessage(message) {
  const { type } = message;

  if (type === 'init') {
    try {
      await Promise.all(['blogs', 'youtube', 'github', 'comics', 'appreciated'].map(ensureFeedLoaded));
      const mode = message.mode || 'blogs';
      return { ready: cache[mode].entries.length > 0, preloadUrl: getPreloadUrl(mode) };
    } catch (e) {
      return { ready: false, error: e.message };
    }
  }

  if (type === 'getCounts') {
    await loadSavedPosts();
    return {
      blogs: cache.blogs.entries.length,
      appreciated: cache.appreciated.entries.length,
      youtube: cache.youtube.entries.length,
      github: cache.github.entries.length,
      comics: cache.comics.entries.length,
      saved: cache.saved.entries.length
    };
  }

  if (type === 'getNextPost') {
    const mode = message.mode || 'blogs';
    await (mode === 'saved' ? loadSavedPosts() : ensureFeedLoaded(mode));
    return { post: getNextPost(mode), preloadUrl: getPreloadUrl(mode) };
  }

  if (type === 'getPreloadUrl') {
    return { preloadUrl: getPreloadUrl(message.mode || 'blogs') };
  }

  if (type === 'navigate') {
    const tabs = await api.tabs.query({ active: true, currentWindow: true });
    if (tabs[0]) {
      const tabId = tabs[0].id;
      const useReader = message.readerMode === true;
      const useDyslexia = message.dyslexia === true;

      console.log('[SmallWeb] navigate:', { url: message.url, useReader, useDyslexia, tabId });

      // Queue reader mode to apply after page loads
      if (useReader) {
        pendingReaderMode.set(tabId, { dyslexia: useDyslexia, attempts: 0 });
        console.log('[SmallWeb] queued reader mode for tab', tabId);
      } else {
        pendingReaderMode.delete(tabId);
      }

      await setReferrerForUrl(message.url);
      await api.tabs.update(tabId, { url: message.url });
    }
    return { success: true };
  }

  if (type === 'prefetch') {
    if (message.url) fetch(message.url, { method: 'GET', mode: 'no-cors', credentials: 'omit' }).catch(() => {});
    return { success: !!message.url };
  }

  if (type === 'appreciate') {
    return { success: await appreciatePost(message.url) };
  }

  if (type === 'savePost') {
    return await savePost(message.post);
  }

  if (type === 'unsavePost') {
    return await unsavePost(message.url);
  }

  if (type === 'isPostSaved') {
    return { saved: await isPostSaved(message.url) };
  }

  if (type === 'toggleReaderMode') {
    const tabs = await api.tabs.query({ active: true, currentWindow: true });
    if (tabs[0]?.id) {
      // Frontend tells us whether to enable or disable
      const shouldEnable = message.enable;
      console.log('[SmallWeb] manual toggle:', { shouldEnable, dyslexia: message.dyslexia });
      const result = await runInTab(tabs[0].id, readerModeScript, [message.dyslexia || false, false, !shouldEnable]);
      console.log('[SmallWeb] manual toggle result:', result);
      return result || { enabled: false };
    }
    return { enabled: false };
  }

  if (type === 'getPageText') {
    const tabs = await api.tabs.query({ active: true, currentWindow: true });
    if (tabs[0]?.id) {
      const text = await runInTab(tabs[0].id, () => {
        for (const sel of ['article', 'main', '.post', '.content', '.entry', '[role="main"]']) {
          const el = document.querySelector(sel);
          if (el && el.innerText.trim().length > 200) return el.innerText.trim();
        }
        return document.body.innerText?.trim() || '';
      }, []);
      return { text: text || '' };
    }
    return { text: '' };
  }

  return {};
}

// Message listener
api.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message)
    .then(r => sendResponse(r || {}))
    .catch(e => sendResponse({ error: e.message }));
  return true;
});

// Pre-fetch on install
const initFeeds = () => ['blogs', 'youtube', 'github', 'comics'].forEach(ensureFeedLoaded);

if (IS_FIREFOX) {
  api.runtime.onInstalled.addListener(initFeeds);
} else {
  chrome.runtime.onInstalled.addListener(initFeeds);
  chrome.runtime.onStartup.addListener(() => ensureFeedLoaded('blogs'));
}

// Try to apply reader mode to a tab
async function tryApplyReaderMode(tabId) {
  const config = pendingReaderMode.get(tabId);
  if (!config) return;

  config.attempts++;
  console.log('[SmallWeb] applying reader mode, attempt', config.attempts);

  try {
    const result = await runInTab(tabId, readerModeScript, [config.dyslexia, false, false]);
    console.log('[SmallWeb] reader mode result:', result);
    if (result?.enabled) {
      pendingReaderMode.delete(tabId);
      console.log('[SmallWeb] reader mode applied successfully');
      return true;
    }
  } catch (e) {
    console.log('[SmallWeb] reader mode error:', e.message);
  }

  if (config.attempts >= 6) {
    pendingReaderMode.delete(tabId);
    console.log('[SmallWeb] giving up after max attempts');
  }
  return false;
}

// Apply reader mode when tab finishes loading
api.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (!pendingReaderMode.has(tabId)) return;
  if (changeInfo.status !== 'complete') return;

  console.log('[SmallWeb] onUpdated complete:', { tabId });

  // Try immediately, then with delays for JS-rendered content
  const success = await tryApplyReaderMode(tabId);
  if (success) return;

  // Retry with delays for slow-rendering pages
  const delays = [500, 1000, 2000];
  for (const delay of delays) {
    if (!pendingReaderMode.has(tabId)) return;
    await new Promise(r => setTimeout(r, delay));
    if (!pendingReaderMode.has(tabId)) return;
    const ok = await tryApplyReaderMode(tabId);
    if (ok) return;
  }
});

// Clean up when tab is closed
api.tabs.onRemoved.addListener((tabId) => {
  pendingReaderMode.delete(tabId);
});
