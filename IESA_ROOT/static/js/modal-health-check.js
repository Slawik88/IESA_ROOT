/**
 * MODAL HEALTH CHECK - System Diagnostic
 * 
 * Проверка здоровья всех модальных окон на странице
 * Выводит детальный отчёт о статусе инициализации
 * 
 * Для запуска в консоли браузера: modalHealthCheck()
 */

window.modalHealthCheck = function() {
    console.clear();
    console.log('%c🏥 MODAL HEALTH CHECK', 'font-size: 20px; font-weight: bold; color: #007bff;');
    console.log('%c' + '='.repeat(70), 'color: #ddd;');
    
    const report = {
        timestamp: new Date().toISOString(),
        bootstrap: typeof bootstrap !== 'undefined',
        htmx: typeof htmx !== 'undefined',
        modals: [],
        buttons: [],
        backdrops: [],
        issues: []
    };
    
    // 1. Проверка Bootstrap
    console.log('\n%c1️⃣ BOOTSTRAP CHECK', 'font-weight: bold; color: #0066cc;');
    if (report.bootstrap) {
        console.log('✅ Bootstrap загружен:', bootstrap.Modal ? 'Modal API готов' : '❌ Modal API не найден');
    } else {
        console.log('❌ Bootstrap НЕ загружен!');
        report.issues.push('Bootstrap не загружен');
    }
    
    // 2. Проверка HTMX
    console.log('\n%c2️⃣ HTMX CHECK', 'font-weight: bold; color: #0066cc;');
    if (report.htmx) {
        console.log('✅ HTMX загружен');
    } else {
        console.log('⚠️ HTMX не загружен (может быть необязательным)');
    }
    
    // 3. Проверка модалей
    console.log('\n%c3️⃣ MODALS FOUND', 'font-weight: bold; color: #0066cc;');
    const modals = document.querySelectorAll('.modal');
    console.log(`Всего модалей: ${modals.length}`);
    
    modals.forEach((modal, idx) => {
        const info = {
            id: modal.id || `modal-${idx}`,
            classes: modal.className,
            visible: modal.classList.contains('show'),
            instance: bootstrap.Modal.getInstance(modal) ? 'Инициализирована' : 'Не инициализирована'
        };
        
        report.modals.push(info);
        
        const status = modal.classList.contains('show') ? '🟢 OPEN' : '⚫ CLOSED';
        const initStatus = bootstrap.Modal.getInstance(modal) ? '✅' : '⚠️';
        const pointerEvents = window.getComputedStyle(modal).pointerEvents;
        const pointerOk = pointerEvents === 'auto' ? '✅' : '❌';
        
        console.log(`  ${idx + 1}. #${info.id} ${status} ${initStatus} Initialized | pointer-events: ${pointerEvents} ${pointerOk}`);
    });
    
    // 4. Проверка кнопок
    console.log('\n%c4️⃣ MODAL TRIGGER BUTTONS', 'font-weight: bold; color: #0066cc;');
    const buttons = document.querySelectorAll('[data-bs-toggle="modal"]');
    console.log(`Всего кнопок: ${buttons.length}`);
    
    buttons.forEach((btn, idx) => {
        const target = btn.getAttribute('data-bs-target');
        const targetExists = target ? document.querySelector(target) : null;
        const pointerEvents = window.getComputedStyle(btn).pointerEvents;
        const pointerOk = pointerEvents === 'auto' ? '✅' : '❌';
        
        report.buttons.push({
            target: target,
            exists: !!targetExists,
            pointerEvents: pointerEvents
        });
        
        const status = targetExists ? '✅' : '❌';
        console.log(`  ${idx + 1}. ${btn.textContent.trim().slice(0, 30)} → ${target} ${status} | pointer-events: ${pointerEvents} ${pointerOk}`);
        
        if (!targetExists && target) {
            report.issues.push(`Modal target "${target}" не найдена (button #${idx})`);
        }
    });
    
    // 5. Проверка backdrops
    console.log('\n%c5️⃣ MODAL BACKDROPS', 'font-weight: bold; color: #0066cc;');
    const backdrops = document.querySelectorAll('.modal-backdrop');
    console.log(`Всего backdrop'ов: ${backdrops.length}`);
    
    backdrops.forEach((backdrop, idx) => {
        const pointerEvents = window.getComputedStyle(backdrop).pointerEvents;
        const pointerOk = pointerEvents === 'auto' ? '✅' : '❌';
        const isShow = backdrop.classList.contains('show') ? '🟢 SHOW' : '⚫ HIDE';
        
        report.backdrops.push({
            show: backdrop.classList.contains('show'),
            pointerEvents: pointerEvents
        });
        
        console.log(`  ${idx + 1}. backdrop ${isShow} | pointer-events: ${pointerEvents} ${pointerOk}`);
    });
    
    // 6. Проверка CSS
    console.log('\n%c6️⃣ CSS CRITICAL PROPERTIES', 'font-weight: bold; color: #0066cc;');
    
    const testModal = modals[0];
    if (testModal) {
        const css = {
            'z-index': window.getComputedStyle(testModal).zIndex,
            'pointer-events': window.getComputedStyle(testModal).pointerEvents,
            'display': window.getComputedStyle(testModal).display,
            'visibility': window.getComputedStyle(testModal).visibility
        };
        
        console.log('Первая модаль CSS:');
        Object.entries(css).forEach(([key, value]) => {
            const ok = (key === 'pointer-events' && value === 'auto') ? '✅' : 
                       (key === 'display' && value !== 'none') ? '✅' : 
                       (key === 'z-index' && parseInt(value) >= 1050) ? '✅' : 
                       (key === 'visibility' && value !== 'hidden') ? '✅' : '⚠️';
            console.log(`  ${key}: ${value} ${ok}`);
        });
    }
    
    // 7. Итоговый отчёт
    console.log('\n%c' + '='.repeat(70), 'color: #ddd;');
    console.log('\n%c7️⃣ FINAL REPORT', 'font-weight: bold; color: #0066cc;');
    
    if (report.issues.length === 0) {
        console.log('%c✅ ВСЁ ХОРОШО! Модальные окна инициализированы корректно.', 'color: #28a745; font-weight: bold;');
    } else {
        console.log(`%c⚠️ ОБНАРУЖЕНО ${report.issues.length} ПРОБЛЕМ:`, 'color: #ff6600; font-weight: bold;');
        report.issues.forEach(issue => {
            console.log(`  • ${issue}`);
        });
    }
    
    // 8. Советы для отладки
    console.log('\n%c💡 DEBUG TIPS', 'font-weight: bold; color: #0066cc;');
    console.log('• Откройте любую модаль и проверьте:');
    console.log('  - Видимость элементов (Elements tab)');
    console.log('  - pointer-events в CSS');
    console.log('  - z-index значения');
    console.log('• Для открытия модали в консоли:');
    console.log('  const m = new bootstrap.Modal(document.getElementById("registerModal")); m.show();');
    console.log('• Для закрытия:');
    console.log('  const m = bootstrap.Modal.getInstance(document.getElementById("registerModal")); m.hide();');
    
    console.log('\n%c' + '='.repeat(70), 'color: #ddd;');
    console.log('%c📊 Полный отчёт:', 'font-weight: bold;');
    console.table(report);
    
    return report;
};

// Автоматическая проверка при загрузке
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
        setTimeout(() => {
            console.log('%c💬 Введите "modalHealthCheck()" в консоль для полной диагностики', 'color: #0066cc; font-weight: bold;');
        }, 1000);
    });
} else {
    console.log('%c💬 Введите "modalHealthCheck()" в консоль для полной диагностики', 'color: #0066cc; font-weight: bold;');
}
