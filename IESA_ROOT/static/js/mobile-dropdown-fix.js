/**
 * Mobile Dropdown Menu Fix
 * Версия: 1.0
 * 
 * Фиксит проблему с дропдаун меню на мобильных устройствах.
 * Проблема: при клике на "Community" меню закрывается вместо открытия.
 * Решение: предотвращаем закрытие navbar при клике на dropdown toggle.
 */

document.addEventListener('DOMContentLoaded', function() {
    // Находим все dropdown toggles в navbar
    const dropdownToggles = document.querySelectorAll('.navbar .dropdown-toggle');
    
    dropdownToggles.forEach(toggle => {
        toggle.addEventListener('click', function(e) {
            // На мобильных (когда navbar collapsed)
            const navbar = document.querySelector('.navbar-collapse');
            const isCollapsed = !navbar.classList.contains('show');
            
            if (!isCollapsed) {
                // Navbar открыт (mobile view) - предотвращаем его закрытие
                e.stopPropagation();
                
                // Получаем dropdown menu
                const dropdown = this.nextElementSibling;
                if (dropdown && dropdown.classList.contains('dropdown-menu')) {
                    // Закрываем все другие dropdown меню
                    document.querySelectorAll('.navbar .dropdown-menu.show').forEach(menu => {
                        if (menu !== dropdown) {
                            menu.classList.remove('show');
                        }
                    });
                    
                    // Переключаем текущий dropdown
                    dropdown.classList.toggle('show');
                    this.setAttribute('aria-expanded', dropdown.classList.contains('show'));
                }
            }
        });
    });
    
    // Закрываем dropdown при клике на dropdown-item
    const dropdownItems = document.querySelectorAll('.navbar .dropdown-item');
    dropdownItems.forEach(item => {
        item.addEventListener('click', function() {
            // Закрываем dropdown menu
            const dropdownMenu = this.closest('.dropdown-menu');
            if (dropdownMenu) {
                dropdownMenu.classList.remove('show');
                
                // Обновляем aria-expanded на toggle
                const toggle = dropdownMenu.previousElementSibling;
                if (toggle) {
                    toggle.setAttribute('aria-expanded', 'false');
                }
            }
        });
    });
    
    // Закрываем dropdown при клике вне его
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.navbar .dropdown')) {
            document.querySelectorAll('.navbar .dropdown-menu.show').forEach(menu => {
                menu.classList.remove('show');
                const toggle = menu.previousElementSibling;
                if (toggle) {
                    toggle.setAttribute('aria-expanded', 'false');
                }
            });
        }
    });
    
    // Фикс для Bootstrap dropdown на мобильных
    // Предотвращаем конфликт между Bootstrap dropdown и navbar collapse
    const navbarToggler = document.querySelector('.navbar-toggler');
    if (navbarToggler) {
        navbarToggler.addEventListener('click', function() {
            // Закрываем все открытые dropdown меню при закрытии navbar
            setTimeout(() => {
                const navbar = document.querySelector('.navbar-collapse');
                if (!navbar.classList.contains('show')) {
                    document.querySelectorAll('.navbar .dropdown-menu.show').forEach(menu => {
                        menu.classList.remove('show');
                        const toggle = menu.previousElementSibling;
                        if (toggle) {
                            toggle.setAttribute('aria-expanded', 'false');
                        }
                    });
                }
            }, 10);
        });
    }
});

// Альтернативный метод: используем Bootstrap events
document.addEventListener('DOMContentLoaded', function() {
    const navbarCollapse = document.querySelector('.navbar-collapse');
    
    if (navbarCollapse) {
        // Когда navbar закрывается, закрываем все dropdown
        navbarCollapse.addEventListener('hide.bs.collapse', function() {
            document.querySelectorAll('.navbar .dropdown-menu.show').forEach(menu => {
                menu.classList.remove('show');
                const toggle = menu.previousElementSibling;
                if (toggle) {
                    toggle.setAttribute('aria-expanded', 'false');
                }
            });
        });
    }
});
