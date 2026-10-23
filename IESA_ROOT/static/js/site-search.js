/* One search dialog and history shared by desktop, phone and tablet. */
(function () {
    'use strict';
    const modal = document.getElementById('siteSearchModal');
    const input = document.getElementById('global-community-search');
    const suggestions = document.getElementById('search-suggestions');
    const results = document.getElementById('community-search-results');
    if (!modal || !input || !suggestions || !results) return;
    const key = 'iesa_recent_searches';

    function recent() {
        try {
            const value = JSON.parse(localStorage.getItem(key) || '[]');
            return Array.isArray(value) ? value.filter(item => typeof item === 'string').slice(0, 5) : [];
        } catch { return []; }
    }
    function save() {
        const query = input.value.trim();
        if (!query) return;
        try { localStorage.setItem(key, JSON.stringify([query, ...recent().filter(item => item !== query)].slice(0, 5))); }
        catch { /* Search also works when storage is disabled. */ }
    }
    function renderRecent() {
        suggestions.replaceChildren();
        const queries = input.value.trim() ? [] : recent();
        suggestions.hidden = queries.length === 0;
        if (!queries.length) return;
        const label = document.createElement('p');
        label.className = 'small text-muted mb-1 mt-2';
        label.textContent = suggestions.dataset.recentLabel;
        suggestions.append(label);
        queries.forEach(query => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'search-history-item';
            button.textContent = query;
            button.addEventListener('click', () => {
                input.value = query;
                suggestions.hidden = true;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.focus();
            });
            suggestions.append(button);
        });
        const clear = document.createElement('button');
        clear.type = 'button';
        clear.className = 'search-history-item small text-muted';
        clear.textContent = suggestions.dataset.clearLabel;
        clear.addEventListener('click', () => {
            try { localStorage.removeItem(key); } catch { /* Optional history. */ }
            suggestions.hidden = true;
        });
        suggestions.append(clear);
    }
    modal.addEventListener('show.bs.modal', () => {
        const nav = document.getElementById('iesa-nav-collapse');
        if (nav?.classList.contains('show') && window.bootstrap) {
            bootstrap.Collapse.getOrCreateInstance(nav, { toggle: false }).hide();
        }
    });
    modal.addEventListener('shown.bs.modal', () => { input.focus(); renderRecent(); });
    input.addEventListener('input', renderRecent);
    input.addEventListener('keydown', event => { if (event.key === 'Enter') save(); });
    results.addEventListener('click', event => { if (event.target.closest('a')) save(); });
})();
