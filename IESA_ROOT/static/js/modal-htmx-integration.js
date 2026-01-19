/**
 * Modal + HTMX Integration Fix
 * 
 * Проблема: После загрузки HTMX контента в modal, кнопки не работают
 * Решение: Перинициализация Bootstrap Modal после HTMX обновлений
 * 
 * Версия: 1.0
 * Дата: 19 января 2026
 */

(function() {
    'use strict';
    
    const DEBUG = true;
    
    function log(...args) {
        if (DEBUG) console.log('[HTMX Modal]', ...args);
    }
    
    /**
     * После загрузки содержимого HTMX, открываем модаль
     */
    function fixHTMXModalOpening() {
        log('🔧 Инициализация HTMX Modal открытия...');
        
        // Обработчик для кнопок с HTMX + modal
        document.addEventListener('htmx:afterSwap', function(e) {
            // Проверяем, была ли запрошена модаль
            const targetId = e.detail.target.getAttribute('hx-target');
            if (targetId && targetId.includes('modal')) {
                log('🔧 HTMX загрузил контент в modal - открываем её');
                
                // Находим ближайшую modal
                const btn = e.detail.xhr.responseURL ? 
                    document.querySelector('[data-bs-target*="modal"]') : 
                    e.detail.target.closest('[data-bs-target*="modal"]');
                
                if (btn) {
                    const modalTarget = btn.getAttribute('data-bs-target');
                    const modal = document.querySelector(modalTarget);
                    if (modal && typeof bootstrap !== 'undefined') {
                        setTimeout(() => {
                            const instance = new bootstrap.Modal(modal);
                            instance.show();
                            log(`✅ Открыта модаль: ${modalTarget}`);
                        }, 100);
                    }
                }
            }
        });
    }
    
    /**
     * Убеждаемся что обработчики HTMX не конфликтуют с Bootstrap Modal
     */
    function fixHTMXBootstrapConflicts() {
        log('🔧 Исправление HTMX/Bootstrap конфликтов...');
        
        // Когда HTMX готовится к запросу
        document.addEventListener('htmx:beforeRequest', function(e) {
            // Если это modal-related запрос, сохраняем state
            const isModalRequest = e.detail.xhr.target && 
                e.detail.xhr.target.closest('[data-bs-toggle="modal"]');
            if (isModalRequest) {
                e.detail.xhr.modalRequest = true;
                log('🔧 HTMX modal request detected');
            }
        });
        
        // Убеждаемся что modal остаётся открытой после HTMX запроса
        document.addEventListener('htmx:afterRequest', function(e) {
            if (e.detail.xhr.modalRequest) {
                // Переинициализируем кнопки в modal
                const openModal = document.querySelector('.modal.show');
                if (openModal) {
                    const buttons = openModal.querySelectorAll('[data-bs-toggle="modal"], [data-bs-dismiss="modal"], .btn');
                    buttons.forEach(btn => {
                        btn.style.pointerEvents = 'auto';
                        btn.style.cursor = 'pointer';
                    });
                    log('✅ Переинициализированы кнопки в modal');
                }
            }
        });
    }
    
    /**
     * Исправляем проблемы с pointer-events при HTMX загрузке
     */
    function fixPointerEventsOnHTMXLoad() {
        log('🔧 Инициализация pointer-events фиксов для HTMX...');
        
        document.addEventListener('htmx:afterSettle', function(e) {
            // Убеждаемся что все элементы в modal имеют correct pointer-events
            const modals = document.querySelectorAll('.modal.show');
            modals.forEach(modal => {
                // Modal elements
                modal.style.pointerEvents = 'auto';
                
                // Modal content
                const content = modal.querySelector('.modal-content');
                if (content) content.style.pointerEvents = 'auto';
                
                // All buttons in modal
                const buttons = modal.querySelectorAll('button, a.btn, [role="button"]');
                buttons.forEach(btn => {
                    btn.style.pointerEvents = 'auto';
                    btn.style.cursor = 'pointer';
                });
                
                // All interactive elements
                const interactive = modal.querySelectorAll('input, select, textarea, a, button');
                interactive.forEach(elem => {
                    elem.style.pointerEvents = 'auto';
                });
            });
        });
    }
    
    /**
     * Логирование всех HTMX событий для отладки
     */
    function setupDebugging() {
        if (!DEBUG) return;
        
        log('🐛 Режим отладки включен');
        
        const events = [
            'htmx:beforeRequest',
            'htmx:afterRequest', 
            'htmx:beforeSwap',
            'htmx:afterSwap',
            'htmx:beforeSettle',
            'htmx:afterSettle',
            'htmx:requestEnded',
            'htmx:error'
        ];
        
        events.forEach(eventName => {
            document.addEventListener(eventName, function(e) {
                log(`📡 Event: ${eventName}`);
                if (e.detail?.target) {
                    log(`   Target: ${e.detail.target.className}`);
                }
            });
        });
    }
    
    /**
     * Главная инициализация
     */
    function initialize() {
        log('=' .repeat(60));
        log('🚀 HTMX MODAL INTEGRATION');
        log('=' .repeat(60));
        
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', runInit);
        } else {
            runInit();
        }
    }
    
    function runInit() {
        try {
            fixHTMXModalOpening();
            fixHTMXBootstrapConflicts();
            fixPointerEventsOnHTMXLoad();
            setupDebugging();
            
            log('=' .repeat(60));
            log('✅ HTMX MODAL INTEGRATION READY');
            log('=' .repeat(60));
        } catch (e) {
            console.error('[HTMX Modal] CRITICAL ERROR:', e);
        }
    }
    
    // Запускаем
    initialize();
    
})();
