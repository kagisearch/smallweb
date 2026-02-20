(() => { // IIFE – keeps global scope clean
  const CSS_ID = 'global-dark-mode-style';
  const DARK_CSS = `
    /* apply dark filter ONLY to the embedded pages */
    #content iframe,
    #content-yt iframe {
      filter: invert(90%) hue-rotate(180deg);
      background:#fff;          /* keeps blank areas white pre-inversion */
    }
  `;

  const IFRAME_REINVERT_CSS = `
    /* runs *inside* the iframe document */
    html { background:#fff !important; }

    img,
    video,
    svg,
    [style*="background-image"]:not([data-no-dark-invert]) {
      filter: invert(100%) hue-rotate(180deg) brightness(105%) contrast(105%);
    }
  `;

  /* simpler icons */
  const moonSVG = '<svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor"><path d="M12 2a10 10 0 000 20 9.93 9.93 0 006.77-2.67A10 10 0 0112 2z"/></svg>';
  const sunSVG = '<svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor"><circle cx="12" cy="12" r="5"/><g stroke="currentColor" stroke-width="2"><line x1="12" y1="1"  x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="1"  y1="12" x2="3"  y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="4.22"  x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64"  x2="19.78" y2="4.22"/></g></svg>';

  const btn = document.getElementById('dark-mode-toggle');
  if (!btn) return;

  function updateIframeStyles(enable) {
    document.querySelectorAll('#content iframe, #content-yt iframe').forEach((ifr) => {
      try {
        const doc = ifr.contentDocument || ifr.contentWindow?.document;
        if (!doc) return; // cannot access (probably x-origin)
        const STYLE_ID = 'iframe-dark-mode-style';
        let s = doc.getElementById(STYLE_ID);

        if (enable) {
          if (!s) {
            s = doc.createElement('style');
            s.id = STYLE_ID;
            s.textContent = IFRAME_REINVERT_CSS;
            doc.head.appendChild(s);
          }
        } else {
          if (s) s.remove();
        }
      } catch (_) {
        /* cross-origin – ignore */
      }
    });
  }

  function applyDark() {
    if (document.getElementById(CSS_ID)) return; // already on

    const style = document.createElement('style');
    style.id = CSS_ID;
    style.textContent = DARK_CSS;
    document.head.appendChild(style);

    btn.innerHTML = sunSVG;
    localStorage.setItem('darkMode', 'on');

    updateIframeStyles(true); // NEW: inject into current frames
    document
      .querySelectorAll('#content iframe, #content-yt iframe')
      .forEach((ifr) => ifr.addEventListener('load', () => updateIframeStyles(true)));
  }

  function removeDark() {
    const style = document.getElementById(CSS_ID);
    if (style) style.remove();

    btn.innerHTML = moonSVG;
    localStorage.setItem('darkMode', 'off');

    updateIframeStyles(false); // NEW: remove from reachable frames
  }

  // Initialise state from localStorage
  localStorage.getItem('darkMode') === 'on' ? applyDark() : removeDark();

  // Toggle on click
  btn.addEventListener('click', () =>
    document.getElementById(CSS_ID) ? removeDark() : applyDark()
  );
})();
