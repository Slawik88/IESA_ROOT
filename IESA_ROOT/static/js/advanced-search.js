/**
 * TIER 9: ADVANCED SEARCH & FILTERS
 * Версия: 1.0
 * 
 * Функционал:
 * - Full-text search с автодополнением
 * - Faceted filters (категории, даты, теги)
 * - Real-time results
 * - Search history
 * - Saved searches
 * - Sort & view options
 */

(function() {
    'use strict';

    // ====================================================
    // 1. STATE MANAGEMENT
    // ====================================================

    let searchHistory = [];
    let savedSearches = [];
    let activeFilters = {};
    let searchTimeout = null;
    let currentQuery = '';
    let selectedSuggestionIndex = -1;

    // ====================================================
    // 2. SEARCH INTERFACE
    // ====================================================

    function initAdvancedSearch() {
        const searchContainer = document.querySelector('.advanced-search-container');
        if (!searchContainer) return;

        loadSearchHistory();
        loadSavedSearches();
        setupEventListeners();

        console.log('✓ Advanced Search (TIER 9) initialized');
    }

    function setupEventListeners() {
        // Main search input
        const searchInput = document.querySelector('.search-main-input');
        if (searchInput) {
            searchInput.addEventListener('input', handleSearchInput);
            searchInput.addEventListener('keydown', handleSearchKeydown);
            searchInput.addEventListener('focus', showSearchSuggestions);
        }

        // Clear search button
        const clearBtn = document.querySelector('.search-clear-btn');
        if (clearBtn) {
            clearBtn.addEventListener('click', clearSearch);
        }

        // Toggle filters
        const toggleBtn = document.querySelector('.search-toggle-filters');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', toggleFilters);
        }

        // Filter inputs
        document.addEventListener('change', handleFilterChange);

        // Clear filters
        const clearFiltersBtn = document.querySelector('.clear-filters-btn');
        if (clearFiltersBtn) {
            clearFiltersBtn.addEventListener('click', clearAllFilters);
        }

        // Save search
        const saveBtn = document.querySelector('.save-search-btn');
        if (saveBtn) {
            saveBtn.addEventListener('click', saveSearch);
        }

        // Sort controls
        const sortSelect = document.querySelector('.sort-select');
        if (sortSelect) {
            sortSelect.addEventListener('change', handleSortChange);
        }

        // View toggle
        document.querySelectorAll('.view-toggle-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.view-toggle-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const view = btn.dataset.view;
                changeView(view);
            });
        });

        // Close suggestions on outside click
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.search-main-input-wrapper')) {
                hideSearchSuggestions();
            }
        });
    }

    function handleSearchInput(e) {
        currentQuery = e.target.value.trim();
        
        clearTimeout(searchTimeout);
        
        if (currentQuery.length >= 2) {
            searchTimeout = setTimeout(() => {
                performSearch(currentQuery);
                showSearchSuggestions();
            }, 300);
        } else {
            hideSearchSuggestions();
        }
    }

    function handleSearchKeydown(e) {
        const suggestions = document.querySelector('.search-suggestions');
        if (!suggestions || !suggestions.classList.contains('show')) return;

        const items = suggestions.querySelectorAll('.suggestion-item');
        
        switch(e.key) {
            case 'ArrowDown':
                e.preventDefault();
                selectedSuggestionIndex = Math.min(selectedSuggestionIndex + 1, items.length - 1);
                updateSuggestionSelection(items);
                break;
            case 'ArrowUp':
                e.preventDefault();
                selectedSuggestionIndex = Math.max(selectedSuggestionIndex - 1, -1);
                updateSuggestionSelection(items);
                break;
            case 'Enter':
                e.preventDefault();
                if (selectedSuggestionIndex >= 0 && items[selectedSuggestionIndex]) {
                    items[selectedSuggestionIndex].click();
                } else {
                    submitSearch();
                }
                break;
            case 'Escape':
                hideSearchSuggestions();
                break;
        }
    }

    function updateSuggestionSelection(items) {
        items.forEach((item, index) => {
            item.classList.toggle('selected', index === selectedSuggestionIndex);
        });
    }

    function performSearch(query) {
        console.log('Searching for:', query);
        
        // Add to history
        addToSearchHistory(query);
        
        // Generate suggestions (would be from backend in real app)
        generateSuggestions(query);
        
        // Trigger search (would update results via HTMX in real app)
        const resultsContainer = document.querySelector('.search-results-container');
        if (resultsContainer) {
            // In real app, HTMX would handle this
            console.log('Updating results for:', query, activeFilters);
        }
    }

    function generateSuggestions(query) {
        const suggestions = document.querySelector('.search-suggestions');
        if (!suggestions) return;

        // Sample suggestions (would come from backend)
        const sampleSuggestions = {
            posts: [
                { title: 'Amazing kitesurfing experience', type: 'post', icon: 'fa-newspaper' },
                { title: 'Boxing training tips', type: 'post', icon: 'fa-newspaper' }
            ],
            users: [
                { title: 'John Doe', type: 'user', icon: 'fa-user', meta: 'Member since 2024' }
            ],
            events: [
                { title: 'Summer Camp 2025', type: 'event', icon: 'fa-calendar', meta: 'June 15, 2025' }
            ]
        };

        suggestions.innerHTML = '';

        // Add history section
        if (searchHistory.length > 0) {
            const historySection = createSuggestionSection('Recent Searches', searchHistory.slice(0, 3).map(h => ({
                title: h,
                type: 'history',
                icon: 'fa-clock-rotate-left'
            })));
            suggestions.appendChild(historySection);
        }

        // Add results sections
        Object.entries(sampleSuggestions).forEach(([type, items]) => {
            if (items.length > 0) {
                const section = createSuggestionSection(type.charAt(0).toUpperCase() + type.slice(1), items);
                suggestions.appendChild(section);
            }
        });
    }

    function createSuggestionSection(title, items) {
        const section = document.createElement('div');
        section.className = 'suggestion-section';

        const titleEl = document.createElement('div');
        titleEl.className = 'suggestion-section-title';
        titleEl.textContent = title;
        section.appendChild(titleEl);

        items.forEach(item => {
            const itemEl = document.createElement('div');
            itemEl.className = 'suggestion-item';
            itemEl.dataset.type = item.type;
            itemEl.dataset.value = item.title;

            const icon = document.createElement('div');
            icon.className = 'suggestion-icon';
            icon.innerHTML = `<i class="fas ${item.icon}"></i>`;

            const content = document.createElement('div');
            content.className = 'suggestion-content';

            const titleEl = document.createElement('div');
            titleEl.className = 'suggestion-title';
            titleEl.textContent = item.title;

            content.appendChild(titleEl);

            if (item.meta) {
                const metaEl = document.createElement('div');
                metaEl.className = 'suggestion-meta';
                metaEl.textContent = item.meta;
                content.appendChild(metaEl);
            }

            itemEl.appendChild(icon);
            itemEl.appendChild(content);

            itemEl.addEventListener('click', () => {
                if (item.type === 'history') {
                    document.querySelector('.search-main-input').value = item.title;
                    performSearch(item.title);
                } else {
                    console.log('Navigate to:', item.type, item.title);
                }
                hideSearchSuggestions();
            });

            section.appendChild(itemEl);
        });

        return section;
    }

    function showSearchSuggestions() {
        const suggestions = document.querySelector('.search-suggestions');
        if (suggestions && suggestions.children.length > 0) {
            suggestions.classList.add('show');
            selectedSuggestionIndex = -1;
        }
    }

    function hideSearchSuggestions() {
        const suggestions = document.querySelector('.search-suggestions');
        if (suggestions) {
            suggestions.classList.remove('show');
        }
    }

    function clearSearch() {
        const input = document.querySelector('.search-main-input');
        if (input) {
            input.value = '';
            input.focus();
        }
        currentQuery = '';
        hideSearchSuggestions();
    }

    function submitSearch() {
        if (!currentQuery) return;
        
        performSearch(currentQuery);
        hideSearchSuggestions();
        showToast('Search submitted!', 'info');
    }

    // ====================================================
    // 3. FILTERS
    // ====================================================

    function toggleFilters() {
        const container = document.querySelector('.filters-container');
        const btn = document.querySelector('.search-toggle-filters');
        
        if (container && btn) {
            container.classList.toggle('show');
            btn.classList.toggle('active');
        }
    }

    function handleFilterChange(e) {
        if (!e.target.matches('.filter-checkbox-item input, .filter-date-input, .filter-range-input, .filter-tag')) {
            return;
        }

        const filterType = e.target.dataset.filterType;
        const filterValue = e.target.value;

        if (e.target.type === 'checkbox') {
            if (e.target.checked) {
                addFilter(filterType, filterValue);
            } else {
                removeFilter(filterType, filterValue);
            }
        } else if (e.target.classList.contains('filter-tag')) {
            e.target.classList.toggle('active');
            if (e.target.classList.contains('active')) {
                addFilter(filterType, filterValue);
            } else {
                removeFilter(filterType, filterValue);
            }
        } else {
            addFilter(filterType, filterValue);
        }

        updateActiveFilters();
        performSearch(currentQuery);
    }

    function addFilter(type, value) {
        if (!activeFilters[type]) {
            activeFilters[type] = [];
        }
        if (!activeFilters[type].includes(value)) {
            activeFilters[type].push(value);
        }
    }

    function removeFilter(type, value) {
        if (activeFilters[type]) {
            activeFilters[type] = activeFilters[type].filter(v => v !== value);
            if (activeFilters[type].length === 0) {
                delete activeFilters[type];
            }
        }
    }

    function updateActiveFilters() {
        const container = document.querySelector('.active-filters');
        if (!container) return;

        container.innerHTML = '';

        Object.entries(activeFilters).forEach(([type, values]) => {
            values.forEach(value => {
                const chip = document.createElement('div');
                chip.className = 'active-filter-chip';
                chip.innerHTML = `
                    <span>${type}: ${value}</span>
                    <button class="active-filter-remove" data-type="${type}" data-value="${value}">
                        <i class="fas fa-times"></i>
                    </button>
                `;

                chip.querySelector('button').addEventListener('click', () => {
                    removeFilter(type, value);
                    updateActiveFilters();
                    performSearch(currentQuery);
                });

                container.appendChild(chip);
            });
        });
    }

    function clearAllFilters() {
        activeFilters = {};
        updateActiveFilters();
        
        // Reset UI
        document.querySelectorAll('.filter-checkbox-item input').forEach(cb => cb.checked = false);
        document.querySelectorAll('.filter-tag.active').forEach(tag => tag.classList.remove('active'));
        document.querySelectorAll('.filter-date-input').forEach(input => input.value = '');
        
        performSearch(currentQuery);
        showToast('Filters cleared', 'info');
    }

    // ====================================================
    // 4. SEARCH HISTORY
    // ====================================================

    function loadSearchHistory() {
        const stored = localStorage.getItem('searchHistory');
        if (stored) {
            try {
                searchHistory = JSON.parse(stored);
            } catch (e) {
                console.error('Failed to load search history:', e);
            }
        }
    }

    function addToSearchHistory(query) {
        if (!query || searchHistory.includes(query)) return;

        searchHistory.unshift(query);
        searchHistory = searchHistory.slice(0, 10); // Keep last 10

        localStorage.setItem('searchHistory', JSON.stringify(searchHistory));
    }

    function clearSearchHistory() {
        searchHistory = [];
        localStorage.removeItem('searchHistory');
        showToast('Search history cleared', 'info');
    }

    // ====================================================
    // 5. SAVED SEARCHES
    // ====================================================

    function loadSavedSearches() {
        const stored = localStorage.getItem('savedSearches');
        if (stored) {
            try {
                savedSearches = JSON.parse(stored);
            } catch (e) {
                console.error('Failed to load saved searches:', e);
            }
        }
    }

    function saveSearch() {
        if (!currentQuery) {
            showToast('Enter a search query first', 'warning');
            return;
        }

        const search = {
            id: Date.now(),
            query: currentQuery,
            filters: {...activeFilters},
            timestamp: new Date().toISOString()
        };

        savedSearches.push(search);
        localStorage.setItem('savedSearches', JSON.stringify(savedSearches));

        showToast('Search saved!', 'success');
    }

    // ====================================================
    // 6. SORT & VIEW
    // ====================================================

    function handleSortChange(e) {
        const sortBy = e.target.value;
        console.log('Sorting by:', sortBy);
        
        // Would trigger re-sort of results
        showToast(`Sorted by ${sortBy}`, 'info');
    }

    function changeView(view) {
        console.log('Changing view to:', view);
        
        const resultsContainer = document.querySelector('.search-results-container');
        if (resultsContainer) {
            resultsContainer.dataset.view = view;
            // Would re-render results in grid/list view
        }
    }

    // ====================================================
    // 7. UTILITY FUNCTIONS
    // ====================================================

    function showToast(message, type = 'info') {
        if (window.ToastNotifications && window.ToastNotifications.show) {
            window.ToastNotifications.show(message, type);
        } else {
            console.log(`[${type.toUpperCase()}] ${message}`);
        }
    }

    // ====================================================
    // 8. INITIALIZATION
    // ====================================================

    function init() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initAdvancedSearch);
        } else {
            initAdvancedSearch();
        }
    }

    // Export for global access
    window.AdvancedSearch = {
        init,
        performSearch,
        addFilter,
        removeFilter,
        clearAllFilters,
        saveSearch,
        searchHistory,
        savedSearches
    };

    // Auto-initialize
    init();

})();
