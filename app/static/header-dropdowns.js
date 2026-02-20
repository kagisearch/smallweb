(() => {
  const CLOSE_ALL_EVENT = 'smallweb:close-all-dropdowns';

  const entries = Array.from(document.querySelectorAll('.dropdown-container'))
    .map((container) => {
      const trigger = container.querySelector('[data-dropdown-trigger]');
      const panel = container.querySelector('.dropdown-panel');
      if (!trigger || !panel) return null;
      const alignRight =
        container.classList.contains('right-dropdown-container') ||
        container.closest('.right') !== null;
      return {container, trigger, panel, alignRight};
    })
    .filter(Boolean);

  if (!entries.length) return;
  const header = document.getElementById('header');

  function getPanelTop() {
    if (!header) return 50;
    return Math.round(header.getBoundingClientRect().bottom);
  }

  function positionEntry(entry) {
    entry.panel.style.top = `${getPanelTop()}px`;

    const triggerRect = entry.trigger.getBoundingClientRect();
    const panelWidth = entry.panel.getBoundingClientRect().width;
    const maxLeft = Math.max(0, window.innerWidth - panelWidth);

    let panelLeft;
    if (entry.alignRight) {
      panelLeft = triggerRect.right - panelWidth;
    } else {
      panelLeft = triggerRect.left;
    }

    panelLeft = Math.min(Math.max(panelLeft, 0), maxLeft);
    entry.panel.style.left = `${Math.round(panelLeft)}px`;
  }

  function positionOpenEntries() {
    entries.forEach((entry) => {
      if (entry.panel.classList.contains('open')) {
        positionEntry(entry);
      }
    });
  }

  function closeEntry(entry, restoreFocus = false) {
    entry.panel.classList.remove('open');
    entry.panel.setAttribute('aria-hidden', 'true');
    entry.trigger.setAttribute('aria-expanded', 'false');
    if (restoreFocus) {
      entry.trigger.focus();
    }
  }

  function openEntry(entry) {
    document.dispatchEvent(
      new CustomEvent(CLOSE_ALL_EVENT, {detail: {except: entry.panel.id || null}})
    );
    entry.panel.classList.add('open');
    entry.panel.setAttribute('aria-hidden', 'false');
    entry.trigger.setAttribute('aria-expanded', 'true');
    positionEntry(entry);
    const autofocusTarget = entry.panel.querySelector('[data-dropdown-autofocus]');
    if (autofocusTarget instanceof HTMLElement) {
      autofocusTarget.focus();
    }
  }

  function toggleEntry(entry) {
    if (entry.panel.classList.contains('open')) {
      closeEntry(entry, true);
      return;
    }
    openEntry(entry);
  }

  entries.forEach((entry) => {
    closeEntry(entry);

    entry.trigger.addEventListener('click', () => {
      toggleEntry(entry);
    });

    entry.panel.addEventListener('click', (event) => {
      if (event.target.closest('a[href]')) {
        closeEntry(entry);
      }
    });
  });

  document.addEventListener(CLOSE_ALL_EVENT, (event) => {
    const exceptId = event.detail?.except;
    entries.forEach((entry) => {
      if (entry.panel.id !== exceptId) {
        closeEntry(entry);
      }
    });
  });

  document.addEventListener('click', (event) => {
    const clickedInsideDropdown = entries.some((entry) =>
      entry.container.contains(event.target)
    );
    if (!clickedInsideDropdown) {
      entries.forEach((entry) => closeEntry(entry));
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      const openEntryRef = entries.find((entry) => entry.panel.classList.contains('open'));
      if (!openEntryRef) return;
      closeEntry(openEntryRef, true);
      entries.forEach((entry) => {
        if (entry !== openEntryRef) closeEntry(entry);
      });
    }
  });

  window.addEventListener('resize', positionOpenEntries);
})();
