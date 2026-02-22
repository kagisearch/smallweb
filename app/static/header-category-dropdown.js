(() => {
  const CLOSE_ALL_EVENT = 'smallweb:close-all-dropdowns';
  const toggle = document.getElementById('catToggle');
  const dropdown = document.getElementById('catDropdown');
  const backdrop = document.getElementById('catBackdrop');
  const header = document.getElementById('header');
  if (!toggle || !dropdown || !backdrop) return;

  const allItems = [...dropdown.querySelectorAll('.cat-item')];
  let focusIndex = -1;

  function getDropdownTop() {
    if (!header) return 50;
    return Math.round(header.getBoundingClientRect().bottom);
  }

  function positionDropdown() {
    dropdown.style.top = `${getDropdownTop()}px`;

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
