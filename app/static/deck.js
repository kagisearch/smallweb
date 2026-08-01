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
  /* Bumped by every history traversal. A traversal restores the documents the
     target entry recorded for each frame slot, so an iframe that lived through
     one can be sitting on another post's page (or about:blank) while its src
     still names this post -- the header updates, the frame does not. Panels
     built before the last traversal are therefore not reusable. */
  let historyEpoch = 0;

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

  /** A panel whose iframe a history traversal may have re-pointed. */
  function isStale(panel) {
    return !panel || panel.dataset.epoch !== String(historyEpoch);
  }

  /** Build the like target's panel so its iframe is loading before the click. */
  function mountLikeTarget(post) {
    if (!post || sliding) return;
    const selector = `.deck-panel[data-url="${CSS.escape(post.url)}"]`;
    const existing = content.querySelector(selector);
    // Never drop the panel on screen: only show() replaces that one.
    if (existing && (!isStale(existing) || existing.dataset.url === current?.url)) return;
    if (existing) existing.remove();
    const panel = buildPanel(post);
    panel.classList.add('is-preload');
    content.appendChild(panel);
  }

  function updateNextLink() {
    const nextBtn = document.querySelector('.next-button');
    if (!nextBtn) return;
    // A server-rendered next_link points back at this post when the pool holds
    // nothing else (a one-result search, a one-post category). Offering it
    // would make Next a full navigation that lands where the reader already is.
    const fallback =
      current && current.next_link && current.next_link !== current.page_url
        ? current.next_link
        : '';
    const href = queue[0]?.page_url || fallback;
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
    panel.dataset.epoch = String(historyEpoch);

    const frame = document.createElement('iframe');
    // A name of its own keeps the browser from matching this frame slot to a
    // document another post recorded there.
    frame.name = 'sw-post-' + (post.seen_hash || '');
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
    if (existing && existing.dataset.url === post.url && !isStale(existing)) return;
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
    // Rendering the post already on screen is never an advance: it would push a
    // duplicate history entry and change nothing the reader can see. Whatever
    // handed us this post is wrong, and swallowing it here keeps that bug off
    // the screen.
    if (!post || (current && identityUrl(post) === currentUrl())) return false;
    sliding = true;

    try {
      const postKey = identityUrl(post);
      queue = queue.filter((candidate) => identityUrl(candidate) !== postKey);

      let panel = content.querySelector(`.deck-panel[data-url="${CSS.escape(post.url)}"]`);
      // A panel from before the last traversal may be showing someone else's
      // page behind a src that still names this post. Reloading is cheap next
      // to putting the wrong post on screen under this post's header.
      if (panel && isStale(panel)) {
        panel.remove();
        panel = null;
      }
      if (!panel) {
        panel = buildPanel(post);
        content.appendChild(panel);
      }

      if (push) {
        try {
          history.pushState(
            {swDeck: true, index: historyIndex + 1, url: post.page_url},
            '',
            post.page_url
          );
          historyIndex += 1;
        } catch {
          // Throttled by the browser: advance anyway, the address bar lags.
          // Leaving historyIndex alone keeps it matched to the entries that
          // do exist, so a later popstate still resolves.
        }
      }

      swapPanel(panel);
      current = post;
      // The exclusion set just changed, so a pool that had nothing to add for
      // the previous post is worth asking again.
      deckBroken = false;
      applySlots(post);
      markSeen(post.seen_hash);
      document.dispatchEvent(new CustomEvent('sw:content-changed'));

      // A preload built for the post we just left is dead weight, and its
      // iframe would keep running behind the new one.
      for (const stale of content.querySelectorAll('.deck-panel.is-preload')) {
        if (stale !== panel) stale.remove();
      }

      likeClient?.reset();
    } finally {
      // Anything that throws mid-swap must not leave the deck latched: sliding
      // gates every advance and every popstate render.
      sliding = false;
    }

    mountNextPanel();
    updateNextLink();
    if (queue.length <= QUEUE_REFILL_AT) refill();
    return true;
  }

  /** Drop any queued copy of the post on screen; advancing to it is a no-op. */
  function dropCurrentFromQueue() {
    const key = currentUrl();
    if (!key) return;
    queue = queue.filter((candidate) => identityUrl(candidate) !== key);
  }

  async function advance() {
    if (sliding) return false;
    dropCurrentFromQueue();
    if (!queue.length) {
      await refill();
      dropCurrentFromQueue();
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

    // Landing on the post already on screen: there is nothing to render, and
    // the queue must not be touched. An iframe navigation inside a post adds a
    // history entry of its own, so this fires on ordinary browsing; queueing
    // `current` here would leave it at the head and replay it on the next
    // advance, which is only ever undone by the show() below.
    if (current && identityUrl(current) === identityUrl(post)) {
      updateNextLink();
      return;
    }

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

    show(post, false);
  }

  window.addEventListener('popstate', (event) => {
    historyEpoch += 1;
    handlePop(pageKey(), event.state);
  });

  /* A back/forward that restored this whole document from the bfcache is a
     traversal too, and it fires no popstate when the entry is the one we were
     already on. */
  window.addEventListener('pageshow', (event) => {
    if (event.persisted) historyEpoch += 1;
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
    // show() refuses a target that is already on screen, so fall through to a
    // plain advance rather than leaving the reader where they liked.
    if (!target || !show(target, true)) advance();
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
