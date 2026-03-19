(function () {
  var KEY = 'lastSearch';
  var chip = document.getElementById('last-search');
  var link = document.getElementById('last-search-link');
  var clearBtn = document.getElementById('last-search-clear');
  var form = document.getElementById('search-form');
  var input = document.getElementById('search-input');
  if (!chip || !link || !clearBtn || !form || !input) return;

  var currentQuery = input.value.trim();
  var saved = localStorage.getItem(KEY);

  // Save current search term
  if (currentQuery) {
    localStorage.setItem(KEY, currentQuery);
    saved = currentQuery;
  }

  // Show chip only when the search field is empty and there's a saved term
  if (!currentQuery && saved) {
    link.textContent = saved;
    link.href = form.action + '?search=' + encodeURIComponent(saved);
    chip.hidden = false;
  }

  clearBtn.addEventListener('click', function () {
    localStorage.removeItem(KEY);
    chip.hidden = true;
  });
})();
