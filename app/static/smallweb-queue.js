/**
 * SmallWeb Queue - Client-side random selection with dynamic FIFO exclusion
 */

(function(global) {
  'use strict';

  const DEFAULT_CONFIG = {
    metaUrl: '/smallweb/appreciated/meta',
    fullListUrl: '/smallweb/appreciated.json',
    checkOnNext: false,
    periodicCheckEnabled: false,
    periodicCheckMinutes: 60,
    checkOnExhaustion: true,
    persistKey: 'kagi_smallweb_queue_v2',
    resetOnVersionChange: false,
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
        log('Loaded state:', state.version, 'items:', Object.keys(state.items || {}).length, 'visited:', state.visited_fifo?.length || 0);
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
        log('State updated by another tab');
        loadState();
      }
    });
  }

  // API calls
  async function fetchMeta() {
    const response = await fetch(config.metaUrl, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
    });
    if (!response.ok) throw new Error(`Meta fetch failed: ${response.status}`);
    return await response.json();
  }

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
    log('Fetched', data.urls.length, 'items');
    return { notModified: false, version: data.version, urls: data.urls };
  }

  // Version checking
  async function maybeRefreshMeta() {
    try {
      log('Checking version...');
      const meta = await fetchMeta();
      
      if (!state || state.version !== meta.version) {
        log('Version changed:', state?.version, '->', meta.version);
        await refreshFullList();
        return true;
      }
      log('Version unchanged');
      return false;
    } catch (e) {
      error('Version check failed:', e);
      return false;
    }
  }

  async function refreshFullList() {
    try {
      const data = await fetchFullList(state?.version);
      if (data.notModified) return;
      
      if (config.resetOnVersionChange || !state) {
        state = createEmptyState();
        state.version = data.version;
        state.lastUpdated = Date.now();
        for (const item of data.urls) state.items[item.id] = item;
      } else {
        mergeNewItems(data.urls, data.version);
      }
      saveState();
    } catch (e) {
      error('Refresh failed:', e);
    }
  }

  function mergeNewItems(newUrls, newVersion) {
    const shownSet = new Set(state.visited_fifo);
    
    const newItems = {};
    for (const item of newUrls) newItems[item.id] = item;
    
    const newIds = Object.keys(newItems).filter(id => !shownSet.has(id));
    
    state.version = newVersion;
    state.items = newItems;
    state.lastUpdated = Date.now();
    
    // Remove deleted items from FIFO
    const oldFifoLen = state.visited_fifo.length;
    state.visited_fifo = state.visited_fifo.filter(id => newItems[id]);
    state.roundRobinCounter = 0;
    
    log('Merged: total:', Object.keys(state.items).length, 'new:', newIds.length, 'removed from FIFO:', oldFifoLen - state.visited_fifo.length);
  }

  async function forceRefresh() {
    state = createEmptyState();
    await refreshFullList();
    return state;
  }

  // Selection logic
  async function getNext() {
    if (config.checkOnNext) await maybeRefreshMeta();
    
    if (!state || Object.keys(state.items).length === 0) {
      await refreshFullList();
      if (!state || Object.keys(state.items).length === 0) {
        warn('No items available');
        return null;
      }
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
    
    log('Selection: total:', Object.keys(state.items).length, 'visited:', state.visited_fifo.length, 'candidates:', candidates.length);
    
    if (candidates.length === 0) return await handleExhaustion();
    
    const idx = Math.floor(Math.random() * candidates.length);
    return state.items[candidates[idx]];
  }

  async function handleExhaustion() {
    const totalItems = Object.keys(state.items).length;
    if (typeof state.roundRobinCounter !== 'number') state.roundRobinCounter = 0;
    
    log('Exhaustion: FIFO:', state.visited_fifo.length, 'total:', totalItems, 'round-robin:', state.roundRobinCounter);
    
    const shouldFetch = state.roundRobinCounter === 0 || state.roundRobinCounter >= totalItems;
    
    if (shouldFetch && config.checkOnExhaustion) {
      log('Fetching new items (', state.roundRobinCounter === 0 ? 'first exhaustion' : 'full rotation', ')');
      state.roundRobinCounter = 0;
      const refreshed = await maybeRefreshMeta();
      
      if (refreshed) {
        const visitedSet = new Set(state.visited_fifo);
        const newCandidates = Object.keys(state.items).filter(id => !visitedSet.has(id));
        if (newCandidates.length > 0) {
          state.roundRobinCounter = 0;
          const idx = Math.floor(Math.random() * newCandidates.length);
          saveState();
          return state.items[newCandidates[idx]];
        }
      }
    }
    
    // Round-robin: pick oldest, move to end
    if (state.visited_fifo.length === 0) return null;
    
    const oldestId = state.visited_fifo.shift();
    state.visited_fifo.push(oldestId);
    state.roundRobinCounter++;
    
    log('Round-robin:', state.roundRobinCounter, '/', totalItems);
    saveState();
    return state.items[oldestId];
  }

  function addToVisited(id) {
    const existingIdx = state.visited_fifo.indexOf(id);
    if (existingIdx !== -1) state.visited_fifo.splice(existingIdx, 1);
    state.visited_fifo.push(id);
    log('Added to FIFO:', state.visited_fifo.length, '/', Object.keys(state.items).length);
  }

  // Periodic checking
  function startPeriodicCheck() {
    if (!config.periodicCheckEnabled) return;
    if (periodicTimer) clearInterval(periodicTimer);
    
    const intervalMs = config.periodicCheckMinutes * 60 * 1000;
    periodicTimer = setInterval(async () => {
      log('Periodic check');
      await maybeRefreshMeta();
    }, intervalMs);
    log('Periodic check started:', config.periodicCheckMinutes, 'min');
  }

  function stopPeriodicCheck() {
    if (periodicTimer) {
      clearInterval(periodicTimer);
      periodicTimer = null;
    }
  }

  // Public API
  async function init(userConfig = {}) {
    if (initialized) { warn('Already initialized'); return; }
    
    config = { ...DEFAULT_CONFIG, ...userConfig };
    log('Init with config:', config);
    
    setupStorageListener();
    
    if (!loadState()) {
      log('No saved state, fetching...');
      state = createEmptyState();
      await refreshFullList();
    }
    
    startPeriodicCheck();
    initialized = true;
    log('Initialized: items:', Object.keys(state.items).length, 'visited:', state.visited_fifo.length);
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
    let id = idOrUrl;
    for (const [itemId, item] of Object.entries(state.items)) {
      if (item.url === idOrUrl) { id = itemId; break; }
    }
    addToVisited(id);
    saveState();
  }

  function clearVisited() {
    if (!state) return;
    state.visited_fifo = [];
    state.roundRobinCounter = 0;
    saveState();
    log('Cleared visited');
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
    const oldPeriodic = config.periodicCheckEnabled;
    const oldMinutes = config.periodicCheckMinutes;
    config = { ...config, ...newConfig };
    if (config.periodicCheckEnabled !== oldPeriodic || config.periodicCheckMinutes !== oldMinutes) {
      stopPeriodicCheck();
      startPeriodicCheck();
    }
    log('Config updated');
  }

  function shutdown() {
    stopPeriodicCheck();
    saveState();
    initialized = false;
  }

  const SmallWebQueue = {
    init,
    shutdown,
    getNext,
    forceRefresh,
    maybeRefreshMeta,
    getDebugInfo,
    getVersion,
    getItem,
    getAllItems,
    isVisited,
    markVisited,
    clearVisited,
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
