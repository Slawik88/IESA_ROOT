/**
 * LANGUAGE SELECTOR
 * Версия: 1.0
 * 
 * Простой переключатель языков для navbar
 */

(function() {
    'use strict';

    const LANGUAGES = {
        'en': { name: 'English', native: 'English', flag: '🇬🇧' },
        'ru': { name: 'Russian', native: 'Русский', flag: '🇷🇺' },
        'de': { name: 'German', native: 'Deutsch', flag: '🇩🇪' },
        'fr': { name: 'French', native: 'Français', flag: '🇫🇷' },
        'es': { name: 'Spanish', native: 'Español', flag: '🇪🇸' }
    };

    let currentLanguage = 'en';

    function initLanguageSelector() {
        // Check if language selector already exists
        if (document.querySelector('.language-selector')) return;

        // Get or set language from localStorage
        currentLanguage = localStorage.getItem('language') || 'en';

        // Create language selector
        const selector = createLanguageSelector();
        
        // Insert into navbar
        const navbarActions = document.querySelector('.navbar-collapse .d-flex.align-items-center');
        if (navbarActions) {
            const searchDropdown = navbarActions.querySelector('.dropdown');
            if (searchDropdown) {
                navbarActions.insertBefore(selector, searchDropdown);
            } else {
                navbarActions.insertBefore(selector, navbarActions.firstChild);
            }
        }

        setupEventListeners();

        console.log('✓ Language Selector initialized');
    }

    function createLanguageSelector() {
        const container = document.createElement('div');
        container.className = 'language-selector me-2';

        const toggle = document.createElement('button');
        toggle.className = 'language-toggle';
        toggle.innerHTML = `
            <span class="language-flag">${LANGUAGES[currentLanguage].flag}</span>
            <span class="language-code">${currentLanguage.toUpperCase()}</span>
            <i class="fas fa-chevron-down" style="font-size: 10px;"></i>
        `;

        const dropdown = document.createElement('div');
        dropdown.className = 'language-dropdown';

        Object.entries(LANGUAGES).forEach(([code, lang]) => {
            const option = document.createElement('div');
            option.className = `language-option ${code === currentLanguage ? 'active' : ''}`;
            option.dataset.lang = code;
            option.innerHTML = `
                <span class="language-flag">${lang.flag}</span>
                <div>
                    <div class="language-option-name">${lang.name}</div>
                    <div class="language-option-native">${lang.native}</div>
                </div>
            `;
            dropdown.appendChild(option);
        });

        container.appendChild(toggle);
        container.appendChild(dropdown);

        return container;
    }

    function setupEventListeners() {
        // Toggle dropdown
        document.addEventListener('click', (e) => {
            const toggle = e.target.closest('.language-toggle');
            if (toggle) {
                e.stopPropagation();
                const dropdown = toggle.nextElementSibling;
                dropdown.classList.toggle('show');
                return;
            }

            // Select language
            const option = e.target.closest('.language-option');
            if (option) {
                const lang = option.dataset.lang;
                changeLanguage(lang);
                return;
            }

            // Close dropdown when clicking outside
            document.querySelectorAll('.language-dropdown.show').forEach(dropdown => {
                dropdown.classList.remove('show');
            });
        });
    }

    function changeLanguage(lang) {
        if (!LANGUAGES[lang]) return;

        currentLanguage = lang;
        localStorage.setItem('language', lang);

        // Update toggle
        const toggle = document.querySelector('.language-toggle');
        if (toggle) {
            toggle.innerHTML = `
                <span class="language-flag">${LANGUAGES[lang].flag}</span>
                <span class="language-code">${lang.toUpperCase()}</span>
                <i class="fas fa-chevron-down" style="font-size: 10px;"></i>
            `;
        }

        // Update active option
        document.querySelectorAll('.language-option').forEach(option => {
            option.classList.toggle('active', option.dataset.lang === lang);
        });

        // Close dropdown
        document.querySelector('.language-dropdown')?.classList.remove('show');

        // Show toast
        if (window.ToastNotifications && window.ToastNotifications.show) {
            window.ToastNotifications.show(`Language changed to ${LANGUAGES[lang].name}`, 'info');
        }

        // In real app, would reload page or update content
        console.log('Language changed to:', lang);
    }

    function init() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initLanguageSelector);
        } else {
            initLanguageSelector();
        }
    }

    window.LanguageSelector = {
        init,
        changeLanguage,
        getCurrentLanguage: () => currentLanguage,
        getLanguages: () => LANGUAGES
    };

    init();

})();
