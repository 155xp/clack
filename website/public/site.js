(() => {
  const dialog = document.querySelector('#search-dialog');
  const searchInput = document.querySelector('#search-input');
  const results = document.querySelector('#search-results');
  let searchIndex;
  let returnFocus;

  function message(text) {
    const paragraph = document.createElement('p');
    paragraph.className = 'search-message';
    paragraph.textContent = text;
    results?.replaceChildren(paragraph);
  }

  function renderSearch() {
    if (!results || !searchInput || !searchIndex) return;
    const query = searchInput.value.trim().toLowerCase();
    const tokens = query.split(/\s+/).filter(Boolean);
    const ranked = searchIndex.map((entry) => {
      const title = entry.title.toLowerCase();
      const text = entry.text.toLowerCase();
      const matches = tokens.every((token) => title.includes(token) || text.includes(token));
      const score = tokens.reduce((total, token) => total + (title.includes(token) ? 8 : 0) + (text.includes(token) ? 1 : 0), 0);
      return { entry, score, matches };
    }).filter(({ matches }) => matches)
      .sort((a, b) => b.score - a.score)
      .slice(0, 8);
    results.replaceChildren();
    if (!ranked.length) return message('No pages found. Try a function name or topic.');
    if (!tokens.length) {
      const hint = document.createElement('p');
      hint.className = 'search-message';
      hint.textContent = 'Search the handbook';
      results.append(hint);
    }
    for (const { entry } of ranked) {
      const link = document.createElement('a');
      link.className = 'search-result';
      link.href = entry.url;
      const title = document.createElement('strong');
      title.textContent = entry.title;
      const excerpt = document.createElement('span');
      const position = tokens.length ? Math.max(0, entry.text.toLowerCase().indexOf(tokens[0]) - 50) : 0;
      excerpt.textContent = `${position ? '…' : ''}${entry.text.slice(position, position + 150).trim()}${entry.text.length > position + 150 ? '…' : ''}`;
      link.append(title, excerpt);
      results.append(link);
    }
  }

  async function openSearch() {
    if (!dialog || !searchInput || dialog.open) return;
    returnFocus = document.activeElement;
    dialog.showModal();
    searchInput.focus();
    if (!searchIndex) {
      message('Loading the handbook…');
      try {
        const response = await fetch('/search-index.json');
        if (!response.ok) throw new Error('Search index unavailable');
        const entries = await response.json();
        searchIndex = Array.isArray(entries) ? entries : entries.pages;
        if (!Array.isArray(searchIndex)) throw new Error('Search index invalid');
      } catch {
        message('Search is unavailable. You can still browse the documentation.');
        return;
      }
    }
    renderSearch();
  }

  document.querySelectorAll('[data-search-open]').forEach((button) => button.addEventListener('click', openSearch));
  document.querySelectorAll('[data-search-close]').forEach((button) => button.addEventListener('click', () => dialog?.close()));
  searchInput?.addEventListener('input', renderSearch);
  searchInput?.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      results?.querySelector('a')?.focus();
    }
  });
  dialog?.addEventListener('close', () => returnFocus?.focus());
  dialog?.addEventListener('click', (event) => {
    if (event.target !== dialog) return;
    const rect = dialog.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
  });

  const menuButton = document.querySelector('[data-menu-toggle]');
  const mobileNavigation = document.querySelector('#mobile-navigation');
  function closeMenu() {
    if (mobileNavigation) mobileNavigation.hidden = true;
    menuButton?.setAttribute('aria-expanded', 'false');
  }
  menuButton?.addEventListener('click', () => {
    if (!mobileNavigation) return;
    const expanded = menuButton.getAttribute('aria-expanded') === 'true';
    mobileNavigation.hidden = expanded;
    menuButton.setAttribute('aria-expanded', String(!expanded));
  });
  mobileNavigation?.querySelectorAll('a').forEach((link) => link.addEventListener('click', closeMenu));
  document.addEventListener('keydown', (event) => {
    const editing = event.target instanceof Element && event.target.closest('input, textarea, select, [contenteditable="true"]');
    if (((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') || (event.key === '/' && !editing)) {
      event.preventDefault();
      openSearch();
    }
    if (event.key === 'Escape') closeMenu();
  });

  const copyTimers = new WeakMap();
  document.querySelectorAll('[data-copy]').forEach((button) => {
    const original = button.innerHTML;
    button.addEventListener('click', async () => {
      const text = button.dataset.copy || button.closest('.code-block')?.querySelector('code')?.textContent;
      if (!text) return;
      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(text);
        } else {
          const temporary = document.createElement('textarea');
          temporary.value = text;
          temporary.setAttribute('aria-hidden', 'true');
          temporary.style.position = 'fixed';
          temporary.style.opacity = '0';
          document.body.append(temporary);
          temporary.select();
          const copied = document.execCommand('copy');
          temporary.remove();
          button.focus();
          if (!copied) throw new Error('Copy unavailable');
        }
        button.textContent = 'Copied';
      } catch {
        button.textContent = 'Select and copy';
      }
      clearTimeout(copyTimers.get(button));
      copyTimers.set(button, setTimeout(() => { button.innerHTML = original; }, 1600));
    });
  });

  const tabs = [...document.querySelectorAll('[data-code-tab]')];
  function selectTab(tab, focus = false) {
    tabs.forEach((button) => {
      const selected = button === tab;
      button.setAttribute('aria-selected', String(selected));
      button.tabIndex = selected ? 0 : -1;
    });
    document.querySelectorAll('[data-code-panel]').forEach((panel) => {
      panel.hidden = panel.id !== tab.getAttribute('aria-controls');
    });
    if (focus) tab.focus();
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => selectTab(tab));
    tab.addEventListener('keydown', (event) => {
      const positions = { ArrowRight: (index + 1) % tabs.length, ArrowLeft: (index - 1 + tabs.length) % tabs.length, Home: 0, End: tabs.length - 1 };
      if (Object.hasOwn(positions, event.key)) {
        event.preventDefault();
        selectTab(tabs[positions[event.key]], true);
      }
    });
  });

  if ('IntersectionObserver' in window) {
    const links = [...document.querySelectorAll('.toc a[href^="#"]')];
    const byId = new Map(links.map((link) => [decodeURIComponent(link.hash.slice(1)), link]));
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.find((entry) => entry.isIntersecting);
      if (!visible) return;
      links.forEach((link) => link.removeAttribute('aria-current'));
      byId.get(visible.target.id)?.setAttribute('aria-current', 'location');
    }, { rootMargin: '-10% 0px -75% 0px' });
    byId.forEach((_, id) => {
      const heading = document.getElementById(id);
      if (heading) observer.observe(heading);
    });
  }
})();
