/**
 * Mobile Navbar Dropdown Fix
 * Решает проблему: При клике на Community dropdown на мобильном телефоне весь header закрывается
 * Это происходит потому что Bootstrap dropdown toggle закрывает navbar-collapse
 */

(function() {
    'use strict';

    // Инициализация при загрузке документа
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initMobileNavbarFix);
    } else {
        initMobileNavbarFix();
    }

    function initMobileNavbarFix() {
        console.log('📱 Mobile Navbar Fix initialized');

        // Получаем элементы навбара
        const navbar = document.querySelector('.navbar-collapse');
        const toggler = document.querySelector('.navbar-toggler');
        const dropdownToggles = document.querySelectorAll('.dropdown-toggle');

        if (!navbar || !toggler) return;

        // Для каждого dropdown toggle
        dropdownToggles.forEach(toggle => {
            toggle.addEventListener('click', function(e) {
                // На мобильном устройстве (когда navbar-toggler видна)
                if (toggler.offsetParent !== null) {
                    console.log('📱 Dropdown clicked on mobile');
                    // НЕ закрываем navbar-collapse
                    e.preventDefault();
                    e.stopPropagation();

                    // Переключаем dropdown
                    const dropdown = this.nextElementSibling;
                    if (dropdown && dropdown.classList.contains('dropdown-menu')) {
                        dropdown.classList.toggle('show');
                    }
                    
                    // Или используем Bootstrap Dropdown API
                    if (typeof bootstrap !== 'undefined' && bootstrap.Dropdown) {
                        const dropdownInstance = bootstrap.Dropdown.getInstance(this) || 
                                               new bootstrap.Dropdown(this);
                    }
                }
            });

            // Предотвращаем закрытие при клике внутри dropdown
            const dropdown = toggle.nextElementSibling;
            if (dropdown && dropdown.classList.contains('dropdown-menu')) {
                dropdown.addEventListener('click', function(e) {
                    e.stopPropagation();
                    console.log('📱 Click inside dropdown menu prevented from closing navbar');
                });
            }
        });

        // Когда navbar-collapse открывается/закрывается
        navbar.addEventListener('show.bs.collapse', function() {
            console.log('📱 Navbar opening...');
        });

        navbar.addEventListener('hide.bs.collapse', function() {
            console.log('📱 Navbar hiding...');
            // Закрываем все dropdown меню когда закрывается navbar
            document.querySelectorAll('.dropdown-menu.show').forEach(menu => {
                menu.classList.remove('show');
            });
        });

        // Обработчик для обычных ссылок в навбаре
        // Они должны закрывать navbar, но не dropdown
        const navLinks = document.querySelectorAll('.navbar-nav .nav-link:not(.dropdown-toggle)');
        navLinks.forEach(link => {
            link.addEventListener('click', function() {
                // На мобильном - закрываем navbar после клика
                if (toggler.offsetParent !== null && navbar.classList.contains('show')) {
                    const bsCollapse = new bootstrap.Collapse(navbar, {toggle: false});
                    bsCollapse.hide();
                    console.log('📱 Navbar closed after nav link click');
                }
            });
        });

        // Специальный обработчик для ссылок внутри dropdown
        const dropdownItems = document.querySelectorAll('.dropdown-menu .dropdown-item');
        dropdownItems.forEach(item => {
            item.addEventListener('click', function(e) {
                // На мобильном - закрываем navbar после клика
                if (toggler.offsetParent !== null && navbar.classList.contains('show')) {
                    setTimeout(() => {
                        const bsCollapse = new bootstrap.Collapse(navbar, {toggle: false});
                        bsCollapse.hide();
                        console.log('📱 Navbar closed after dropdown item click');
                    }, 100);
                }
            });
        });

        // Мониторим для новых dropdown элементов
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.type === 'childList') {
                    mutation.addedNodes.forEach(function(node) {
                        if (node.nodeType === 1 && node.classList) {
                            if (node.classList.contains('dropdown-toggle')) {
                                console.log('🆕 New dropdown detected');
                                // Переиницализируем обработчики
                                node.addEventListener('click', function(e) {
                                    if (toggler.offsetParent !== null) {
                                        e.preventDefault();
                                        e.stopPropagation();
                                    }
                                });
                            }
                        }
                    });
                }
            });
        });

        observer.observe(document.querySelector('.navbar-nav'), {
            childList: true,
            subtree: true
        });

        console.log('✅ Mobile navbar dropdown fix applied');
    }

    // Экспортируем если нужны в других местах
    window.MobileNavbarFix = {
        closeNavbar: function() {
            const navbar = document.querySelector('.navbar-collapse');
            if (navbar && navbar.classList.contains('show')) {
                const bsCollapse = new bootstrap.Collapse(navbar, {toggle: false});
                bsCollapse.hide();
            }
        }
    };
})();
