// Categories dropdown
(() => {
  const toggle = document.getElementById('catToggle');
  const dropdown = document.getElementById('catDropdown');
  const backdrop = document.getElementById('catBackdrop');
  if (!toggle || !dropdown) return;

  const allItems = [...dropdown.querySelectorAll('.cat-item')];
  let focusIndex = -1;

  function openDropdown() {
    dropdown.classList.add('open');
    backdrop.classList.add('open');
    toggle.classList.add('active');
    toggle.setAttribute('aria-expanded', 'true');
    focusIndex = -1;
  }

  function closeDropdown() {
    dropdown.classList.remove('open');
    backdrop.classList.remove('open');
    toggle.classList.remove('active');
    toggle.setAttribute('aria-expanded', 'false');
    toggle.focus();
  }

  toggle.addEventListener('click', () => {
    dropdown.classList.contains('open') ? closeDropdown() : openDropdown();
  });

  backdrop.addEventListener('click', closeDropdown);

  document.addEventListener('keydown', (e) => {
    const isOpen = dropdown.classList.contains('open');
    if (e.key === 'Escape' && isOpen) {
      closeDropdown();
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

  function updateFocus() {
    allItems.forEach((item, i) => {
      if (i === focusIndex) {
        item.style.background = 'rgba(52,152,219,0.3)';
        item.scrollIntoView({block: 'nearest'});
      } else if (!item.classList.contains('selected')) {
        item.style.background = '';
      }
    });
  }
})();
