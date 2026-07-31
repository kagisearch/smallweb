/*
 * State-machine tests for static/deck.js.
 *
 * deck.js is a browser IIFE, so it runs here in a vm context against a shim
 * that implements only what it touches: the handful of selectors it queries,
 * class/dataset/attribute access, history, location and fetch. The point is the
 * queue and history bookkeeping, not layout, so nothing here renders.
 *
 * Run: node --test app/tests/deck.test.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const DECK_JS = path.join(
  path.dirname(fileURLToPath(import.meta.url)), '..', 'static', 'deck.js'
);

const PREFIX = '/smallweb/';
const A = 'https://a.example/1';

// --- DOM shim ----------------------------------------------------------------

const kebab = (s) => s.replace(/[A-Z]/g, (c) => '-' + c.toLowerCase());

/** Compound selectors only: tag, .class, #id, [attr="v"], :not(.class). */
function matches(el, selector) {
  const notRe = /:not\(\.([\w-]+)\)/g;
  let m;
  while ((m = notRe.exec(selector))) if (el.classes.has(m[1])) return false;
  const base = selector.replace(notRe, '');
  const tokens = base.match(/^[a-zA-Z]+|\.[\w-]+|#[\w-]+|\[[\w-]+="[^"]*"\]/g) || [];
  for (const token of tokens) {
    if (token[0] === '.') {
      if (!el.classes.has(token.slice(1))) return false;
    } else if (token[0] === '#') {
      if (el.attrs.get('id') !== token.slice(1)) return false;
    } else if (token[0] === '[') {
      const [, name, value] = token.match(/\[([\w-]+)="([^"]*)"\]/);
      if (el.attrs.get(name) !== value) return false;
    } else if (el.tagName !== token.toUpperCase()) {
      return false;
    }
  }
  return true;
}

class El {
  constructor(tag) {
    this.tagName = tag.toUpperCase();
    this.childNodes = [];
    this.parent = null;
    this.attrs = new Map();
    this.classes = new Set();
    this.innerHTML = '';
    this.classList = {
      add: (...names) => names.forEach((n) => this.classes.add(n)),
      remove: (...names) => names.forEach((n) => this.classes.delete(n)),
      contains: (name) => this.classes.has(name),
    };
    this.dataset = new Proxy({}, {
      get: (_, key) => this.attrs.get('data-' + kebab(String(key))),
      set: (_, key, value) => {
        this.attrs.set('data-' + kebab(String(key)), String(value));
        return true;
      },
    });
  }

  set className(value) {
    this.classes = new Set(String(value).split(/\s+/).filter(Boolean));
  }

  get className() {
    return [...this.classes].join(' ');
  }

  set href(value) {
    this.attrs.set('href', String(value));
  }

  get href() {
    return this.attrs.get('href');
  }

  setAttribute(name, value) {
    this.attrs.set(name, String(value));
  }

  getAttribute(name) {
    return this.attrs.has(name) ? this.attrs.get(name) : null;
  }

  removeAttribute(name) {
    this.attrs.delete(name);
  }

  hasAttribute(name) {
    return this.attrs.has(name);
  }

  appendChild(child) {
    child.parent = this;
    this.childNodes.push(child);
    return child;
  }

  remove() {
    if (!this.parent) return;
    this.parent.childNodes = this.parent.childNodes.filter((c) => c !== this);
    this.parent = null;
  }

  *walk() {
    for (const child of this.childNodes) {
      yield child;
      yield* child.walk();
    }
  }

  querySelector(selector) {
    for (const node of this.walk()) if (matches(node, selector)) return node;
    return null;
  }

  querySelectorAll(selector) {
    return [...this.walk()].filter((node) => matches(node, selector));
  }

  closest(selector) {
    let node = this;
    while (node) {
      if (matches(node, selector)) return node;
      node = node.parent;
    }
    return null;
  }
}

function makeEl(tag, attrs = {}, classes = []) {
  const el = new El(tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  classes.forEach((c) => el.classes.add(c));
  return el;
}

// --- harness -----------------------------------------------------------------

const pageUrl = (url) => PREFIX + '?url=' + url;

/** A post shaped like one item of the /api/deck payload. */
function deckPost(url) {
  return {
    url,
    source_url: url,
    page_url: pageUrl(url),
    next_link: null,
    seen_hash: url.slice(-4),
    flagged: false,
    similar_href: '',
    slots: {},
  };
}

/**
 * Boot deck.js on a page showing post A.
 * `batches` is consumed one /api/deck response at a time.
 */
function boot({batches = [], nextHref = pageUrl('https://z.example/0')} = {}) {
  const root = new El('html');
  root.appendChild(makeEl('meta', {name: 'sw-deck-url'})).content =
    PREFIX + 'api/deck';
  root.appendChild(makeEl('meta', {name: 'sw-seen-max'})).content = '100';

  const nextBtn = makeEl('a', {href: nextHref}, ['next-button']);
  root.appendChild(nextBtn);

  const content = makeEl('div', {id: 'content'});
  content.appendChild(
    makeEl('div', {'data-url': A, 'data-source-url': A}, ['deck-panel'])
  );
  root.appendChild(content);

  const listeners = new Map();
  const document = {
    cookie: '',
    querySelector: (s) => root.querySelector(s),
    querySelectorAll: (s) => root.querySelectorAll(s),
    getElementById: (id) => root.querySelector('#' + id),
    createElement: (tag) => new El(tag),
    addEventListener: (type, fn) => {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(fn);
    },
    dispatchEvent: (event) => {
      for (const fn of listeners.get(event.type) || []) fn(event);
      return true;
    },
  };

  const location = {
    pathname: PREFIX,
    search: '?url=' + A,
    get href() {
      return 'https://kagi.com' + this.pathname + this.search;
    },
    reload() {
      this.reloaded = (this.reloaded || 0) + 1;
    },
  };

  const entries = [];
  const history = {
    pushState(state, _title, url) {
      if (history.failNextPush) {
        history.failNextPush = false;
        throw new Error('too many pushState calls');
      }
      entries.push({state, url});
      const [pathname, search] = url.split('?');
      location.pathname = pathname;
      location.search = search ? '?' + search : '';
    },
    replaceState(state, _title, url) {
      entries.push({state, url, replaced: true});
    },
  };

  const fetchCalls = [];
  const win = {addEventListener: document.addEventListener};

  const context = {
    window: win,
    document,
    history,
    location,
    CSS: {escape: (s) => s},  // attribute values need no escaping for matches()
    CustomEvent: class {
      constructor(type) {
        this.type = type;
      }
    },
    AbortController,
    URL,
    setTimeout,
    clearTimeout,
    fetch: async (href) => {
      fetchCalls.push(href);
      const posts = batches.length ? batches.shift() : [];
      return {ok: true, json: async () => ({posts})};
    },
  };
  vm.runInNewContext(fs.readFileSync(DECK_JS, 'utf8'), context);

  const flush = async () => {
    for (let i = 0; i < 6; i++) await new Promise((r) => setTimeout(r, 0));
  };

  return {
    content,
    history,
    entries,
    fetchCalls,
    location,
    flush,
    nextHref: () => nextBtn.getAttribute('href'),
    /** data-url of the panel that is actually on top. */
    shown: () => {
      const panel = content.querySelector(
        '.deck-panel:not(.is-next):not(.is-preload)'
      );
      return panel ? panel.getAttribute('data-url') : null;
    },
    clickNext: async () => {
      document.dispatchEvent({
        type: 'click',
        target: nextBtn,
        button: 0,
        metaKey: false,
        ctrlKey: false,
        shiftKey: false,
        preventDefault() {},
      });
      await flush();
    },
    pop: async (state) => {
      for (const fn of listeners.get('popstate') || []) fn({state});
      await flush();
    },
  };
}

// --- tests -------------------------------------------------------------------

const B = 'https://b.example/2';
const C = 'https://c.example/3';
const D = 'https://d.example/4';

test('a pop onto the post on screen does not queue that post', async () => {
  // An iframe navigation inside a post adds a history entry of its own, so a
  // Back can land on an entry that names the post already displayed. Queueing
  // it there made the following Next replay the same post.
  const deck = boot({batches: [[deckPost(B), deckPost(C), deckPost(D)]]});
  await deck.flush();

  await deck.clickNext();
  assert.equal(deck.shown(), B);

  await deck.pop({swDeck: true, index: 0, url: pageUrl(B)});
  assert.notEqual(deck.nextHref(), pageUrl(B), 'Next must not point at itself');

  await deck.clickNext();
  assert.equal(deck.shown(), C);
});

test('a repeated pop onto the post on screen still advances', async () => {
  const deck = boot({batches: [[deckPost(B), deckPost(C), deckPost(D)]]});
  await deck.flush();
  await deck.clickNext();

  for (let i = 0; i < 3; i++) {
    await deck.pop({swDeck: true, index: 0, url: pageUrl(B)});
  }
  await deck.clickNext();
  assert.equal(deck.shown(), C);
});

test('a deck response that repeats the current post is never shown', async () => {
  const deck = boot({batches: [[deckPost(A), deckPost(B)]]});
  await deck.flush();
  assert.notEqual(deck.nextHref(), pageUrl(A));

  await deck.clickNext();
  assert.equal(deck.shown(), B);
});

test('a throttled pushState does not latch the deck', async () => {
  // pushState throws once the browser decides it is being called too often.
  // Leaving `sliding` true there froze every later advance and every popstate.
  const deck = boot({batches: [[deckPost(B), deckPost(C), deckPost(D)]]});
  await deck.flush();

  deck.history.failNextPush = true;
  await deck.clickNext();
  assert.equal(deck.shown(), B, 'advance must survive a failed pushState');

  await deck.clickNext();
  assert.equal(deck.shown(), C);
});

test('a self-referential server next_link is not offered', async () => {
  // _pick_next_entry loops a one-post pool back to itself, and /api/deck has
  // nothing to add for that pool. Following the anchor would be a full
  // navigation back to the page the reader is already on.
  const deck = boot({batches: [[]], nextHref: PREFIX + '?url=' + A});
  await deck.flush();

  assert.equal(deck.nextHref(), null, 'Next must not link to the current page');
});
