/**
 * Modal Initialization & Fix Script
 * 
 * Проблема: Модальные окна не открываются/закрываются корректно
 * Решение: Принудительная инициализация через Bootstrap.Modal API
 * 
 * Версия: 2.0
 * Дата: 19 января 2026
 */

(function() {
    'use strict';
    
    const DEBUG = true;
    
    function log(...args) {
        if (DEBUG) console.log('[Modal Init]', ...args);
    }
    
    function error(...args) {
        console.error('[Modal Init ERROR]', ...args);
    }
    
    /**
     * Инициализация всех модалей на странице
     */
    function initializeAllModals() {
        log('🔧 Инициализация модалей...');
        
        // Проверяем наличие Bootstrap
        if (typeof bootstrap === 'undefined') {
            error('❌ Bootstrap не загружен! Modal инициализация невозможна.');
            return;
        }
        
        log('✅ Bootstrap загружен:', bootstrap.Modal ? 'Modal' : 'NO Modal');
        
        // Получаем все модали на странице
        const modals = document.querySelectorAll('.modal');
        log(`📊 Найдено модалей: ${modals.length}`);
        
        modals.forEach((modalElement, index) => {
            const modalId = modalElement.id || `modal-${index}`;
            log(`  ${index + 1}. Инициализация: #${modalId}`);
            
            try {
                // Проверяем, инициализирована ли уже
                const existingInstance = bootstrap.Modal.getInstance(modalElement);
                if (!existingInstance) {
                    // Инициализируем modal через Bootstrap API
                    new bootstrap.Modal(modalElement, {
                        backdrop: true,      // Позволяет закрывать по клику на backdrop
                        keyboard: true,      // Позволяет закрывать по ESC
                        focus: true          // Фокусируем modal при открытии
                    });
                    log(`     ✅ Инициализирована новая modal`);
                } else {
                    log(`     ✓ Уже инициализирована`);
                }
            } catch (e) {
                error(`     ❌ Ошибка при инициализации #${modalId}:`, e);
            }
        });
    }
    
    /**
     * Инициализация кнопок для открытия модалей
     */
    function initializeModalButtons() {
        log('🔘 Инициализация кнопок модалей...');
        
        const modalButtons = document.querySelectorAll('[data-bs-toggle="modal"]');
        log(`📊 Найдено кнопок: ${modalButtons.length}`);
        
        modalButtons.forEach((button, index) => {
            const targetId = button.getAttribute('data-bs-target');
            log(`  ${index + 1}. Кнопка → ${targetId}`);
            
            // Убеждаемся, что кнопка может быть кликнута
            button.style.pointerEvents = 'auto';
            
            // Добавляем обработчик клика с явной инициализацией
            button.addEventListener('click', function(e) {
                const targetSelector = this.getAttribute('data-bs-target');
                if (!targetSelector) {
                    error('❌ Кнопка без data-bs-target:', this);
                    return;
                }
                
                const modalElement = document.querySelector(targetSelector);
                if (!modalElement) {
                    error(`❌ Modal не найдена: ${targetSelector}`);
                    return;
                }
                
                try {
                    // Получаем или создаём Modal экземпляр
                    let modalInstance = bootstrap.Modal.getInstance(modalElement);
                    if (!modalInstance) {
                        modalInstance = new bootstrap.Modal(modalElement, {
                            backdrop: true,
                            keyboard: true,
                            focus: true
                        });
                    }
                    
                    // Показываем modal
                    modalInstance.show();
                    log(`✅ Открыта modal: ${targetSelector}`);
                    
                } catch (e) {
                    error(`❌ Ошибка при открытии ${targetSelector}:`, e);
                }
            }, false);
        });
    }
    
    /**
     * Исправляем backdrop клики
     */
    function fixBackdropClicks() {
        log('🖱️ Исправление backdrop кликов...');
        
        const backdrops = document.querySelectorAll('.modal-backdrop');
        log(`📊 Найдено backdrop элементов: ${backdrops.length}`);
        
        backdrops.forEach(backdrop => {
            backdrop.style.pointerEvents = 'auto';
            backdrop.style.cursor = 'pointer';
            
            backdrop.addEventListener('click', function(e) {
                if (e.target === this) {
                    log('🖱️ Backdrop клик - закрываем modal');
                    
                    // Находим open modal
                    const openModal = document.querySelector('.modal.show');
                    if (openModal) {
                        const instance = bootstrap.Modal.getInstance(openModal);
                        if (instance) {
                            instance.hide();
                        }
                    }
                }
            });
        });
    }
    
    /**
     * Исправляем close кнопки
     */
    function fixCloseButtons() {
        log('❌ Инициализация close кнопок...');
        
        const closeButtons = document.querySelectorAll('[data-bs-dismiss="modal"]');
        log(`📊 Найдено close кнопок: ${closeButtons.length}`);
        
        closeButtons.forEach((button, index) => {
            button.style.pointerEvents = 'auto';
            button.style.cursor = 'pointer';
            
            button.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                log(`❌ Close кнопка #${index + 1} - закрываем modal`);
                
                // Находим ближайший modal
                const modal = this.closest('.modal');
                if (modal) {
                    const instance = bootstrap.Modal.getInstance(modal);
                    if (instance) {
                        instance.hide();
                    }
                }
            }, false);
        });
    }
    
    /**
     * Добавляем обработчик клавиши ESC
     */
    function fixEscapeKey() {
        log('⌨️ Инициализация ESC key...');
        
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' || e.keyCode === 27) {
                const openModal = document.querySelector('.modal.show');
                if (openModal) {
                    const instance = bootstrap.Modal.getInstance(openModal);
                    if (instance) {
                        instance.hide();
                        log('⌨️ ESC нажата - закрыта modal');
                    }
                }
            }
        }, false);
    }
    
    /**
     * Исправляем CSS issues
     */
    function fixCSSIssues() {
        log('🎨 Исправление CSS проблем...');
        
        // Гарантируем правильный pointer-events на модальных окнах
        const style = document.createElement('style');
        style.textContent = `
            /* CRITICAL MODAL FIXES */
            .modal {
                pointer-events: auto !important;
            }
            .modal.show {
                pointer-events: auto !important;
                display: flex !important;
            }
            .modal-backdrop {
                pointer-events: auto !important;
            }
            .modal-backdrop.show {
                pointer-events: auto !important;
            }
            .modal-content {
                pointer-events: auto !important;
            }
            .modal-header,
            .modal-body,
            .modal-footer {
                pointer-events: auto !important;
            }
            .btn-close {
                pointer-events: auto !important;
                cursor: pointer !important;
            }
            [data-bs-toggle="modal"] {
                pointer-events: auto !important;
                cursor: pointer !important;
            }
            [data-bs-dismiss="modal"] {
                pointer-events: auto !important;
                cursor: pointer !important;
            }
            /* Предотвращаем скрытие элементов */
            .modal.fade {
                transition: opacity 0.3s ease-in-out;
            }
        `;
        document.head.appendChild(style);
        log('✅ CSS стили добавлены');
    }
    
    /**
     * Главная инициализация
     */
    function initialize() {
        log('=' .repeat(60));
        log('🚀 ИНИЦИАЛИЗАЦИЯ МОДАЛЬНЫХ ОКОН');
        log('=' .repeat(60));
        
        // Ждём полной загрузки DOM
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function() {
                runInitialization();
            });
        } else {
            runInitialization();
        }
        
        // Добавляем обработчик для HTMX событий
        setupHTMXHandlers();
    }
    
    /**
     * Настройка обработчиков HTMX событий
     * для перинициализации модалей при загрузке контента
     */
    function setupHTMXHandlers() {
        log('🔌 Инициализация HTMX обработчиков...');
        
        // После успешной загрузки контента HTMX
        document.addEventListener('htmx:afterSettle', function(e) {
            log('🔌 HTMX afterSettle - перепроверяем модали...');
            
            // Переинициализируем все модали
            setTimeout(function() {
                initializeAllModals();
                initializeModalButtons();
                fixCloseButtons();
            }, 100);
        });
        
        // Также обрабатываем успешные запросы
        document.addEventListener('htmx:afterRequest', function(e) {
            if (e.detail.xhr.status === 200) {
                log('🔌 HTMX success - перепроверяем модали...');
                setTimeout(function() {
                    initializeAllModals();
                    initializeModalButtons();
                }, 100);
            }
        });
        
        log('✅ HTMX обработчики установлены');
    }

    
    function runInitialization() {
        try {
            fixCSSIssues();
            initializeAllModals();
            initializeModalButtons();
            fixBackdropClicks();
            fixCloseButtons();
            fixEscapeKey();
            
            log('=' .repeat(60));
            log('✅ ИНИЦИАЛИЗАЦИЯ ЗАВЕРШЕНА');
            log('=' .repeat(60));
            
            // Проверяем через 500ms что всё инициализировалось
            setTimeout(function() {
                const modals = document.querySelectorAll('.modal');
                const buttons = document.querySelectorAll('[data-bs-toggle="modal"]');
                log(`📊 Финальная проверка: ${modals.length} модалей, ${buttons.length} кнопок`);
            }, 500);
            
        } catch (e) {
            error('КРИТИЧЕСКАЯ ОШИБКА:', e);
        }
    }
    
    // Запускаем инициализацию
    initialize();
    
})();
