/*
 * Client-side post deck.
 *
 * The next post's iframe is mounted behind the current one and has finished
 * loading before Next is ever clicked, so advancing is a transform, not a
 * navigation. Falls back to following the Next anchor whenever the deck is
 * empty or the fetch fails.
 */
(() => {
  const deckUrlMeta = document.querySelector('meta[name="sw-deck-url"]');
  const content = document.getElementById('content');
  const currentPanel = content && content.querySelector('.deck-panel');
  if (!deckUrlMeta || !content || !currentPanel) return;

  const DECK_URL = deckUrlMeta.content;
  const LIKE_URL =
    document.querySelector('meta[name="sw-like-url"]')?.content || '';
  const LIKE_TARGET_URL =
    document.querySelector('meta[name="sw-like-target-url"]')?.content || '';
  const parsedSeenMax = parseInt(
    document.querySelector('meta[name="sw-seen-max"]')?.content || '', 10
  );
  const SEEN_MAX = Number.isFinite(parsedSeenMax) ? parsedSeenMax : 100;
  const HISTORY_MAX = 50;      // cached posts kept for Back; older ones reload
  const QUEUE_TARGET = 3;      // posts to keep queued ahead of the current one
  const QUEUE_REFILL_AT = 2;   // refill once the queue drops to this
  const FETCH_TIMEOUT_MS = 8000;
  const SLOT_IDS = [
    'reactions', 'post-cats', 'url-display-phone',
    'share-dropdown', 'mobile-more-dropdown', 'flag-dropdown', 'flag-btn-label',
  ];

  /** @type {Array<object>} upcoming posts, index 0 is the one rendered behind */
  let queue = [];
  /** @type {Map<string, object>} page_url -> post, so popstate can re-render */
  const byPageUrl = new Map();
  /** @type {object} the post on screen right now */
  let current = null;
  let sliding = false;
  let refillPromise = null;
  let deckBroken = false;
  let historyIndex = 0;

  function slotEl(id) {
    return document.getElementById(id) || document.querySelector(`.${id}`);
  }

  function pageKey() {
    return location.pathname + location.search;
  }

  function identityUrl(post) {
    return post ? post.source_url || post.url : '';
  }

  // --- data ----------------------------------------------------------------

  /* Read from state, not the DOM: between a slide finishing and the next panel
     being mounted, DOM order does not identify the current post. */
  function currentUrl() {
    return identityUrl(current);
  }

  const likeClient = window.createSmallWebLikeClient?.({
    likeUrl: LIKE_URL,
    targetUrl: LIKE_TARGET_URL,
    timeoutMs: FETCH_TIMEOUT_MS,
    currentUrl,
    onTarget(post) {
      remember(post);
      mountLikeTarget(post);
    },
  });

  function remember(post) {
    byPageUrl.set(post.page_url, post);
    while (byPageUrl.size > HISTORY_MAX) {
      byPageUrl.delete(byPageUrl.keys().next().value);
    }
  }

  async function fetchDeck(count, afterUrl) {
    const url = new URL(DECK_URL, location.href);
    url.searchParams.set('count', String(count));
    url.searchParams.set('url', afterUrl);
    url.searchParams.delete('exclude');
    for (const post of [current, ...queue]) {
      const value = identityUrl(post);
      if (value) url.searchParams.append('exclude', value);
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    try {
      const res = await fetch(url.href, {
        signal: controller.signal,
        headers: {Accept: 'application/json'},
      });
      if (!res.ok) return {ok: false, posts: []};
      const data = await res.json();
      return {
        ok: true,
        posts: Array.isArray(data.posts) ? data.posts : [],
      };
    } catch {
      return {ok: false, posts: []};
    } finally {
      clearTimeout(timer);
    }
  }

  /** Build the like target's panel so its iframe is loading before the click. */
  function mountLikeTarget(post) {
    if (!post || sliding) return;
    const selector = `.deck-panel[data-url="${CSS.escape(post.url)}"]`;
    if (content.querySelector(selector)) return;
    const panel = buildPanel(post);
    panel.classList.add('is-preload');
    content.appendChild(panel);
  }

  function updateNextLink() {
    const nextBtn = document.querySelector('.next-button');
    if (!nextBtn) return;
    const href = queue[0]?.page_url || current?.next_link || '';
    if (href) {
      nextBtn.href = href;
      nextBtn.removeAttribute('aria-disabled');
    } else {
      nextBtn.removeAttribute('href');
      if (deckBroken) nextBtn.setAttribute('aria-disabled', 'true');
      else nextBtn.removeAttribute('aria-disabled');
    }
    nextBtn.setAttribute('aria-busy', refillPromise && !queue.length ? 'true' : 'false');
  }

  function refill() {
    if (deckBroken) return Promise.resolve(false);
    if (refillPromise) return refillPromise;

    const anchor = queue[queue.length - 1] || current;
    const anchorUrl = identityUrl(anchor);
    const anchorPageUrl = anchor?.page_url;
    const count = Math.max(1, QUEUE_TARGET - queue.length);

    refillPromise = (async () => {
      const result = await fetchDeck(count, anchorUrl);
      if (!result.ok) return false;

      const anchorIsRelevant =
        current?.page_url === anchorPageUrl ||
        queue.some((post) => post.page_url === anchorPageUrl);
      if (!anchorIsRelevant) return false;

      const known = new Set([current, ...queue].map(identityUrl));
      const posts = result.posts.filter((post) => {
        const key = identityUrl(post);
        if (!key || known.has(key)) return false;
        known.add(key);
        return true;
      });

      if (!posts.length) {
        if (!queue.length) deckBroken = true;
        return false;
      }

      const tail = queue[queue.length - 1] || current;
      if (tail) tail.next_link = posts[0].page_url;
      for (const post of posts) {
        queue.push(post);
        remember(post);
      }
      mountNextPanel();
      return true;
    })().finally(() => {
      refillPromise = null;
      updateNextLink();
    });

    updateNextLink();
    return refillPromise;
  }

  // --- rendering -----------------------------------------------------------

  function buildPanel(post) {
    const panel = document.createElement('div');
    panel.className = 'deck-panel';
    panel.dataset.url = post.url;
    panel.dataset.sourceUrl = identityUrl(post);

    const frame = document.createElement('iframe');
    if (post.flagged) {
      frame.srcdoc =
        '<p>The content of this page has been flagged by users. Click below to open the page in new tab.</p>' +
        `<a href="${escapeAttr(post.url)}" target="_blank" rel="noopener noreferrer">View Flagged Content</a>`;
    } else {
      frame.src = post.url;
    }
    panel.appendChild(frame);
    return panel;
  }

  function escapeAttr(value) {
    return value
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  /** Mount the head of the queue behind the current panel, loading it now. */
  function mountNextPanel() {
    if (sliding) return;
    if (!queue.length) {
      content.querySelector('.deck-panel.is-next')?.remove();
      return;
    }
    const post = queue[0];
    const existing = content.querySelector('.deck-panel.is-next');
    if (existing && existing.dataset.url === post.url) return;
    if (existing) existing.remove();

    const panel = buildPanel(post);
    panel.classList.add('is-next');
    content.appendChild(panel);
  }

  /**
   * Capture the server-rendered post already on screen, so Back can restore it
   * from the same markup instead of forcing a full reload.
   */
  function snapshotCurrent() {
    const panel = content.querySelector('.deck-panel');
    const slots = {};
    for (const id of SLOT_IDS) {
      const el = slotEl(id);
      if (el) slots[id] = el.innerHTML;
    }
    const similar = document.querySelector('.similar-btn');
    const nextBtn = document.querySelector('.next-button');
    return {
      url: panel.dataset.url,
      source_url: panel.dataset.sourceUrl || panel.dataset.url,
      page_url: pageKey(),
      slots,
      similar_href:
        similar && !similar.classList.contains('hidden')
          ? similar.getAttribute('href')
          : '',
      next_link: nextBtn ? nextBtn.getAttribute('href') : null,
      flagged: !!panel.querySelector('iframe[srcdoc]'),
      seen_hash: '',  // the server already recorded this one
    };
  }

  function applySlots(post) {
    for (const [id, html] of Object.entries(post.slots || {})) {
      const el = slotEl(id);
      if (el) el.innerHTML = html;
    }

    const similar = document.querySelector('.similar-btn');
    if (similar) {
      if (post.similar_href) {
        similar.href = post.similar_href;
        similar.classList.remove('hidden');
        similar.removeAttribute('aria-hidden');
        similar.removeAttribute('tabindex');
      } else {
        similar.classList.add('hidden');
        similar.setAttribute('aria-hidden', 'true');
        similar.setAttribute('tabindex', '-1');
      }
    }

  }

  function markSeen(hash) {
    if (!hash) return;
    const raw = document.cookie
      .split('; ')
      .find((c) => c.startsWith('seen='));
    let value = raw ? raw.slice(5) : '';
    try {
      value = decodeURIComponent(value);
    } catch {
      value = '';
    }
    const list = value.split(',').filter(Boolean);
    const next = list.filter((h) => h !== hash);
    next.push(hash);
    const trimmed = next.slice(-SEEN_MAX);
    document.cookie = `seen=${trimmed.join(',')};path=/;max-age=86400;SameSite=Lax`;
  }

  function swapPanel(panel) {
    const outgoing = content.querySelector(
      '.deck-panel:not(.is-next):not(.is-preload)'
    );
    panel.classList.remove('is-next', 'is-preload');
    if (outgoing && outgoing !== panel) outgoing.remove();
  }

  // --- navigation ----------------------------------------------------------

  function show(post, push) {
    if (sliding) return false;
    sliding = true;

    const postKey = identityUrl(post);
    queue = queue.filter((candidate) => identityUrl(candidate) !== postKey);

    let panel = content.querySelector(`.deck-panel[data-url="${CSS.escape(post.url)}"]`);
    if (!panel) {
      panel = buildPanel(post);
      content.appendChild(panel);
    }

    if (push) {
      historyIndex += 1;
      history.pushState(
        {swDeck: true, index: historyIndex, url: post.page_url},
        '',
        post.page_url
      );
    }

    swapPanel(panel);
    current = post;
    applySlots(post);
    markSeen(post.seen_hash);
    document.dispatchEvent(new CustomEvent('sw:content-changed'));

    // A preload built for the post we just left is dead weight, and its iframe
    // would keep running behind the new one.
    for (const stale of content.querySelectorAll('.deck-panel.is-preload')) {
      if (stale !== panel) stale.remove();
    }

    likeClient?.reset();
    sliding = false;
    mountNextPanel();
    updateNextLink();
    if (queue.length <= QUEUE_REFILL_AT) refill();
    return true;
  }

  async function advance() {
    if (sliding) return false;
    if (!queue.length) {
      await refill();
      if (!queue.length) return false;
    }
    return show(queue[0], true);
  }

  function handlePop(key, state) {
    const targetIndex =
      state?.swDeck && Number.isInteger(state.index) ? state.index : null;
    const post = byPageUrl.get(state?.url || key);
    if (!post || targetIndex === null) {
      // A history entry this session never rendered, or one evicted from the
      // cache: let the server serve it.
      location.reload();
      return;
    }

    const movingBack = targetIndex < historyIndex;
    historyIndex = targetIndex;
    if (current && movingBack) {
      const currentKey = identityUrl(current);
      queue = queue.filter((candidate) => identityUrl(candidate) !== currentKey);
      queue.unshift(current);
    } else if (!movingBack) {
      const targetPosition = queue.findIndex(
        (candidate) => identityUrl(candidate) === identityUrl(post)
      );
      if (targetPosition > 0) queue = queue.slice(targetPosition);
    }

    if (current && identityUrl(current) === identityUrl(post)) {
      updateNextLink();
      return;
    }
    show(post, false);
  }

  window.addEventListener('popstate', (event) => {
    handlePop(pageKey(), event.state);
  });

  /* Start loading the like destination as soon as the user reaches for the
     heart. Pointerdown lands well before submit, which is the head start that
     makes the swap feel instant on a first click. */
  for (const evt of ['pointerenter', 'pointerdown', 'focusin']) {
    document.addEventListener(
      evt,
      (event) => {
        if (event.target.closest && event.target.closest('.emoji-form')) {
          likeClient?.prepare();
        }
      },
      true  // capture: pointerenter does not bubble
    );
  }

  /* Liking posts the reaction and swaps to the most similar post, matching
     where the server's POST-and-redirect would have landed. Falls through to
     the plain form whenever there is nowhere to go, so a like is never lost. */
  document.addEventListener('submit', async (event) => {
    const form = event.target.closest && event.target.closest('.emoji-form');
    if (!form) return;
    if (!likeClient) return;
    if (form.dataset.submitting) {
      event.preventDefault();
      return;
    }
    event.preventDefault();
    form.dataset.submitting = 'true';
    const button = form.querySelector('button[type="submit"]');
    if (button) button.disabled = true;
    form.parentElement?.querySelector('.reaction-error')?.remove();

    const submittedFor = currentUrl();
    const targetRequest = likeClient.prepare();
    const refillRequest =
      !queue.length && !deckBroken ? refill() : Promise.resolve(false);
    const [target] = await Promise.all([targetRequest, refillRequest]);
    if (!target && !queue.length) {
      delete form.dataset.submitting;
      if (button) button.disabled = false;
      HTMLFormElement.prototype.submit.call(form);
      return;
    }

    const saved = await likeClient.save(form);
    if (!saved) {
      const error = document.createElement('span');
      error.className = 'reaction-error';
      error.setAttribute('role', 'alert');
      error.textContent = 'Like failed. Try again.';
      form.insertAdjacentElement('afterend', error);
      delete form.dataset.submitting;
      if (button) button.disabled = false;
      return;
    }

    if (currentUrl() !== submittedFor) return;
    if (target) show(target, true);
    else advance();
  });

  // Delegated, so the `n` shortcut clicking .next-button routes here too.
  document.addEventListener('click', (event) => {
    const link = event.target.closest && event.target.closest('.next-button');
    if (!link) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    if (deckBroken && !queue.length && link.hasAttribute('href')) return;
    event.preventDefault();
    advance();
  });

  current = snapshotCurrent();
  remember(current);
  history.replaceState(
    {swDeck: true, index: historyIndex, url: current.page_url},
    '',
    location.href
  );
  refill();
})();
