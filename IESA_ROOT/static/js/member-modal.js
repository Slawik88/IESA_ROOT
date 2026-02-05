/**
 * Member Modal Handler
 * Handles opening and populating member detail modals
 * Extracted from inline script in index.html
 */

(function() {
    'use strict';

    /**
     * Open member modal with provided data
     * @param {HTMLElement} button - The button that triggered the modal
     */
    function openMemberModal(button) {
        if (!button || !button.dataset) {
            console.error('Invalid button element passed to openMemberModal');
            return;
        }

        // Get modal element
        const modalElement = document.getElementById('memberModal');
        if (!modalElement) {
            console.error('Member modal element not found');
            return;
        }

        // Populate modal data
        populateModalData(button.dataset);

        // Open modal using Bootstrap 5 API
        openModal(modalElement);
    }

    /**
     * Populate modal with member data
     * @param {Object} data - Dataset from button element
     */
    function populateModalData(data) {
        // Set text content
        const elements = {
            name: document.getElementById('memberModalName'),
            position: document.getElementById('memberModalPosition'),
            description: document.getElementById('memberModalDescription'),
            photo: document.getElementById('memberModalPhoto')
        };

        if (elements.name) {
            elements.name.textContent = data.memberName || '';
        }

        if (elements.position) {
            elements.position.textContent = data.memberPosition || '';
        }

        if (elements.description) {
            elements.description.innerHTML = data.memberDescription || '';
        }

        // Handle photo
        if (elements.photo) {
            const photoUrl = data.memberPhoto;
            if (photoUrl) {
                elements.photo.src = photoUrl;
                elements.photo.alt = data.memberName || 'Team member';
                elements.photo.style.display = 'block';
            } else {
                elements.photo.style.display = 'none';
            }
        }
    }

    /**
     * Open modal using Bootstrap 5 Modal API
     * @param {HTMLElement} modalElement - Modal element
     */
    function openModal(modalElement) {
        if (typeof bootstrap === 'undefined') {
            console.error('Bootstrap is not loaded');
            return;
        }

        const modal = new bootstrap.Modal(modalElement, {
            backdrop: true,
            keyboard: true,
            focus: true
        });

        modal.show();
    }

    /**
     * Initialize event delegation for member modal triggers
     */
    function initMemberModals() {
        document.addEventListener('click', function(event) {
            const button = event.target.closest('.member-more-btn');
            if (button) {
                openMemberModal(button);
            }
        });
    }

    // Expose to global scope for backwards compatibility
    window.openMemberModal = openMemberModal;

    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initMemberModals);
    } else {
        initMemberModals();
    }
})();
