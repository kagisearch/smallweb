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
  const parsedSeenMax = parseInt(
    document.querySelector('meta[name="sw-seen-max"]')?.content || '', 10
  );
  const SEEN_MAX = Number.isFinite(parsedSeenMax) ? parsedSeenMax : 100;
  // Slide transition is off: posts swap instantly. Flip to true to bring the
  // right-to-left slide in slideIn() back.
  const SLIDE_ENABLED = false;
  const HISTORY_MAX = 50;      // cached posts kept for Back; older ones reload
  const QUEUE_TARGET = 3;      // posts to keep queued ahead of the current one
  const QUEUE_REFILL_AT = 2;   // refill once the queue drops to this
  const SLIDE_MS = 350;
  const FETCH_TIMEOUT_MS = 8000;
  const SLOT_IDS = [
    'reactions', 'post-cats', 'url-display-phone',
    'share-dropdown', 'mobile-more-dropdown', 'flag-dropdown', 'flag-btn-label',
  ];

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /** @type {Array<object>} upcoming posts, index 0 is the one rendered behind */
  let queue = [];
  /** @type {Map<string, object>} page_url -> post, so popstate can re-render */
  const byPageUrl = new Map();
  /** @type {object} the post on screen right now */
  let current = null;
  let sliding = false;
  let fetching = false;
  let deckBroken = false;
  /** @type {string|null} a popstate that arrived mid-slide, applied afterwards */
  let pendingPop = null;

  function slotEl(id) {
    return document.getElementById(id) || document.querySelector(`.${id}`);
  }

  function pageKey() {
    return location.pathname + location.search;
  }

  // --- data ----------------------------------------------------------------

  /* Read from state, not the DOM: between a slide finishing and the next panel
     being mounted, DOM order does not identify the current post. */
  function currentUrl() {
    return current ? current.url : '';
  }

  function remember(post) {
    byPageUrl.set(post.page_url, post);
    while (byPageUrl.size > HISTORY_MAX) {
      byPageUrl.delete(byPageUrl.keys().next().value);
    }
  }

  async function fetchDeck(count) {
    const sep = DECK_URL.includes('?') ? '&' : '?';
    const url = `${DECK_URL}${sep}count=${count}&url=${encodeURIComponent(currentUrl())}`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    try {
      const res = await fetch(url, {
        signal: controller.signal,
        headers: {Accept: 'application/json'},
      });
      if (!res.ok) return [];
      const data = await res.json();
      return Array.isArray(data.posts) ? data.posts : [];
    } catch {
      return [];
    } finally {
      clearTimeout(timer);
    }
  }

  async function refill() {
    if (fetching || deckBroken) return;
    fetching = true;
    try {
      const posts = await fetchDeck(QUEUE_TARGET);
      if (!posts.length) {
        // Nothing to queue: leave Next as a plain link rather than a dead button.
        if (!queue.length) deckBroken = true;
        return;
      }
      for (const post of posts) {
        queue.push(post);
        remember(post);
      }
      mountNextPanel();
    } finally {
      fetching = false;
    }
  }

  // --- rendering -----------------------------------------------------------

  function buildPanel(post) {
    const panel = document.createElement('div');
    panel.className = 'deck-panel';
    panel.dataset.url = post.url;
    if (post.no_embed) panel.dataset.noEmbed = '1';

    const frame = document.createElement('iframe');
    // Same order as index.html: a flagged post keeps the flag interstitial even
    // when its domain also refuses framing.
    if (post.flagged) {
      frame.srcdoc =
        '<p>The content of this page has been flagged by users. Click below to open the page in new tab.</p>' +
        `<a href="${escapeAttr(post.url)}" target="_blank" rel="noopener noreferrer">View Flagged Content</a>`;
    } else if (post.no_embed) {
      frame.srcdoc =
        '<p>This site cannot be displayed here. Click below to open it in a new tab.</p>' +
        `<a href="${escapeAttr(post.url)}" target="_blank" rel="noopener noreferrer">Open in new tab</a>`;
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
    if (sliding || !queue.length) return;
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
    // Both interstitials use srcdoc, so the flag has to be ruled out explicitly
    // or Back would re-render a non-embeddable post as a flagged one.
    const noEmbed = panel.dataset.noEmbed === '1';
    const slots = {};
    for (const id of SLOT_IDS) {
      const el = slotEl(id);
      if (el) slots[id] = el.innerHTML;
    }
    const similar = document.querySelector('.similar-btn');
    const nextBtn = document.querySelector('.next-button');
    return {
      url: panel.dataset.url,
      page_url: pageKey(),
      slots,
      similar_href:
        similar && !similar.classList.contains('hidden')
          ? similar.getAttribute('href')
          : '',
      next_link: nextBtn ? nextBtn.getAttribute('href') : null,
      flagged: !noEmbed && !!panel.querySelector('iframe[srcdoc]'),
      no_embed: noEmbed,
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

    const nextBtn = document.querySelector('.next-button');
    if (nextBtn && post.next_link) nextBtn.href = post.next_link;
  }

  function markSeen(hash) {
    if (!hash) return;
    const raw = document.cookie
      .split('; ')
      .find((c) => c.startsWith('seen='));
    const list = raw ? decodeURIComponent(raw.slice(5)).split(',').filter(Boolean) : [];
    const next = list.filter((h) => h !== hash);
    next.push(hash);
    const trimmed = next.slice(-SEEN_MAX);
    document.cookie = `seen=${trimmed.join(',')};path=/;max-age=86400;SameSite=Lax`;
  }

  // --- transition ----------------------------------------------------------

  /**
   * Slide `panel` in over the current one, right to left for the next post and
   * left to right going back. Resolves once state is committed, whether the
   * transition fired or the timeout guard did.
   */
  function slideIn(panel, direction) {
    return new Promise((resolve) => {
      const outgoing = content.querySelector('.deck-panel:not(.is-next)');
      panel.classList.remove('is-next');

      const finish = () => {
        if (outgoing && outgoing !== panel) outgoing.remove();
        panel.classList.remove('is-sliding');
        panel.style.transition = '';
        panel.style.transform = '';
        if (outgoing) {
          outgoing.style.transition = '';
          outgoing.style.transform = '';
        }
        resolve();
      };

      if (!SLIDE_ENABLED || reduceMotion) {
        finish();
        return;
      }

      const from = direction === 'next' ? '100%' : '-100%';
      const outTo = direction === 'next' ? '-100%' : '100%';

      panel.classList.add('is-sliding');
      panel.style.transition = 'none';
      panel.style.transform = `translateX(${from})`;
      if (outgoing) {
        outgoing.style.transition = 'none';
        outgoing.style.transform = 'translateX(0)';
      }

      // Two frames: the first commits the start position, the second animates.
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          const ease = `transform ${SLIDE_MS}ms cubic-bezier(0.4, 0, 0.2, 1)`;
          panel.style.transition = ease;
          panel.style.transform = 'translateX(0)';
          if (outgoing) {
            outgoing.style.transition = ease;
            outgoing.style.transform = `translateX(${outTo})`;
          }
        });
      });

      // A dropped transitionend must not wedge the deck.
      let done = false;
      const once = () => {
        if (done) return;
        done = true;
        panel.removeEventListener('transitionend', once);
        clearTimeout(guard);
        finish();
      };
      const guard = setTimeout(once, SLIDE_MS + 250);
      panel.addEventListener('transitionend', once);
    });
  }

  // --- navigation ----------------------------------------------------------

  async function show(post, direction, push) {
    if (sliding) return;
    sliding = true;

    queue = queue.filter((p) => p.url !== post.url);

    let panel = content.querySelector(`.deck-panel[data-url="${CSS.escape(post.url)}"]`);
    if (!panel) {
      panel = buildPanel(post);
      content.appendChild(panel);
    }

    // Push before the slide, not after: a Back pressed mid-slide needs the
    // entry to already exist, or it walks off the site instead of going back.
    if (push) history.pushState({url: post.page_url}, '', post.page_url);

    await slideIn(panel, direction);
    sliding = false;

    current = post;
    applySlots(post);
    markSeen(post.seen_hash);
    document.dispatchEvent(new CustomEvent('sw:content-changed'));

    mountNextPanel();
    if (queue.length <= QUEUE_REFILL_AT) refill();

    // A Back pressed mid-slide would otherwise leave the address bar pointing
    // at a post that is not on screen.
    if (pendingPop !== null) {
      const key = pendingPop;
      pendingPop = null;
      handlePop(key);
    }
  }

  async function advance() {
    if (sliding) return false;
    if (!queue.length) {
      refill();
      return false;
    }
    await show(queue[0], 'next', true);
    return true;
  }

  function handlePop(key) {
    const post = byPageUrl.get(key);
    if (!post) {
      // A history entry this session never rendered, or one evicted from the
      // cache: let the server serve it.
      location.reload();
      return;
    }
    if (current && current.url === post.url) return;  // already on screen
    // The post being left goes back to the front of the queue, so Next returns
    // to it rather than skipping ahead to an unrelated one.
    if (current && !queue.some((p) => p.url === current.url)) {
      queue.unshift(current);
    }
    show(post, 'prev', false);
  }

  window.addEventListener('popstate', () => {
    if (sliding) {
      pendingPop = pageKey();
      return;
    }
    handlePop(pageKey());
  });

  // Delegated, so the `n` shortcut clicking .next-button routes here too.
  document.addEventListener('click', (event) => {
    const link = event.target.closest && event.target.closest('.next-button');
    if (!link) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    if (deckBroken || !queue.length) return;  // let the anchor navigate
    event.preventDefault();
    advance();
  });

  current = snapshotCurrent();
  remember(current);
  history.replaceState({url: current.page_url}, '', location.href);
  refill();
})();
