/**
 * SmallWeb Queue - Client-side random selection with dynamic FIFO exclusion
 */

(function(global) {
  'use strict';

  const DEFAULT_CONFIG = {
    fullListUrl: '/appreciated.json',
    enablePeriodicResetQueue: true,
    periodicResetQueueMinutes: 720,
    checkOnExhaustion: true,
    persistKey: 'kagi_smallweb_queue_v2',
    enableDebug: false,
  };

  let config = { ...DEFAULT_CONFIG };
  let state = null;
  let periodicTimer = null;
  let initialized = false;
  let onNextCallbacks = [];

  function log(...args) {
    if (config.enableDebug) console.log('[SmallWebQueue]', ...args);
  }

  function warn(...args) {
    console.warn('[SmallWebQueue]', ...args);
  }

  function error(...args) {
    console.error('[SmallWebQueue]', ...args);
  }

  // Storage
  function loadState() {
    try {
      const stored = localStorage.getItem(config.persistKey);
      if (stored) {
        state = JSON.parse(stored);

        // Validate and clean up loaded state
        if (state && state.items && state.visited_fifo) {
          const originalFifoLen = state.visited_fifo.length;

          // Remove invalid entries (non-existent item IDs) and deduplicate
          const seen = new Set();
          state.visited_fifo = state.visited_fifo.filter(id => {
            if (!state.items[id] || seen.has(id)) return false;
            seen.add(id);
            return true;
          });
        }
        return true;
      }
    } catch (e) {
      error('Failed to load state:', e);
    }
    return false;
  }

  function saveState() {
    try {
      localStorage.setItem(config.persistKey, JSON.stringify(state));
    } catch (e) {
      error('Failed to save state:', e);
    }
  }

  function createEmptyState() {
    return {
      version: null,
      items: {},
      visited_fifo: [],
      roundRobinCounter: 0,
      lastUpdated: 0,
    };
  }

  function setupStorageListener() {
    window.addEventListener('storage', (event) => {
      if (event.key === config.persistKey) {
        loadState();
      }
    });
  }

  // API calls
  async function fetchFullList(currentEtag = null) {
    const headers = {
      'Accept': 'application/json',
      'Accept-Encoding': 'gzip, deflate',
    };
    if (currentEtag) headers['If-None-Match'] = `"${currentEtag}"`;
    
    const response = await fetch(config.fullListUrl, { method: 'GET', headers });
    
    if (response.status === 304) {
      return { notModified: true, version: currentEtag, urls: [] };
    }
    if (!response.ok) throw new Error(`Full list fetch failed: ${response.status}`);
    
    const data = await response.json();
    return { notModified: false, version: data.version, urls: data.urls };
  }

  // Version checking
  async function maybeRefreshMeta() {
    try {
      const data = await fetchFullList(state?.version);

      if (!data.notModified) {
        await resetQueueCompletely();
        return true;
      }
      return false;
    } catch (e) {
      error('Version check failed:', e);
      return false;
    }
  }


  // Selection logic
  async function getNext() {

    if (!state || Object.keys(state.items).length === 0) {
      warn('No items available');
      return null;
    }

    // Reload state in case another tab updated it
    loadState();

    const item = await selectNextRandom();
    if (item && !state.visited_fifo.includes(item.id)) {
      addToVisited(item.id);
    }
    if (item) saveState();

    for (const cb of onNextCallbacks) {
      try { cb(item); } catch (e) { error('Callback error:', e); }
    }
    return item;
  }

  async function selectNextRandom() {
    const visitedSet = new Set(state.visited_fifo);
    const candidates = Object.keys(state.items).filter(id => !visitedSet.has(id));
        
    if (candidates.length === 0) return await handleExhaustion();
    
    const idx = Math.floor(Math.random() * candidates.length);
    return state.items[candidates[idx]];
  }

  async function handleExhaustion() {
    const totalItems = Object.keys(state.items).length;
    if (typeof state.roundRobinCounter !== 'number') state.roundRobinCounter = 0;
        
    const shouldFetch = state.roundRobinCounter === 0 || state.roundRobinCounter >= totalItems;
    
    if (shouldFetch && config.checkOnExhaustion) {
      state.roundRobinCounter = 0;
      const refreshed = await maybeRefreshMeta();
      
      if (refreshed) {
        // Version changed - queue was reset, re-initialize immediately
        await init();
        // Now we have fresh state, get a random item from the new data
        const allItems = Object.keys(state.items);
        if (allItems.length > 0) {
          const idx = Math.floor(Math.random() * allItems.length);
          const selectedId = allItems[idx];
          addToVisited(selectedId);
          saveState();
          return state.items[selectedId];
        }
      }
    }
    
    // Round-robin: pick oldest, move to end
    if (state.visited_fifo.length === 0) return null;
    
    const oldestId = state.visited_fifo.shift();
    state.visited_fifo.push(oldestId);
    state.roundRobinCounter++;
    
    saveState();
    return state.items[oldestId];
  }

  function addToVisited(id) {
    const existingIdx = state.visited_fifo.indexOf(id);
    if (existingIdx !== -1) state.visited_fifo.splice(existingIdx, 1);
    state.visited_fifo.push(id);
  }

  // Periodic checking
  function startPeriodicReset() {
    if (!config.enablePeriodicResetQueue) return;
    if (periodicTimer) clearInterval(periodicTimer);

    const intervalMs = config.periodicResetQueueMinutes * 60 * 1000;
    periodicTimer = setInterval(async () => {
      await resetQueueCompletely();
    }, intervalMs);
  }

  function stopPeriodicReset() {
    if (periodicTimer) {
      clearInterval(periodicTimer);
      periodicTimer = null;
    }
  }

  // Public API
  async function init(userConfig = {}, currentUrl = null) {
    // If already initialized and we have state, don't re-initialize
    if (initialized && state) {
      return;
    }

    config = { ...DEFAULT_CONFIG, ...userConfig };
    setupStorageListener();

    // Check if state exists in localStorage (persistent across page loads)
    const hasExistingState = loadState();

    if (!hasExistingState) {
      const data = await fetchFullList();
      state = createEmptyState();
      state.version = data.version;
      state.lastUpdated = Date.now();
      for (const item of data.urls) state.items[item.id] = item;
      startPeriodicReset();
      saveState();
    } else {
      // Check if we need to reset due to time-based reset (window was closed during reset period)
      const timeSinceLastUpdate = Date.now() - (state.lastUpdated || 0);
      const resetIntervalMs = config.periodicResetQueueMinutes * 60 * 1000;

      if (config.enablePeriodicResetQueue && timeSinceLastUpdate >= resetIntervalMs) {
        await resetQueueCompletely();
        // After reset, we need to re-initialize
        const data = await fetchFullList();
        state = createEmptyState();
        state.version = data.version;
        state.lastUpdated = Date.now();
        for (const item of data.urls) state.items[item.id] = item;
        saveState();
      }
    }

    // Mark current URL as visited if provided (for page load scenario)
    if (currentUrl) {
      markVisited(currentUrl);
    }
    initialized = true;
  }

  function getDebugInfo() {
    if (!state) return { initialized: false };
    const totalItems = Object.keys(state.items).length;
    return {
      initialized,
      version: state.version,
      totalItems,
      visitedCount: state.visited_fifo.length,
      candidatesRemaining: totalItems - state.visited_fifo.length,
      isExhausted: state.visited_fifo.length >= totalItems,
      roundRobinCounter: state.roundRobinCounter || 0,
      visitedFifo: [...state.visited_fifo],
      config: { ...config },
    };
  }

  function onNext(callback) {
    if (typeof callback === 'function') onNextCallbacks.push(callback);
  }

  function isVisited(idOrUrl) {
    if (!state) return false;
    if (state.visited_fifo.includes(idOrUrl)) return true;
    for (const id of state.visited_fifo) {
      if (state.items[id]?.url === idOrUrl) return true;
    }
    return false;
  }

  function markVisited(idOrUrl) {
    if (!state) return;

    // First try to find by ID
    if (state.items[idOrUrl]) {
      addToVisited(idOrUrl);
      saveState();
      return;
    }

    // Then try to find by URL
    for (const [itemId, item] of Object.entries(state.items)) {
      if (item.url === idOrUrl) {
        addToVisited(itemId);
        saveState();
        return;
      }
    }

    // If not found, log warning but don't add to FIFO
    console.warn('markVisited: URL not found in queue items:', idOrUrl);
  }

  async function resetQueueCompletely() {
  
    // Clear all localStorage data for this queue
    localStorage.removeItem(config.persistKey);

    // Reset all global state variables
    state = null;
    initialized = false;
  }

  function getVersion() { return state?.version || null; }

  function getItem(idOrUrl) {
    if (!state) return null;
    if (state.items[idOrUrl]) return state.items[idOrUrl];
    for (const item of Object.values(state.items)) {
      if (item.url === idOrUrl) return item;
    }
    return null;
  }

  function getAllItems() {
    return state ? Object.values(state.items) : [];
  }

  function updateConfig(newConfig) {
    const oldPeriodic = config.enablePeriodicResetQueue;
    const oldMinutes = config.periodicResetQueueMinutes;
    config = { ...config, ...newConfig };
    if (config.enablePeriodicResetQueue !== oldPeriodic || config.periodicResetQueueMinutes !== oldMinutes) {
      stopPeriodicReset();
      startPeriodicReset();
    }
  }

  function shutdown() {
    stopPeriodicReset();
    saveState();
    initialized = false;
  }

  const SmallWebQueue = {
    init,
    shutdown,
    getNext,
    maybeRefreshMeta,
    getDebugInfo,
    getVersion,
    getItem,
    getAllItems,
    isVisited,
    markVisited,
    resetQueue: resetQueueCompletely,
    updateConfig,
    onNext,
    DEFAULT_CONFIG,
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = SmallWebQueue;
  } else {
    global.SmallWebQueue = SmallWebQueue;
  }

})(typeof window !== 'undefined' ? window : global);
