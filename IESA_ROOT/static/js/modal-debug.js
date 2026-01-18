/**
 * Modal Debug Script - диагностика проблем с модальными окнами
 */

(function() {
    'use strict';
    
    console.log('🔍 Modal Debug Script loaded');
    
    document.addEventListener('DOMContentLoaded', function() {
        console.log('🔍 DOM loaded - checking modals...');
        
        // Проверяем наличие Bootstrap
        if (typeof bootstrap === 'undefined') {
            console.error('❌ Bootstrap JS NOT loaded!');
            return;
        } else {
            console.log('✅ Bootstrap JS loaded:', bootstrap.Modal);
        }
        
        // Проверяем модалки
        const modals = document.querySelectorAll('.modal');
        console.log(`🔍 Found ${modals.length} modals in DOM:`, 
            Array.from(modals).map(m => m.id || 'unnamed'));
        
        // Проверяем кнопки
        const modalButtons = document.querySelectorAll('[data-bs-toggle="modal"]');
        console.log(`🔍 Found ${modalButtons.length} modal trigger buttons:`, 
            Array.from(modalButtons).map(b => b.getAttribute('data-bs-target')));
        
        // Проверяем конкретные модалки
        const newChatModal = document.getElementById('newChatModal');
        const newGroupModal = document.getElementById('newGroupModal');
        
        if (newChatModal) {
            console.log('✅ #newChatModal found in DOM');
            console.log('   - Classes:', newChatModal.className);
            console.log('   - Parent:', newChatModal.parentElement?.tagName);
        } else {
            console.error('❌ #newChatModal NOT found in DOM');
        }
        
        if (newGroupModal) {
            console.log('✅ #newGroupModal found in DOM');
            console.log('   - Classes:', newGroupModal.className);
            console.log('   - Parent:', newGroupModal.parentElement?.tagName);
        } else {
            console.error('❌ #newGroupModal NOT found in DOM');
        }
        
        // Добавляем слушатели на кнопки
        modalButtons.forEach(button => {
            const target = button.getAttribute('data-bs-target');
            console.log(`🔍 Setting up click listener for button -> ${target}`);
            
            button.addEventListener('click', function(e) {
                console.log(`🖱️ Click detected on button -> ${target}`);
                console.log('   - Event:', e);
                console.log('   - Button:', button);
                
                // Проверяем, создаётся ли Bootstrap Modal instance
                const modalElement = document.querySelector(target);
                if (modalElement) {
                    console.log(`✅ Modal element ${target} exists`);
                    
                    // Пробуем создать Bootstrap Modal вручную
                    try {
                        const modalInstance = new bootstrap.Modal(modalElement);
                        console.log('✅ Bootstrap Modal instance created manually');
                        
                        // Открываем модалку вручную
                        setTimeout(() => {
                            console.log('🔓 Attempting to show modal manually...');
                            modalInstance.show();
                        }, 100);
                    } catch (err) {
                        console.error('❌ Failed to create Bootstrap Modal:', err);
                    }
                } else {
                    console.error(`❌ Modal element ${target} NOT found`);
                }
            });
        });
        
        // Проверяем события Bootstrap модалок
        modals.forEach(modal => {
            modal.addEventListener('show.bs.modal', function(e) {
                console.log(`📂 Modal opening: ${modal.id}`, e);
            });
            
            modal.addEventListener('shown.bs.modal', function(e) {
                console.log(`✅ Modal opened: ${modal.id}`, e);
            });
            
            modal.addEventListener('hide.bs.modal', function(e) {
                console.log(`📁 Modal closing: ${modal.id}`, e);
            });
            
            modal.addEventListener('hidden.bs.modal', function(e) {
                console.log(`✅ Modal closed: ${modal.id}`, e);
            });
        });
        
        console.log('🔍 Modal debug initialization complete');
    });
})();
