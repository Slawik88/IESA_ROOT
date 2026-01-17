/**
 * Modal Handler - обеспечивает правильное закрытие modal окон
 * Решает проблему: modal backdrop перекрывает весь сайт и становится не кликабельным
 */

(function() {
    'use strict';

    // Инициализация при загрузке документа
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initModalHandler);
    } else {
        initModalHandler();
    }

    function initModalHandler() {
        console.log('🎬 Modal Handler initialized');

        // Добавляем обработчик для всех modal backdrop элементов
        document.addEventListener('click', function(e) {
            // Если клик на backdrop (пустое место за modal)
            if (e.target.classList.contains('modal-backdrop')) {
                console.log('💥 Clicked on modal backdrop - closing modal');
                
                // Найди и закрой все активные modal
                const openModals = document.querySelectorAll('.modal.show');
                openModals.forEach(modal => {
                    closeModal(modal);
                });
            }
        });

        // Специальный обработчик для ESC ключа
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                console.log('🔑 ESC pressed - closing modals');
                const openModals = document.querySelectorAll('.modal.show');
                openModals.forEach(modal => {
                    closeModal(modal);
                });
            }
        });

        // Обработчик для кнопок закрытия
        document.addEventListener('click', function(e) {
            if (e.target.classList.contains('btn-close')) {
                const modal = e.target.closest('.modal');
                if (modal) {
                    console.log('❌ Close button clicked - closing modal');
                    closeModal(modal);
                }
            }
        });
    }

    /**
     * Закрытие модального окна
     * @param {Element} modal - модальное окно элемент
     */
    function closeModal(modal) {
        if (!modal) return;

        // Используем Bootstrap Modal API если доступна
        if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
            const bsModal = bootstrap.Modal.getInstance(modal) || new bootstrap.Modal(modal);
            bsModal.hide();
            console.log('✅ Modal closed via Bootstrap API');
        } else {
            // Fallback - удаляем классы вручную
            modal.classList.remove('show');
            modal.style.display = 'none';
            
            // Удаляем backdrop
            const backdrop = document.querySelector('.modal-backdrop');
            if (backdrop) {
                backdrop.remove();
            }
            
            // Восстанавливаем body состояние
            document.body.classList.remove('modal-open');
            document.body.style.overflow = '';
            console.log('✅ Modal closed via fallback method');
        }
    }

    // Мониторим для новых modal элементов (динамические вставки)
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.type === 'childList') {
                mutation.addedNodes.forEach(function(node) {
                    if (node.nodeType === 1 && node.classList && node.classList.contains('modal')) {
                        console.log('🆕 New modal detected - attaching handlers');
                        // Обработчики будут работать через event delegation
                    }
                });
            }
        });
    });

    // Начинаем мониторить добавление новых элементов
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });

    // Экспортируем функции если нужны в других местах
    window.ModalHandler = {
        close: closeModal,
        closeAll: function() {
            document.querySelectorAll('.modal.show').forEach(closeModal);
        }
    };
})();
