/**
 * Advanced Filter System
 * Powerful filtering, sorting, and search with live updates
 * Works with HTMX for seamless UX
 */

(function() {
    'use strict';

    const AdvancedFilters = {
        filters: {},
        sorts: {},
        currentPage: 1,
        debounceTimer: null,
        debounceDelay: 400,
        container: null,

        /**
         * Initialize filter system
         */
        init() {
            this.container = document.querySelector('[data-filters-container]');
            if (!this.container) return;

            // Get all filter inputs
            const filterInputs = document.querySelectorAll('[data-filter]');
            const sortInputs = document.querySelectorAll('[data-sort]');
            const searchInputs = document.querySelectorAll('[data-search]');

            filterInputs.forEach(input => {
                input.addEventListener('change', this.handleFilterChange.bind(this));
            });

            sortInputs.forEach(input => {
                input.addEventListener('change', this.handleSortChange.bind(this));
            });

            searchInputs.forEach(input => {
                input.addEventListener('input', this.handleSearchInput.bind(this));
            });

            // Reset filters button
            const resetBtn = document.querySelector('[data-reset-filters]');
            if (resetBtn) {
                resetBtn.addEventListener('click', this.resetFilters.bind(this));
            }

            // Load initial filters from URL
            this.loadFiltersFromURL();
        },

        /**
         * Handle filter change
         */
        handleFilterChange(event) {
            const filterName = event.target.dataset.filter;
            const filterValue = event.target.value;
            const filterType = event.target.dataset.filterType || 'select';

            if (filterType === 'checkbox') {
                // Handle checkbox filters (multiple values)
                if (!this.filters[filterName]) {
                    this.filters[filterName] = [];
                }
                
                if (event.target.checked) {
                    this.filters[filterName].push(filterValue);
                } else {
                    this.filters[filterName] = this.filters[filterName].filter(v => v !== filterValue);
                }
            } else if (filterType === 'range') {
                // Handle range filters
                const rangeEnd = document.querySelector(`[data-filter="${filterName}"][data-filter-type="range-end"]`);
                this.filters[filterName] = {
                    min: parseFloat(event.target.value),
                    max: rangeEnd ? parseFloat(rangeEnd.value) : Infinity
                };
            } else {
                // Select filter
                if (filterValue === '') {
                    delete this.filters[filterName];
                } else {
                    this.filters[filterName] = filterValue;
                }
            }

            this.currentPage = 1;
            this.applyFilters();
        },

        /**
         * Handle sort change
         */
        handleSortChange(event) {
            const sortName = event.target.dataset.sort;
            const sortValue = event.target.value;
            const sortDirection = event.target.dataset.sortDirection || 'asc';

            if (sortValue === '') {
                delete this.sorts[sortName];
            } else {
                this.sorts = {
                    [sortName]: sortValue,
                    direction: sortDirection
                };
            }

            this.currentPage = 1;
            this.applyFilters();
        },

        /**
         * Handle search input with debounce
         */
        handleSearchInput(event) {
            clearTimeout(this.debounceTimer);
            
            const searchQuery = event.target.value.trim();
            const searchField = event.target.dataset.search;

            if (searchQuery === '') {
                delete this.filters[searchField];
            } else {
                this.filters[searchField] = searchQuery;
            }

            this.debounceTimer = setTimeout(() => {
                this.currentPage = 1;
                this.applyFilters();
            }, this.debounceDelay);
        },

        /**
         * Apply filters and update results
         */
        applyFilters() {
            const url = this.buildFilterURL();
            
            // Show loading state
            this.showLoadingState();

            // Use HTMX to load filtered results
            const target = document.querySelector('[data-filter-results]') || this.container;
            
            htmx.ajax('GET', url, {
                target,
                swap: 'innerHTML',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            // Update URL without page reload
            window.history.pushState({}, '', url);
        },

        /**
         * Build filter URL with parameters
         */
        buildFilterURL() {
            const params = new URLSearchParams();

            // Add filters
            Object.entries(this.filters).forEach(([key, value]) => {
                if (Array.isArray(value)) {
                    value.forEach(v => params.append(key, v));
                } else if (typeof value === 'object' && value !== null) {
                    // Range filter
                    params.append(key + '_min', value.min);
                    params.append(key + '_max', value.max);
                } else {
                    params.append(key, value);
                }
            });

            // Add sorts
            Object.entries(this.sorts).forEach(([key, value]) => {
                if (key !== 'direction') {
                    params.append('sort', value);
                    if (this.sorts.direction) {
                        params.append('direction', this.sorts.direction);
                    }
                }
            });

            // Add page
            params.append('page', this.currentPage);

            return `${window.location.pathname}?${params.toString()}`;
        },

        /**
         * Load filters from URL parameters
         */
        loadFiltersFromURL() {
            const params = new URLSearchParams(window.location.search);

            // Load filter values
            params.forEach((value, key) => {
                if (key !== 'page' && key !== 'sort' && key !== 'direction') {
                    const filterEl = document.querySelector(`[data-filter="${key}"]`);
                    if (filterEl) {
                        if (filterEl.type === 'checkbox') {
                            filterEl.checked = filterEl.value === value;
                        } else {
                            filterEl.value = value;
                        }
                    }
                }
            });

            // Load sort value
            const sort = params.get('sort');
            if (sort) {
                const sortEl = document.querySelector(`[data-sort][value="${sort}"]`);
                if (sortEl) {
                    sortEl.parentElement.querySelector('[data-sort]').value = sort;
                }
            }
        },

        /**
         * Reset all filters
         */
        resetFilters() {
            this.filters = {};
            this.sorts = {};
            this.currentPage = 1;

            // Reset all inputs
            document.querySelectorAll('[data-filter], [data-sort], [data-search]').forEach(input => {
                if (input.type === 'checkbox') {
                    input.checked = false;
                } else {
                    input.value = '';
                }
            });

            // Apply empty filters
            this.applyFilters();
        },

        /**
         * Show loading state
         */
        showLoadingState() {
            const resultsContainer = document.querySelector('[data-filter-results]');
            if (resultsContainer) {
                resultsContainer.style.opacity = '0.6';
                resultsContainer.style.pointerEvents = 'none';
            }
        },

        /**
         * Hide loading state
         */
        hideLoadingState() {
            const resultsContainer = document.querySelector('[data-filter-results]');
            if (resultsContainer) {
                resultsContainer.style.opacity = '1';
                resultsContainer.style.pointerEvents = 'auto';
            }
        },

        /**
         * Get current filters
         */
        getFilters() {
            return { ...this.filters };
        },

        /**
         * Set filter programmatically
         */
        setFilter(filterName, filterValue) {
            this.filters[filterName] = filterValue;
            this.currentPage = 1;
            this.applyFilters();
        }
    };

    /**
     * Filter Panel Toggle
     * Show/hide filter panel on mobile
     */
    const FilterPanel = {
        init() {
            const toggleBtn = document.querySelector('[data-toggle-filters]');
            const panel = document.querySelector('[data-filter-panel]');

            if (!toggleBtn || !panel) return;

            toggleBtn.addEventListener('click', () => {
                panel.classList.toggle('show');
                document.body.classList.toggle('filter-panel-open');
            });

            // Close on outside click
            document.addEventListener('click', (e) => {
                if (!panel.contains(e.target) && !toggleBtn.contains(e.target)) {
                    panel.classList.remove('show');
                    document.body.classList.remove('filter-panel-open');
                }
            });
        }
    };

    /**
     * Filter Tags Display
     * Show active filters as removable tags
     */
    const FilterTags = {
        container: null,

        init() {
            this.container = document.querySelector('[data-filter-tags]');
            if (!this.container) return;

            document.addEventListener('htmx:afterSwap', this.updateTags.bind(this));
        },

        updateTags() {
            const filters = AdvancedFilters.getFilters();
            this.container.innerHTML = '';

            Object.entries(filters).forEach(([key, value]) => {
                const tag = document.createElement('span');
                tag.className = 'filter-tag badge bg-primary';
                tag.innerHTML = `
                    ${key}: ${Array.isArray(value) ? value.join(', ') : value}
                    <button type="button" class="btn-close btn-close-white ms-2" data-remove-filter="${key}"></button>
                `;

                tag.querySelector('[data-remove-filter]').addEventListener('click', () => {
                    delete filters[key];
                    AdvancedFilters.setFilter(key, null);
                });

                this.container.appendChild(tag);
            });
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            AdvancedFilters.init();
            FilterPanel.init();
            FilterTags.init();
        });
    } else {
        AdvancedFilters.init();
        FilterPanel.init();
        FilterTags.init();
    }

    // Export for use in other scripts
    window.AdvancedFilters = AdvancedFilters;
})();
