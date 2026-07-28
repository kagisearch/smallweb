// Append the current post's hash to the `seen` cookie at real page activation.
// The server suppresses Set-Cookie on prefetch/prerender requests (so a
// speculative response cannot mark unviewed URLs as seen), which means a
// navigation served from a speculative load carries no cookie update at all.
// When that happened the cookie froze and repeats became common, especially
// in small pools like ?cat=hardware. Marking the view here, on real load and
// on prerender activation, keeps the cookie correct no matter how the
// response was delivered. Deck advances are marked by deck.js instead.
(() => {
  const meta = document.querySelector('meta[name="sw-seen-hash"]');
  if (!meta || !meta.content) return;
  const hash = meta.content;
  const maxRaw = document.querySelector('meta[name="sw-seen-max"]');
  const max = Math.max(1, parseInt(maxRaw && maxRaw.content, 10) || 100);

  function update() {
    const m = document.cookie.match(/(?:^|;\s*)seen=([^;]*)/);
    const raw = m ? decodeURIComponent(m[1]) : '';
    const list = raw ? raw.split(',').filter(x => x && x !== hash) : [];
    list.push(hash);
    while (list.length > max) list.shift();
    document.cookie = 'seen=' + list.join(',') + ';path=/;max-age=86400;SameSite=Lax';
  }

  if (document.prerendering) {
    document.addEventListener('prerenderingchange', update, { once: true });
  } else {
    update();
  }
})();
