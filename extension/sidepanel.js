// Small Web Extension - Side Panel Logic
// Optimized for instant navigation with preloading
// Works with both Chrome and Firefox

const api = typeof browser !== 'undefined' ? browser : chrome;

let currentMode = 'blogs';
let currentPost = null;
let history = {}; // Per-mode history
let readerModeEnabled = false;

// DOM Elements
const discoverBtn = document.getElementById('nextPost');
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
const openInKagiLink = document.getElementById('openInKagi');

// Initialize - load feeds in background
async function init() {
  // Load saved state
  const stored = await api.storage.local.get(['history', 'currentMode']);
  if (stored.history) {
    history = stored.history;
  }
  if (stored.currentMode) {
    currentMode = stored.currentMode;
  }

  updateModeUI();
  renderList();

  // Initialize feeds and get first preload URL
  const response = await api.runtime.sendMessage({
    type: 'init',
    mode: currentMode
  });

  if (response?.preloadUrl) {
    setPreload(response.preloadUrl);
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

// Apply reader mode with retry for slow-loading pages
function applyReaderModeWithRetry() {
  const delays = [800, 1500, 3000]; // Retry at 800ms, 1.5s, 3s
  delays.forEach(delay => {
    setTimeout(() => {
      if (readerModeEnabled) {
        api.runtime.sendMessage({ type: 'applyReaderMode' });
      }
    }, delay);
  });
}

// Discover next post - INSTANT because post is pre-selected
async function discover() {
  discoverBtn.classList.add('loading');

  try {
    const response = await api.runtime.sendMessage({
      type: 'getNextPost',
      mode: currentMode
    });

    if (response?.post) {
      currentPost = response.post;
      addToHistory(currentPost);
      updatePostUI();

      // Navigate immediately
      api.runtime.sendMessage({
        type: 'navigate',
        url: currentPost.link
      });

      // Re-apply reader mode if enabled (with retry for slow pages)
      if (readerModeEnabled) {
        applyReaderModeWithRetry();
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
    postEmpty.style.display = 'flex';
    postContent.style.display = 'none';
    return;
  }

  postEmpty.style.display = 'none';
  postContent.style.display = 'flex';

  postDomain.textContent = currentPost.domain || '';
  postTitle.textContent = currentPost.title || 'Untitled';
  postAuthor.textContent = currentPost.author ? `by ${currentPost.author}` : '';

  // Update "Open in Kagi" link
  openInKagiLink.href = `https://kagi.com/smallweb/?url=${encodeURIComponent(currentPost.link)}`;

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
}

// Toggle reader mode
async function toggleReaderMode() {
  const response = await api.runtime.sendMessage({
    type: 'toggleReaderMode'
  });

  readerModeEnabled = response?.enabled || false;
  readerBtn.classList.toggle('active', readerModeEnabled);

  if (response?.error) {
    showToast('Cannot enable reader mode here', true);
  } else {
    showToast(readerModeEnabled ? 'Reader mode on' : 'Reader mode off');
  }
}

// Appreciate current post
async function appreciatePost() {
  if (!currentPost) return;

  appreciateBtn.classList.add('active');

  try {
    await api.runtime.sendMessage({
      type: 'appreciate',
      url: currentPost.link
    });
    showToast('Appreciated!');
  } catch (error) {
    appreciateBtn.classList.remove('active');
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
      blogs: 'Recent Blogs',
      appreciated: 'Recent Liked',
      youtube: 'Recent Videos',
      comics: 'Recent Comics'
    };
    listLabel.textContent = modeLabels[currentMode] || 'Recent';
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
        currentPost = item;
        updatePostUI();
        api.runtime.sendMessage({ type: 'navigate', url: item.link });

        // Re-apply reader mode if enabled
        if (readerModeEnabled) {
          applyReaderModeWithRetry();
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
  const div = document.createElement('div');
  div.textContent = text || '';
  return div.innerHTML;
}

// Event Listeners
discoverBtn.addEventListener('click', discover);
clearListBtn.addEventListener('click', clearList);
saveBtn.addEventListener('click', toggleSave);
readerBtn.addEventListener('click', toggleReaderMode);
appreciateBtn.addEventListener('click', appreciatePost);

modeTabs.forEach(tab => {
  tab.addEventListener('click', () => switchMode(tab.dataset.mode));
});

// Keyboard: Space to discover, R for reader mode, S to save
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
  }
});

// Init
init();
