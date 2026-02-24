(() => {
  const dialogue = document.getElementById('shortcuts-dialogue');
  const backdrop = document.getElementById('shortcuts-backdrop');
  const closeBtn = document.getElementById('shortcuts-close');
  const table    = document.getElementById('shortcuts-table');
  if (!dialogue || !backdrop || !table) return;

  function openShortcuts() {
    dialogue.classList.add('open');
    backdrop.classList.add('open');
  }

  function closeShortcuts() {
    dialogue.classList.remove('open');
    backdrop.classList.remove('open');
  }

  const SHORTCUTS = [
    { key: 'n', description: 'Next post', action: () => document.querySelector('.next-button')?.click() },
    { key: '?', description: 'Show keyboard shortcuts', action: () => dialogue.classList.contains('open') ? closeShortcuts() : openShortcuts() },
  ];

  for (const s of SHORTCUTS) {
    const row = table.insertRow();
    row.insertCell().innerHTML = '<kbd>' + s.key + '</kbd>';
    row.insertCell().textContent = s.description;
  }

  function isTyping() {
    const el = document.activeElement;
    return el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable);
  }

  backdrop.addEventListener('click', closeShortcuts);
  closeBtn.addEventListener('click', closeShortcuts);

  document.addEventListener('keydown', (e) => {
    if (isTyping()) return;

    if (e.key === 'Escape' && dialogue.classList.contains('open')) {
      closeShortcuts();
      return;
    }

    const match = SHORTCUTS.find(s => s.key === e.key);
    if (match && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault();
      match.action();
    }
  });
})();
