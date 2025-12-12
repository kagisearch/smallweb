// Kagi Small Web - Background Service Worker / Script
// Works with both Chrome (Manifest V3) and Firefox (Manifest V2)

const IS_FIREFOX = typeof browser !== 'undefined' && browser.runtime?.getBrowserInfo;
const api = typeof browser !== 'undefined' ? browser : chrome;

const API_BASE = 'https://kagi.com/api/v1/smallweb/feed/';
const SMALLWEB_BASE = 'https://kagi.com/smallweb';
const CACHE_DURATION = 10 * 60 * 1000; // 10 minutes

// Feed cache
let cache = {
  blogs: { entries: [], lastFetch: 0 },
  youtube: { entries: [], lastFetch: 0 },
  github: { entries: [], lastFetch: 0 },
  comics: { entries: [], lastFetch: 0 },
  appreciated: { entries: [], lastFetch: 0 },
  saved: { entries: [], lastFetch: 0 }
};

// Next post queue - precomputed for instant access
let nextQueue = {
  blogs: null,
  youtube: null,
  github: null,
  comics: null,
  appreciated: null,
  saved: null
};

// Load saved posts from storage
async function loadSavedPosts() {
  const result = await api.storage.local.get(['savedPosts']);
  cache.saved.entries = result.savedPosts || [];
  prepareNext('saved');
}

// Save a post for later
async function savePost(post) {
  await loadSavedPosts();

  if (cache.saved.entries.some(p => p.link === post.link)) {
    return { success: true, alreadySaved: true };
  }

  cache.saved.entries.unshift({
    ...post,
    savedAt: Date.now()
  });

  cache.saved.entries = cache.saved.entries.slice(0, 100);
  await api.storage.local.set({ savedPosts: cache.saved.entries });
  prepareNext('saved');

  return { success: true, alreadySaved: false };
}

// Remove saved post
async function unsavePost(url) {
  await loadSavedPosts();
  cache.saved.entries = cache.saved.entries.filter(p => p.link !== url);
  await api.storage.local.set({ savedPosts: cache.saved.entries });
  prepareNext('saved');
  return { success: true };
}

// Check if post is saved
async function isPostSaved(url) {
  await loadSavedPosts();
  return cache.saved.entries.some(p => p.link === url);
}

// Parse Atom feed using regex (DOMParser not available in service workers)
function parseFeed(text) {
  const entries = [];
  const entryRegex = /<entry[^>]*>([\s\S]*?)<\/entry>/g;
  let entryMatch;

  while ((entryMatch = entryRegex.exec(text)) !== null) {
    const entryXml = entryMatch[1];

    const titleMatch = entryXml.match(/<title[^>]*>([^<]*)<\/title>/);
    const title = titleMatch ? decodeXmlEntities(titleMatch[1]) : 'Untitled';

    const linkMatch = entryXml.match(/<link[^>]*href="([^"]+)"/);
    const link = linkMatch ? linkMatch[1] : '';

    const authorMatch = entryXml.match(/<author>\s*<name>([^<]*)<\/name>/);
    const author = authorMatch ? decodeXmlEntities(authorMatch[1]) : '';

    const summaryMatch = entryXml.match(/<summary[^>]*>([\s\S]*?)<\/summary>/);
    const contentMatch = entryXml.match(/<content[^>]*>([\s\S]*?)<\/content>/);
    const summary = summaryMatch ? summaryMatch[1] : (contentMatch ? contentMatch[1] : '');

    if (link && link.startsWith('https://')) {
      try {
        const domain = new URL(link).hostname.replace(/^www\./, '');
        entries.push({ title, link, author, summary, domain });
      } catch (e) {}
    }
  }

  return entries;
}

function decodeXmlEntities(text) {
  return text
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&#8217;/g, "'")
    .replace(/&#8211;/g, "–")
    .replace(/&#(\d+);/g, (_, num) => String.fromCharCode(parseInt(num)));
}

// Fetch and cache feed (only when stale)
async function ensureFeedLoaded(mode) {
  if (mode === 'saved') {
    await loadSavedPosts();
    return cache.saved.entries;
  }

  const urls = {
    blogs: API_BASE + '?nso',
    youtube: API_BASE + '?yt',
    github: API_BASE + '?gh',
    comics: API_BASE + '?comic',
    appreciated: SMALLWEB_BASE + '/appreciated'
  };

  const now = Date.now();
  if (cache[mode].entries.length > 0 && now - cache[mode].lastFetch < CACHE_DURATION) {
    return cache[mode].entries;
  }

  try {
    console.log(`Fetching ${mode}...`);
    const response = await fetch(urls[mode]);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const text = await response.text();
    let entries = parseFeed(text);

    if (mode === 'youtube') {
      entries = entries.filter(e => !e.link.includes('/shorts/'));
    }

    cache[mode] = { entries, lastFetch: now };
    console.log(`Cached ${entries.length} entries for ${mode}`);

    prepareNext(mode);
    return entries;
  } catch (error) {
    console.error(`Failed to fetch ${mode}:`, error);
    return cache[mode].entries;
  }
}

// Pick random post from cache
function pickRandom(mode) {
  const entries = cache[mode].entries;
  if (entries.length === 0) return null;
  return entries[Math.floor(Math.random() * entries.length)];
}

// Prepare next post for a mode
function prepareNext(mode) {
  nextQueue[mode] = pickRandom(mode);
  console.log(`Prepared next for ${mode}:`, nextQueue[mode]?.domain);
}

// Get current post and prepare next
function getNextPost(mode) {
  let post = nextQueue[mode];
  if (!post) {
    post = pickRandom(mode);
  }
  prepareNext(mode);
  return post;
}

// Get preload URL
function getPreloadUrl(mode) {
  return nextQueue[mode]?.link || null;
}

// Send appreciation to Kagi
async function appreciatePost(url) {
  try {
    const formData = new FormData();
    formData.append('url', url);
    formData.append('emoji', '👍');

    const response = await fetch(SMALLWEB_BASE + '/favorite', {
      method: 'POST',
      body: formData,
      credentials: 'include'
    });

    cache.appreciated.lastFetch = 0;
    return response.ok;
  } catch (error) {
    console.error('Failed to appreciate:', error);
    return false;
  }
}

// Execute script in tab (cross-browser)
async function executeInTab(tabId, func, args = []) {
  if (IS_FIREFOX) {
    // Firefox uses tabs.executeScript with code string
    const code = `(${func.toString()})(${args.map(a => JSON.stringify(a)).join(',')})`;
    try {
      const results = await api.tabs.executeScript(tabId, { code });
      return results[0];
    } catch (e) {
      console.log('Could not execute script:', e.message);
      return null;
    }
  } else {
    // Chrome uses scripting.executeScript
    try {
      const results = await chrome.scripting.executeScript({
        target: { tabId },
        func,
        args
      });
      return results[0]?.result;
    } catch (e) {
      console.log('Could not execute script:', e.message);
      return null;
    }
  }
}

// Handle toolbar button click
if (IS_FIREFOX) {
  // Firefox: toggle sidebar
  api.browserAction.onClicked.addListener(() => {
    api.sidebarAction.toggle();
  });
} else {
  // Chrome: open side panel
  chrome.action.onClicked.addListener((tab) => {
    chrome.sidePanel.open({ windowId: tab.windowId });
  });
}

// Async message handler - returns Promise for Firefox compatibility
async function handleMessage(message) {
  if (message.type === 'init') {
    await Promise.all([
      ensureFeedLoaded('blogs'),
      ensureFeedLoaded('youtube'),
      ensureFeedLoaded('comics'),
      ensureFeedLoaded('appreciated')
    ]);
    return {
      ready: true,
      preloadUrl: getPreloadUrl(message.mode || 'blogs')
    };
  }

  if (message.type === 'getNextPost') {
    const mode = message.mode || 'blogs';
    await ensureFeedLoaded(mode);
    const post = getNextPost(mode);
    const preloadUrl = getPreloadUrl(mode);
    return { post, preloadUrl };
  }

  if (message.type === 'getPreloadUrl') {
    return { preloadUrl: getPreloadUrl(message.mode || 'blogs') };
  }

  if (message.type === 'navigate') {
    const tabs = await api.tabs.query({ active: true, currentWindow: true });
    if (tabs[0]) {
      await api.tabs.update(tabs[0].id, { url: message.url });
    }
    return { success: true };
  }

  if (message.type === 'prefetch') {
    const tabs = await api.tabs.query({ active: true, currentWindow: true });
    if (tabs[0]?.id) {
      await executeInTab(tabs[0].id, (url) => {
        document.querySelectorAll('link[data-smallweb-prefetch]').forEach(el => el.remove());

        const preconnect = document.createElement('link');
        preconnect.rel = 'preconnect';
        preconnect.href = new URL(url).origin;
        preconnect.setAttribute('data-smallweb-prefetch', 'true');
        document.head.appendChild(preconnect);

        const dns = document.createElement('link');
        dns.rel = 'dns-prefetch';
        dns.href = new URL(url).origin;
        dns.setAttribute('data-smallweb-prefetch', 'true');
        document.head.appendChild(dns);

        const prefetch = document.createElement('link');
        prefetch.rel = 'prefetch';
        prefetch.href = url;
        prefetch.setAttribute('data-smallweb-prefetch', 'true');
        document.head.appendChild(prefetch);

        console.log('[Small Web] Prefetching:', url);
      }, [message.url]);
    }
    return { success: true };
  }

  if (message.type === 'appreciate') {
    const success = await appreciatePost(message.url);
    return { success };
  }

  if (message.type === 'savePost') {
    return await savePost(message.post);
  }

  if (message.type === 'unsavePost') {
    return await unsavePost(message.url);
  }

  if (message.type === 'isPostSaved') {
    const saved = await isPostSaved(message.url);
    return { saved };
  }

  if (message.type === 'toggleReaderMode') {
    const tabs = await api.tabs.query({ active: true, currentWindow: true });
    if (tabs[0]?.id) {
      const result = await executeInTab(tabs[0].id, () => {
        const READER_ID = 'smallweb-reader-mode';
        const existing = document.getElementById(READER_ID);

        if (existing) {
          existing.remove();
          return false;
        }

        const style = document.createElement('style');
        style.id = READER_ID;
        style.textContent = `
          body {
            max-width: 700px !important;
            margin: 0 auto !important;
            padding: 20px 24px !important;
            font-family: Georgia, 'Times New Roman', serif !important;
            font-size: 19px !important;
            line-height: 1.7 !important;
            color: #333 !important;
            background: #fafafa !important;
          }
          img { max-width: 100% !important; height: auto !important; }
          pre, code { font-size: 14px !important; overflow-x: auto !important; }
          nav, header, footer, aside, .sidebar, .nav, .menu, .ads, .advertisement,
          .social-share, .comments, .related-posts, [class*="sidebar"],
          [class*="widget"], [class*="banner"], [class*="popup"], [class*="modal"],
          [id*="sidebar"], [id*="nav"], [id*="menu"], [id*="footer"] {
            display: none !important;
          }
          a { color: #ea580c !important; }
          h1, h2, h3, h4, h5, h6 {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
            line-height: 1.3 !important;
            margin-top: 1.5em !important;
          }
          p, li { margin-bottom: 1em !important; }
        `;
        document.head.appendChild(style);
        return true;
      }, []);
      return { enabled: result };
    }
    return { enabled: false, error: 'No active tab' };
  }

  if (message.type === 'applyReaderMode') {
    const tabs = await api.tabs.query({ active: true, currentWindow: true });
    if (tabs[0]?.id) {
      await executeInTab(tabs[0].id, () => {
        const READER_ID = 'smallweb-reader-mode';
        // Remove existing first to avoid duplicates
        const existing = document.getElementById(READER_ID);
        if (existing) existing.remove();

        const style = document.createElement('style');
        style.id = READER_ID;
        style.textContent = `
          body {
            max-width: 700px !important;
            margin: 0 auto !important;
            padding: 20px 24px !important;
            font-family: Georgia, 'Times New Roman', serif !important;
            font-size: 19px !important;
            line-height: 1.7 !important;
            color: #333 !important;
            background: #fafafa !important;
          }
          img { max-width: 100% !important; height: auto !important; }
          pre, code { font-size: 14px !important; overflow-x: auto !important; }
          nav, header, footer, aside, .sidebar, .nav, .menu, .ads, .advertisement,
          .social-share, .comments, .related-posts, [class*="sidebar"],
          [class*="widget"], [class*="banner"], [class*="popup"], [class*="modal"],
          [id*="sidebar"], [id*="nav"], [id*="menu"], [id*="footer"] {
            display: none !important;
          }
          a { color: #ea580c !important; }
          h1, h2, h3, h4, h5, h6 {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
            line-height: 1.3 !important;
            margin-top: 1.5em !important;
          }
          p, li { margin-bottom: 1em !important; }
        `;
        document.head.appendChild(style);
      }, []);
      return { success: true };
    }
    return { success: false };
  }

  return {};
}

// Message listener - works for both Chrome and Firefox
// Firefox with polyfill expects returning a Promise, Chrome uses sendResponse
api.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const promise = handleMessage(message);

  // For Firefox: return the promise directly
  // For Chrome: use sendResponse callback
  promise.then(response => {
    sendResponse(response);
  }).catch(error => {
    console.error('Message handler error:', error);
    sendResponse({ error: error.message });
  });

  // Return true for Chrome to keep channel open
  // Return promise for Firefox polyfill
  return IS_FIREFOX ? promise : true;
});

// Pre-fetch feeds on install/startup
if (IS_FIREFOX) {
  // Firefox
  api.runtime.onInstalled.addListener(() => {
    console.log('Small Web extension installed');
    ensureFeedLoaded('blogs');
    ensureFeedLoaded('youtube');
    ensureFeedLoaded('comics');
  });
} else {
  // Chrome
  chrome.runtime.onInstalled.addListener(() => {
    console.log('Small Web extension installed');
    ensureFeedLoaded('blogs');
    ensureFeedLoaded('youtube');
    ensureFeedLoaded('comics');
  });

  chrome.runtime.onStartup.addListener(() => {
    console.log('Small Web extension starting');
    ensureFeedLoaded('blogs');
  });
}
