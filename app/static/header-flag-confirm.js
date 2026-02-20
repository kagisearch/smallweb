(() => {
  const flagForm = document.querySelector('form[action*="flag_content"]');
  if (!flagForm) return;

  flagForm.addEventListener('submit', (event) => {
    if (!confirm('Are you sure you want to flag this post?')) {
      event.preventDefault();
    }
  });
})();
