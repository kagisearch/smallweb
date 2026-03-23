(() => {
  const CLOSE_ALL_EVENT = 'smallweb:close-all-dropdowns';
  const toggle = document.getElementById('catToggle');
  const dropdown = document.getElementById('catDropdown');
  const backdrop = document.getElementById('catBackdrop');
  const header = document.getElementById('header');
  if (!toggle || !dropdown || !backdrop) return;

  const allItems = [...dropdown.querySelectorAll('.cat-item')];

  // ── Category exclusion (eye toggle) ──
  const STORAGE_KEY = 'sw_excluded_cats';

  function getExcluded() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? new Set(raw.split(',').filter(Boolean)) : new Set();
    } catch { return new Set(); }
  }

  function saveExcluded(set) {
    const val = [...set].join(',');
    try { localStorage.setItem(STORAGE_KEY, val); } catch {}
    document.cookie = `sw_excluded_cats=${encodeURIComponent(val)};path=/;max-age=31536000;SameSite=Lax`;
  }

  function applyExcludedUI() {
    const excluded = getExcluded();
    dropdown.querySelectorAll('.cat-item-row').forEach(row => {
      const slug = row.dataset.slug;
      row.classList.toggle('excluded', excluded.has(slug));
    });
    // Update toggle label to show count
    const label = toggle.querySelector('.category-toggle-label');
    if (label && !label.dataset.originalText) {
      label.dataset.originalText = label.textContent.trim();
    }
    if (label && excluded.size > 0 && label.dataset.originalText === 'Topics') {
      label.textContent = `Topics (-${excluded.size})`;
    } else if (label && excluded.size === 0 && label.dataset.originalText === 'Topics') {
      label.textContent = 'Topics';
    }
  }

  // Sync cookie on page load
  saveExcluded(getExcluded());
  applyExcludedUI();

  // ── Sticky category (persist selected topic across visits) ──
  const STICKY_KEY = 'sw_sticky_cat';
  const urlCat = new URLSearchParams(window.location.search).get('cat');

  if (urlCat) {
    localStorage.setItem(STICKY_KEY, urlCat);
    document.cookie = `sw_sticky_cat=${encodeURIComponent(urlCat)};path=/;max-age=31536000;SameSite=Lax`;
  }

  const clearBtn = document.querySelector('.cat-inline-clear');
  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      localStorage.removeItem(STICKY_KEY);
      document.cookie = 'sw_sticky_cat=;path=/;max-age=0;SameSite=Lax';
    });
  }

  let excludedChanged = false;

  dropdown.addEventListener('click', (e) => {
    const eyeBtn = e.target.closest('.cat-eye');
    if (!eyeBtn) return;
    e.preventDefault();
    e.stopPropagation();
    const slug = eyeBtn.dataset.slug;
    const excluded = getExcluded();
    if (excluded.has(slug)) {
      excluded.delete(slug);
    } else {
      excluded.add(slug);
    }
    saveExcluded(excluded);
    applyExcludedUI();
    excludedChanged = true;
  });
  let focusIndex = -1;

  function getDropdownTop() {
    if (!header) return 50;
    return Math.round(header.getBoundingClientRect().bottom);
  }

  function getViewportHeight() {
    return Math.round(window.visualViewport?.height || window.innerHeight);
  }

  function positionDropdown() {
    const dropdownTop = getDropdownTop();
    dropdown.style.top = `${dropdownTop}px`;
    dropdown.style.maxHeight = `${Math.max(160, getViewportHeight() - dropdownTop - 8)}px`;

    const dropdownWidth = dropdown.getBoundingClientRect().width;
    const toggleRect = toggle.getBoundingClientRect();
    const maxLeft = Math.max(0, window.innerWidth - dropdownWidth);
    const panelLeft = Math.min(Math.max(toggleRect.left + toggleRect.width / 2 - dropdownWidth / 2, 0), maxLeft);

    dropdown.style.left = `${Math.round(panelLeft)}px`;
  }

  function openDropdown() {
    document.dispatchEvent(
      new CustomEvent(CLOSE_ALL_EVENT, {detail: {except: 'category'}})
    );
    dropdown.classList.add('open');
    backdrop.classList.add('open');
    toggle.classList.add('active');
    toggle.setAttribute('aria-expanded', 'true');
    focusIndex = -1;
    positionDropdown();
  }

  function closeDropdown(restoreFocus = true) {
    dropdown.classList.remove('open');
    backdrop.classList.remove('open');
    toggle.classList.remove('active');
    toggle.setAttribute('aria-expanded', 'false');
    if (excludedChanged) {
      excludedChanged = false;
      window.location.reload();
      return;
    }
    if (restoreFocus) toggle.focus();
  }

  toggle.addEventListener('click', () => {
    dropdown.classList.contains('open') ? closeDropdown() : openDropdown();
  });

  backdrop.addEventListener('click', () => closeDropdown(false));

  document.addEventListener(CLOSE_ALL_EVENT, (event) => {
    const exceptId = event.detail?.except;
    if (exceptId !== 'category' && dropdown.classList.contains('open')) {
      closeDropdown(false);
    }
  });

  document.addEventListener('keydown', (e) => {
    const isOpen = dropdown.classList.contains('open');
    if (e.key === 'Escape' && isOpen) {
      closeDropdown();
      document.dispatchEvent(new CustomEvent(CLOSE_ALL_EVENT, {detail: {except: null}}));
      return;
    }
    if (!isOpen) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      focusIndex = Math.min(focusIndex + 1, allItems.length - 1);
      updateFocus();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      focusIndex = Math.max(focusIndex - 1, 0);
      updateFocus();
    } else if (e.key === 'Enter' && focusIndex >= 0) {
      e.preventDefault();
      window.location.href = allItems[focusIndex].href;
    } else if (e.key.length === 1 && /[a-z]/i.test(e.key)) {
      const char = e.key.toLowerCase();
      const idx = allItems.findIndex((i) =>
        i.querySelector('.cat-name').textContent.toLowerCase().startsWith(char)
      );
      if (idx >= 0) {
        focusIndex = idx;
        updateFocus();
      }
    }
  });

  window.addEventListener('resize', () => {
    if (dropdown.classList.contains('open')) {
      positionDropdown();
    }
  });

  const visualViewport = window.visualViewport;
  if (visualViewport) {
    const onViewportChange = () => {
      if (dropdown.classList.contains('open')) {
        positionDropdown();
      }
    };
    visualViewport.addEventListener('resize', onViewportChange);
    visualViewport.addEventListener('scroll', onViewportChange);
  }

  function updateFocus() {
    allItems.forEach((item, i) => {
      if (i === focusIndex) {
        item.classList.add('cat-kb-focus');
        item.scrollIntoView({block: 'nearest'});
      } else {
        item.classList.remove('cat-kb-focus');
      }
    });
  }
})();
