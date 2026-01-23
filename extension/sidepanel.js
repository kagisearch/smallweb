// Small Web Extension - Side Panel Logic
// Optimized for instant navigation with preloading
// Works with both Chrome and Firefox

const api = typeof browser !== 'undefined' ? browser : chrome;

let currentMode = 'blogs';
let currentPost = null;
let history = {}; // Per-mode history
let readerModeEnabled = false;
let dyslexiaModeEnabled = false;
let ttsEnabled = false;
let isSpeaking = false;

// DOM Elements
const discoverBtn = document.getElementById('nextPost');
const postLoading = document.getElementById('postLoading');
const postEmpty = document.getElementById('postEmpty');
const postContent = document.getElementById('postContent');
const postTitle = document.getElementById('postTitle');
const postDomain = document.getElementById('postDomain');
const postAuthor = document.getElementById('postAuthor');
const saveBtn = document.getElementById('saveBtn');
const readerBtn = document.getElementById('readerBtn');
const appreciateBtn = document.getElementById('appreciateBtn');
const listLabel = document.getElementById('listLabel');
const listItems = document.getElementById('listItems');
const clearListBtn = document.getElementById('clearList');
const modeTabs = document.querySelectorAll('.mode-tab');
const openInSmallWebLink = document.getElementById('openInSmallWeb');
const contributeBtn = document.getElementById('contributeBtn');
const contributeModal = document.getElementById('contributeModal');
const closeModalBtn = document.getElementById('closeModal');
const ttsBtn = document.getElementById('ttsBtn');
const dyslexiaBtn = document.getElementById('dyslexiaBtn');
const shortcutsBtn = document.getElementById('shortcutsBtn');
const shortcutsTooltip = document.getElementById('shortcutsTooltip');

// Initialize - load feeds in background
async function init() {
  // Disable discover button while loading
  discoverBtn.disabled = true;

  // Load saved state
  const stored = await api.storage.local.get(['history', 'currentMode', 'readerModeEnabled', 'dyslexiaModeEnabled', 'ttsEnabled']);
  if (stored.history) {
    history = stored.history;
  }
  if (stored.currentMode) {
    currentMode = stored.currentMode;
  }
  if (stored.readerModeEnabled) {
    readerModeEnabled = true;
    readerBtn.classList.add('active');
    dyslexiaBtn.classList.add('visible');
  }
  if (stored.dyslexiaModeEnabled) {
    dyslexiaModeEnabled = true;
    dyslexiaBtn.classList.add('active');
  }
  if (stored.ttsEnabled) {
    ttsEnabled = true;
    ttsBtn.classList.add('active');
  }

  updateModeUI();
  renderList();

  // Initialize feeds (this fetches all feeds and waits)
  try {
    const response = await api.runtime.sendMessage({
      type: 'init',
      mode: currentMode
    });

    // Hide loading state, enable button
    postLoading.style.display = 'none';
    discoverBtn.disabled = false;

    if (response?.error) {
      console.error('Init failed:', response.error);
      postEmpty.style.display = 'flex';
      showToast('Failed to load feeds', true);
      return;
    }

    if (response?.preloadUrl) {
      setPreload(response.preloadUrl);
    }

    // Auto-discover first post for a great first experience
    if (response?.ready) {
      discover();
    } else {
      // Feeds didn't load, show empty state - user can click Discover to retry
      postEmpty.style.display = 'flex';
      console.log('Init completed but no entries loaded');
    }

    // Update tooltips with counts
    updateTabCounts();
  } catch (error) {
    console.error('Init error:', error);
    postLoading.style.display = 'none';
    discoverBtn.disabled = false;
    postEmpty.style.display = 'flex';
  }
}

// Update mode tabs with item counts (shown on hover)
const tabLabels = {
  blogs: 'Blogs',
  appreciated: 'Appreciated',
  youtube: 'Videos',
  github: 'Code',
  comics: 'Comics',
  saved: 'Saved'
};

async function updateTabCounts() {
  try {
    const counts = await api.runtime.sendMessage({ type: 'getCounts' });
    modeTabs.forEach(tab => {
      const mode = tab.dataset.mode;
      tab.dataset.count = counts[mode] || 0;
      tab.textContent = tabLabels[mode];
    });
  } catch (e) {
    console.error('Failed to get counts:', e);
  }
}


// Prefetch next URL in the actual browser tab
function setPreload(url) {
  if (!url) return;

  api.runtime.sendMessage({
    type: 'prefetch',
    url: url
  });
}

// Discover next post - INSTANT because post is pre-selected
async function discover() {
  discoverBtn.classList.add('loading');

  // Stop any ongoing TTS
  stopReading();

  try {
    const response = await api.runtime.sendMessage({
      type: 'getNextPost',
      mode: currentMode
    });

    if (response?.post) {
      currentPost = response.post;
      addToHistory(currentPost);
      updatePostUI();

      // Navigate immediately (pass reader mode and TTS state)
      api.runtime.sendMessage({
        type: 'navigate',
        url: currentPost.link,
        readerMode: readerModeEnabled,
        dyslexia: dyslexiaModeEnabled
      });

      // Start TTS after page loads (with retry)
      if (ttsEnabled) {
        startReadingWithRetry();
      }

      // Set up preload for the NEXT post
      if (response.preloadUrl) {
        setPreload(response.preloadUrl);
      }
    } else {
      if (currentMode === 'saved') {
        showToast('No saved posts yet', true);
      } else {
        showToast('No posts available', true);
      }
    }
  } catch (error) {
    console.error('Error:', error);
    showToast('Failed to fetch', true);
  } finally {
    discoverBtn.classList.remove('loading');
  }
}

// Update post card UI
async function updatePostUI() {
  if (!currentPost) {
    postLoading.style.display = 'none';
    postEmpty.style.display = 'flex';
    postContent.style.display = 'none';
    return;
  }

  postLoading.style.display = 'none';
  postEmpty.style.display = 'none';
  postContent.style.display = 'flex';

  postDomain.textContent = currentPost.domain || '';
  postTitle.textContent = currentPost.title || 'Untitled';
  postAuthor.textContent = currentPost.author ? `by ${currentPost.author}` : '';

  // Update "Open in Small Web" link
  openInSmallWebLink.href = `https://kagi.com/smallweb/?url=${encodeURIComponent(currentPost.link)}`;

  // Check if post is saved
  const { saved } = await api.runtime.sendMessage({
    type: 'isPostSaved',
    url: currentPost.link
  });
  saveBtn.classList.toggle('active', saved);

  // Keep reader mode state
  readerBtn.classList.toggle('active', readerModeEnabled);

  // Reset appreciate button
  appreciateBtn.classList.remove('active');
}

// Save/unsave current post
async function toggleSave() {
  if (!currentPost) return;

  const isSaved = saveBtn.classList.contains('active');

  if (isSaved) {
    await api.runtime.sendMessage({
      type: 'unsavePost',
      url: currentPost.link
    });
    saveBtn.classList.remove('active');
    showToast('Removed from saved');

    // Refresh list if on saved tab
    if (currentMode === 'saved') {
      renderList();
    }
  } else {
    const result = await api.runtime.sendMessage({
      type: 'savePost',
      post: currentPost
    });
    saveBtn.classList.add('active');
    showToast(result.alreadySaved ? 'Already saved' : 'Saved for later');
  }

  // Update tab counts to reflect the change
  updateTabCounts();
}

// Toggle reader mode
async function toggleReaderMode() {
  // Toggle state immediately (optimistic update)
  readerModeEnabled = !readerModeEnabled;
  readerBtn.classList.toggle('active', readerModeEnabled);
  dyslexiaBtn.classList.toggle('visible', readerModeEnabled);
  api.storage.local.set({ readerModeEnabled });

  // Try to apply/remove - may fail if page still loading, that's okay
  // State is saved and will apply on next navigation
  try {
    const response = await api.runtime.sendMessage({
      type: 'toggleReaderMode',
      enable: readerModeEnabled,
      dyslexia: dyslexiaModeEnabled
    });

    if (response?.notReadable && readerModeEnabled) {
      showToast('Page not readable', true);
    }
  } catch (e) {
    // Page not ready, state will apply on next navigation
  }
}

// Appreciate current post
async function appreciatePost() {
  if (!currentPost) {
    showToast('Discover a post first', true);
    return;
  }

  appreciateBtn.classList.add('active');

  try {
    await api.runtime.sendMessage({
      type: 'appreciate',
      url: currentPost.link
    });
  } catch (error) {
    appreciateBtn.classList.remove('active');
  }
}

// Text-to-speech - toggle persistent TTS mode
function toggleTTS() {
  ttsEnabled = !ttsEnabled;
  api.storage.local.set({ ttsEnabled });
  ttsBtn.classList.toggle('active', ttsEnabled);

  if (ttsEnabled) {
    // Start reading current page if we have a post
    if (currentPost) {
      startReading();
    }
  } else {
    stopReading();
  }
}

// Stop any ongoing speech
function stopReading() {
  if (isSpeaking) {
    speechSynthesis.cancel();
    isSpeaking = false;
    ttsBtn.classList.remove('speaking');
  }
}

// Start reading the current page
async function startReading() {
  if (!ttsEnabled || isSpeaking) return false;

  // Get page content from the active tab
  const response = await api.runtime.sendMessage({ type: 'getPageText' });

  if (!response?.text || response.text.length < 50) {
    return false; // Page may still be loading
  }

  // Truncate to reasonable length for TTS
  const text = response.text.slice(0, 10000);

  // Start speaking
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1.0;
  utterance.pitch = 1.0;

  utterance.onstart = () => {
    isSpeaking = true;
    ttsBtn.classList.add('speaking');
  };

  utterance.onend = () => {
    isSpeaking = false;
    ttsBtn.classList.remove('speaking');
  };

  utterance.onerror = () => {
    isSpeaking = false;
    ttsBtn.classList.remove('speaking');
  };

  speechSynthesis.speak(utterance);
  return true;
}

// Start reading with retry for slow-loading pages
function startReadingWithRetry() {
  const delays = [1500, 3000, 5000]; // Wait for page to load
  let started = false;

  delays.forEach(delay => {
    setTimeout(async () => {
      if (!started && ttsEnabled && !isSpeaking) {
        const success = await startReading();
        if (success) started = true;
      }
    }, delay);
  });
}

// Toggle dyslexia-friendly font
function toggleDyslexia() {
  dyslexiaModeEnabled = !dyslexiaModeEnabled;
  dyslexiaBtn.classList.toggle('active', dyslexiaModeEnabled);
  api.storage.local.set({ dyslexiaModeEnabled });

  // If reader mode is active, re-apply with new font setting
  if (readerModeEnabled) {
    api.runtime.sendMessage({ type: 'toggleReaderMode', enable: true, dyslexia: dyslexiaModeEnabled });
  }
}

// Add to per-mode history
function addToHistory(post) {
  if (!history[currentMode]) {
    history[currentMode] = [];
  }

  // Don't add to history for saved mode (it has its own list)
  if (currentMode === 'saved') return;

  // Remove if exists
  history[currentMode] = history[currentMode].filter(h => h.link !== post.link);

  // Add to start
  history[currentMode].unshift({
    title: post.title,
    link: post.link,
    domain: post.domain,
    timestamp: Date.now()
  });

  // Keep last 20 per mode
  history[currentMode] = history[currentMode].slice(0, 20);

  api.storage.local.set({ history });
  renderList();
}

// Render the list based on current mode
async function renderList() {
  if (currentMode === 'saved') {
    // Show saved posts
    listLabel.textContent = 'Saved Posts';
    clearListBtn.style.display = 'none';

    const { savedPosts } = await api.storage.local.get(['savedPosts']);
    const items = savedPosts || [];

    if (items.length === 0) {
      listItems.innerHTML = '<div class="list-empty">No saved posts yet</div>';
      return;
    }

    listItems.innerHTML = items.map((item, i) => `
      <div class="list-item" data-index="${i}" data-type="saved">
        <div class="list-item-domain">${escapeHtml(item.domain)}</div>
        <div class="list-item-title">${escapeHtml(item.title)}</div>
      </div>
    `).join('');

  } else {
    // Show recent history for this mode
    const modeLabels = {
      blogs: 'Recently Viewed Blogs',
      appreciated: 'Recently Viewed Appreciated',
      youtube: 'Recently Viewed Videos',
      github: 'Recently Viewed Code',
      comics: 'Recently Viewed Comics'
    };
    listLabel.textContent = modeLabels[currentMode] || 'Recently Viewed';
    clearListBtn.style.display = 'block';

    const items = history[currentMode] || [];

    if (items.length === 0) {
      listItems.innerHTML = '<div class="list-empty">No history yet</div>';
      return;
    }

    listItems.innerHTML = items.map((item, i) => `
      <div class="list-item" data-index="${i}" data-type="history">
        <div class="list-item-domain">${escapeHtml(item.domain)}</div>
        <div class="list-item-title">${escapeHtml(item.title)}</div>
      </div>
    `).join('');
  }

  // Add click handlers
  listItems.querySelectorAll('.list-item').forEach(el => {
    el.addEventListener('click', async () => {
      const index = parseInt(el.dataset.index);
      const type = el.dataset.type;

      let item;
      if (type === 'saved') {
        const { savedPosts } = await api.storage.local.get(['savedPosts']);
        item = savedPosts?.[index];
      } else {
        item = history[currentMode]?.[index];
      }

      if (item) {
        stopReading();
        currentPost = item;
        updatePostUI();
        api.runtime.sendMessage({
          type: 'navigate',
          url: item.link,
          readerMode: readerModeEnabled,
          dyslexia: dyslexiaModeEnabled
        });

        // Start TTS after page loads
        if (ttsEnabled) {
          startReadingWithRetry();
        }
      }
    });
  });
}

// Clear history for current mode
function clearList() {
  if (currentMode === 'saved') return; // Don't clear saved from here

  history[currentMode] = [];
  api.storage.local.set({ history });
  renderList();
}

// Update mode UI
function updateModeUI() {
  modeTabs.forEach(tab => {
    tab.classList.toggle('active', tab.dataset.mode === currentMode);
  });
}

// Switch mode - auto-discover a post from the new mode
async function switchMode(mode) {
  currentMode = mode;
  api.storage.local.set({ currentMode });
  updateModeUI();
  renderList();
  discover();
}

// Toast
function showToast(message, isError = false) {
  const existing = document.querySelector('.toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.className = 'toast' + (isError ? ' error' : '');
  toast.textContent = message;
  document.body.appendChild(toast);

  requestAnimationFrame(() => toast.classList.add('show'));

  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, 2000);
}

// Escape HTML
function escapeHtml(text) {
  return (text || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Event Listeners
discoverBtn.addEventListener('click', discover);
clearListBtn.addEventListener('click', clearList);
saveBtn.addEventListener('click', toggleSave);
readerBtn.addEventListener('click', toggleReaderMode);
appreciateBtn.addEventListener('click', appreciatePost);
ttsBtn.addEventListener('click', toggleTTS);
dyslexiaBtn.addEventListener('click', toggleDyslexia);

modeTabs.forEach(tab => {
  tab.addEventListener('click', () => switchMode(tab.dataset.mode));
});

// Modal handlers
contributeBtn.addEventListener('click', () => {
  contributeModal.classList.add('show');
});

closeModalBtn.addEventListener('click', () => {
  contributeModal.classList.remove('show');
});

contributeModal.addEventListener('click', (e) => {
  if (e.target === contributeModal) {
    contributeModal.classList.remove('show');
  }
});

// Shortcuts tooltip
shortcutsBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  shortcutsTooltip.classList.toggle('show');
});

document.addEventListener('click', (e) => {
  if (!shortcutsTooltip.contains(e.target) && e.target !== shortcutsBtn) {
    shortcutsTooltip.classList.remove('show');
  }
});

// Keyboard: Space to discover, R for reader mode, S to save, T for TTS, D for dyslexia
document.addEventListener('keydown', (e) => {
  if (e.target.matches('input, textarea')) return;

  if (e.code === 'Space') {
    e.preventDefault();
    discover();
  } else if (e.code === 'KeyR') {
    e.preventDefault();
    toggleReaderMode();
  } else if (e.code === 'KeyS') {
    e.preventDefault();
    toggleSave();
  } else if (e.code === 'KeyT') {
    e.preventDefault();
    toggleTTS();
  } else if (e.code === 'KeyD') {
    e.preventDefault();
    toggleDyslexia();
  }
});

// Init
init();
