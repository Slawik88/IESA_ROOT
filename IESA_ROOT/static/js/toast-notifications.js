/**
 * Toast Notifications System
 * Красивые всплывающие уведомления на сайте
 */

class ToastNotification {
    constructor(message, type = 'info', duration = 4000) {
        this.message = message;
        this.type = type; // 'success', 'error', 'warning', 'info'
        this.duration = duration;
        this.element = null;
        this.init();
    }

    init() {
        // Создаём контейнер для toast если его нет
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container';
            document.body.appendChild(container);
        }

        // Создаём элемент toast
        this.element = document.createElement('div');
        this.element.className = `toast-notification toast-${this.type}`;
        
        const icons = {
            success: '<i class="fas fa-check-circle"></i>',
            error: '<i class="fas fa-exclamation-circle"></i>',
            warning: '<i class="fas fa-exclamation-triangle"></i>',
            info: '<i class="fas fa-info-circle"></i>'
        };

        this.element.innerHTML = `
            <div class="toast-content">
                <span class="toast-icon">${icons[this.type]}</span>
                <span class="toast-message">${this.message}</span>
            </div>
            <button class="toast-close" onclick="this.closest('.toast-notification').remove()">
                <i class="fas fa-times"></i>
            </button>
        `;

        // Добавляем в контейнер
        container.appendChild(this.element);

        // Добавляем класс active для анимации
        setTimeout(() => this.element.classList.add('active'), 10);

        // Автоматическое удаление
        if (this.duration > 0) {
            setTimeout(() => this.remove(), this.duration);
        }

        // Вибрация на мобильных
        if (navigator.vibrate) {
            const vibrationPattern = this.type === 'success' ? [50, 100, 50] : [100];
            navigator.vibrate(vibrationPattern);
        }
    }

    remove() {
        if (!this.element) return;
        this.element.classList.remove('active');
        setTimeout(() => {
            if (this.element && this.element.parentNode) {
                this.element.remove();
            }
        }, 300);
    }

    // Статические методы для удобства
    static success(message, duration = 3000) {
        return new ToastNotification(message, 'success', duration);
    }

    static error(message, duration = 4000) {
        return new ToastNotification(message, 'error', duration);
    }

    static warning(message, duration = 4000) {
        return new ToastNotification(message, 'warning', duration);
    }

    static info(message, duration = 4000) {
        return new ToastNotification(message, 'info', duration);
    }
}

// Экспортируем для использования
window.Toast = ToastNotification;
