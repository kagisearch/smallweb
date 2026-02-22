(() => {
  'use strict';

  const nextLink = document.getElementById('appreciated-next-link');
  const nextText = document.getElementById('appreciated-next-text');

  if (!nextLink || !nextText || typeof SmallWebQueue === 'undefined') return;

  const queueConfig = {
    fullListUrl: nextLink.dataset.fullListUrl,
    enablePeriodicResetQueue:
      (nextLink.dataset.enablePeriodicResetQueue || 'true') === 'true',
    periodicResetQueueMinutes: Number(
      nextLink.dataset.periodicResetQueueMinutes || '720'
    ),
    checkOnExhaustion: (nextLink.dataset.checkOnExhaustion || 'true') === 'true',
    persistKey: nextLink.dataset.persistKey || 'kagi_smallweb_queue_v2',
    enableDebug: (nextLink.dataset.enableDebug || 'false') === 'true',
  };

  const currentUrl = nextLink.dataset.currentUrl || null;
  const fallbackUrl =
    nextLink.dataset.fallbackUrl || nextLink.getAttribute('href') || '/';

  SmallWebQueue.init(queueConfig, currentUrl)
    .then(() => {
      preloadNextItem();
    })
    .catch((err) => console.error('[SmallWebQueue] Init failed:', err));

  let isNavigating = false;

  nextLink.addEventListener('click', async (e) => {
    e.preventDefault();
    if (isNavigating) return;
    isNavigating = true;

    nextText.textContent = 'Loading...';
    nextLink.style.pointerEvents = 'none';

    try {
      const item = await SmallWebQueue.getNext();
      if (item && item.url) {
        const url = new URL(window.location.href);
        url.searchParams.set('url', item.url);
        window.location.href = url.toString();
      } else {
        window.location.href = fallbackUrl;
      }
    } catch (err) {
      console.error('[SmallWebQueue] Error:', err);
      window.location.href = fallbackUrl;
    }
  });

  async function preloadNextItem() {
    try {
      const debugInfo = SmallWebQueue.getDebugInfo();
      if (!debugInfo.initialized || debugInfo.totalItems === 0) return;

      const allItems = SmallWebQueue.getAllItems();
      const visitedSet = new Set(debugInfo.visitedFifo);

      for (const item of allItems) {
        if (!visitedSet.has(item.id)) {
          const prefetchLink = document.createElement('link');
          prefetchLink.rel = 'prefetch';
          prefetchLink.href = item.url;
          prefetchLink.as = 'document';
          document.head.appendChild(prefetchLink);

          const url = new URL(window.location.href);
          url.searchParams.set('url', item.url);
          nextLink.setAttribute('href', url.toString());
          break;
        }
      }
    } catch (err) {}
  }
})();
