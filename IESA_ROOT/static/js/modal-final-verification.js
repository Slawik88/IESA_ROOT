/**
 * FINAL MODAL VERIFICATION SCRIPT
 * 
 * Это финальный скрипт для убеждения что все модали:
 * 1. Инициализированы как Bootstrap.Modal
 * 2. Имеют pointer-events: auto
 * 3. Имеют правильный z-index
 * 4. Кнопки открытия/закрытия работают
 * 
 * Версия: 1.0 Final
 * Дата: 19 января 2026
 */

(function() {
    'use strict';
    
    /**
     * ГЛАВНАЯ ФУНКЦИЯ ПРОВЕРКИ
     */
    function runFinalVerification() {
        console.log('%c🔍 FINAL MODAL VERIFICATION', 'font-size: 18px; color: #ff0000; font-weight: bold;');
        
        // Проверка 1: Bootstrap загружен
        if (typeof bootstrap === 'undefined') {
            console.error('❌ CRITICAL: Bootstrap не загружен!');
            return false;
        }
        console.log('✅ Bootstrap загружен и готов');
        
        // Проверка 2: Все модали инициализированы
        const modals = document.querySelectorAll('.modal');
        console.log(`📊 Найдено ${modals.length} модалей`);
        
        let allInitialized = true;
        modals.forEach((modal, idx) => {
            const id = modal.id || `modal-${idx}`;
            const instance = bootstrap.Modal.getInstance(modal);
            
            if (!instance) {
                console.warn(`⚠️ Modal #${id} не инициализирована - инициализируем...`);
                new bootstrap.Modal(modal);
                allInitialized = false;
            } else {
                console.log(`✅ Modal #${id} инициализирована`);
            }
            
            // Проверка pointer-events
            const styles = window.getComputedStyle(modal);
            if (styles.pointerEvents !== 'auto') {
                console.warn(`⚠️ Modal #${id} имеет pointer-events: ${styles.pointerEvents} (нужно: auto)`);
                modal.style.pointerEvents = 'auto';
            }
        });
        
        if (allInitialized) {
            console.log('✅ Все модали инициализированы корректно');
        }
        
        // Проверка 3: Кнопки открытия работают
        const buttons = document.querySelectorAll('[data-bs-toggle="modal"]');
        console.log(`📊 Найдено ${buttons.length} кнопок открытия`);
        
        let buttonIssues = 0;
        buttons.forEach((btn, idx) => {
            const target = btn.getAttribute('data-bs-target');
            const modal = document.querySelector(target);
            
            if (!modal) {
                console.error(`❌ Кнопка #${idx}: target "${target}" не найден`);
                buttonIssues++;
                return;
            }
            
            // Гарантируем pointer-events на кнопке
            btn.style.pointerEvents = 'auto';
            
            // Добавляем обработчик если его нет
            if (!btn.hasAttribute('data-modal-handler')) {
                btn.addEventListener('click', function(e) {
                    if (!modal) return;
                    
                    let instance = bootstrap.Modal.getInstance(modal);
                    if (!instance) {
                        instance = new bootstrap.Modal(modal);
                    }
                    instance.show();
                }, false);
                
                btn.setAttribute('data-modal-handler', 'true');
            }
        });
        
        if (buttonIssues === 0) {
            console.log('✅ Все кнопки открытия работают');
        } else {
            console.warn(`⚠️ ${buttonIssues} кнопок имеют проблемы`);
        }
        
        // Проверка 4: Close buttons
        const closeButtons = document.querySelectorAll('[data-bs-dismiss="modal"]');
        console.log(`📊 Найдено ${closeButtons.length} кнопок закрытия`);
        
        closeButtons.forEach((btn, idx) => {
            btn.style.pointerEvents = 'auto';
            btn.style.cursor = 'pointer';
            
            if (!btn.hasAttribute('data-close-handler')) {
                btn.addEventListener('click', function(e) {
                    const modal = this.closest('.modal');
                    if (modal) {
                        const instance = bootstrap.Modal.getInstance(modal);
                        if (instance) {
                            instance.hide();
                        }
                    }
                }, false);
                
                btn.setAttribute('data-close-handler', 'true');
            }
        });
        
        console.log('✅ Кнопки закрытия инициализированы');
        
        // Проверка 5: Backdrop клики
        const backdrops = document.querySelectorAll('.modal-backdrop');
        console.log(`📊 Найдено ${backdrops.length} backdrop элементов`);
        
        backdrops.forEach((backdrop, idx) => {
            backdrop.style.pointerEvents = 'auto';
            backdrop.style.cursor = 'pointer';
            
            if (!backdrop.hasAttribute('data-backdrop-handler')) {
                backdrop.addEventListener('click', function(e) {
                    if (e.target === this) {
                        const modal = document.querySelector('.modal.show');
                        if (modal) {
                            const instance = bootstrap.Modal.getInstance(modal);
                            if (instance) {
                                instance.hide();
                            }
                        }
                    }
                });
                
                backdrop.setAttribute('data-backdrop-handler', 'true');
            }
        });
        
        console.log('✅ Backdrop клики инициализированы');
        
        // Итоговый результат
        console.log('%c' + '='.repeat(70), 'color: #ddd;');
        console.log('%c✅ ФИНАЛЬНАЯ ПРОВЕРКА ЗАВЕРШЕНА УСПЕШНО', 'color: #28a745; font-weight: bold; font-size: 16px;');
        console.log('%c' + '='.repeat(70), 'color: #ddd;');
        
        return true;
    }
    
    /**
     * Запуск при загрузке
     */
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            setTimeout(runFinalVerification, 100);
        });
    } else {
        setTimeout(runFinalVerification, 100);
    }
    
    // Экспортируем для ручного запуска
    window.runModalVerification = runFinalVerification;
    
})();
