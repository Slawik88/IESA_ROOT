/**
 * Messaging Panel - Load and display user conversations
 * Loads conversations when panel opens, prevents skeleton flashing
 * Optimized for smooth rendering and no black artifacts
 */

(function() {
    'use strict';
    
    let cachedConversations = null;
    let loadingPromise = null;
    let isLoading = false;

    /**
     * Fetch conversations from API with retry logic
     */
    async function fetchConversations() {
        // Use cached data if available
        if (cachedConversations !== null) {
            return cachedConversations;
        }

        // Return existing promise if already loading
        if (loadingPromise) {
            return loadingPromise;
        }

        // Prevent duplicate requests
        if (isLoading) {
            return loadingPromise || Promise.resolve([]);
        }

        isLoading = true;

        // Create new fetch promise with timeout
        loadingPromise = Promise.race([
            fetch('/messages/api/conversations/', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                credentials: 'same-origin'
            }),
            new Promise((_, reject) => 
                setTimeout(() => reject(new Error('Timeout')), 5000)
            )
        ])
        .then(response => {
            if (response.status === 401 || response.status === 403) {
                return []; // User not authenticated or no access
            }
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            cachedConversations = Array.isArray(data) ? data : [];
            isLoading = false;
            loadingPromise = null;
            return cachedConversations;
        })
        .catch(err => {
            console.warn('⚠️ Failed to load conversations:', err.message);
            isLoading = false;
            loadingPromise = null;
            return [];
        });

        return loadingPromise;
    }

    /**
     * Render conversation item HTML with proper escaping
     */
    function renderConversationItem(conversation) {
        const lastMessage = conversation.last_message || {};
        const lastMessageText = lastMessage.text || '[File]';
        const lastMessageTime = lastMessage.created_at 
            ? new Date(lastMessage.created_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
            : '';
        
        const otherParticipant = conversation.other_participant || {};
        const participantName = otherParticipant.username || 'Unknown';
        const participantAvatar = otherParticipant.avatar?.url || null;
        const participantAvatarInitial = participantName.charAt(0).toUpperCase();

        const unreadClass = conversation.unread_count > 0 ? 'unread' : '';
        const unreadBadge = conversation.unread_count > 0 
            ? `<span class="badge bg-primary rounded-pill" style="font-size: 11px; padding: 2px 6px;">${conversation.unread_count}</span>`
            : '';

        const avatarHTML = participantAvatar
            ? `<img src="${escapeHtml(participantAvatar)}" alt="${escapeHtml(participantName)}" class="avatar-img" style="width: 100%; height: 100%; object-fit: cover;">`
            : `<span class="avatar-initial">${escapeHtml(participantAvatarInitial)}</span>`;

        const previewText = escapeHtml(lastMessageText.substring(0, 40)) + (lastMessageText.length > 40 ? '...' : '');

        return `
            <a href="/messages/${conversation.id}/" 
               class="messaging-conversation-item ${unreadClass}" 
               data-conversation-id="${conversation.id}"
               title="${escapeHtml(participantName)}"
               style="text-decoration: none; color: inherit;">
                <div class="messaging-conversation-avatar">
                    ${avatarHTML}
                </div>
                <div class="messaging-conversation-info">
                    <div class="messaging-conversation-name">
                        <span>${escapeHtml(participantName)}</span>
                        ${unreadBadge}
                    </div>
                    <div class="messaging-conversation-preview">
                        ${previewText}
                    </div>
                    <div class="messaging-conversation-time">
                        ${lastMessageTime}
                    </div>
                </div>
            </a>
        `;
    }

    /**
     * Escape HTML to prevent XSS
     */
    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Create loading skeleton HTML
     */
    function createSkeletonHTML() {
        return `
            <div class="messaging-loading-skeleton" style="padding: 8px 0;">
                ${Array.from({length: 3}, () => '<div class="skeleton-item"></div>').join('')}
            </div>
        `;
    }

    /**
     * Load and display conversations in panel with smooth transition
     */
    async function loadAndDisplayConversations() {
        const conversationsList = document.getElementById('conversationsList');
        const emptyState = document.getElementById('messagingEmptyState');

        if (!conversationsList) {
            console.warn('⚠️ conversationsList element not found');
            return;
        }

        // Show skeleton only if list is empty
        if (conversationsList.innerHTML.trim() === '') {
            conversationsList.innerHTML = createSkeletonHTML();
        }

        try {
            const conversations = await fetchConversations();

            // Smooth fade out skeleton
            const skeleton = conversationsList.querySelector('.messaging-loading-skeleton');
            if (skeleton) {
                skeleton.style.opacity = '0';
                skeleton.style.transition = 'opacity 0.2s ease-out';
                setTimeout(() => {
                    conversationsList.innerHTML = '';
                }, 150);
            } else {
                conversationsList.innerHTML = '';
            }

            if (conversations.length === 0) {
                // Show empty state with fade in
                if (emptyState) {
                    emptyState.style.display = 'flex';
                    emptyState.style.animation = 'fadeIn 0.3s ease-in';
                }
            } else {
                // Hide empty state
                if (emptyState) {
                    emptyState.style.display = 'none';
                }

                // Render conversations with staggered animation
                const fragment = document.createDocumentFragment();
                conversations.forEach((conv, index) => {
                    const div = document.createElement('div');
                    div.innerHTML = renderConversationItem(conv);
                    div.style.animation = `slideIn 0.3s ease-out ${index * 0.05}s backwards`;
                    fragment.appendChild(div.firstElementChild);
                });
                
                conversationsList.appendChild(fragment);

                // Add click handlers
                conversationsList.querySelectorAll('.messaging-conversation-item').forEach(item => {
                    item.addEventListener('click', function(e) {
                        e.preventDefault();
                        window.location.href = this.href;
                    });
                });
            }
        } catch (err) {
            console.error('❌ Error loading conversations:', err);
            conversationsList.innerHTML = '';
            if (emptyState) {
                emptyState.innerHTML = `
                    <i class="fas fa-exclamation-triangle fa-2x mb-3 text-warning" style="opacity: 0.7;"></i>
                    <p class="fw-semibold mb-2">Failed to load conversations</p>
                    <p class="small text-muted">Please try again later</p>
                `;
                emptyState.style.display = 'flex';
            }
        }
    }

    /**
     * Add animation keyframes to document
     */
    function injectAnimations() {
        if (document.querySelector('style[data-messaging-animations]')) return;
        
        const style = document.createElement('style');
        style.setAttribute('data-messaging-animations', 'true');
        style.textContent = `
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            @keyframes slideIn {
                from {
                    opacity: 0;
                    transform: translateX(-8px);
                }
                to {
                    opacity: 1;
                    transform: translateX(0);
                }
            }
        `;
        document.head.appendChild(style);
    }

    /**
     * Initialize messaging panel
     */
    function initMessagingPanel() {
        const messagingBtn = document.getElementById('messagingToggle');
        const messagingPanel = document.getElementById('messaging-panel');

        if (!messagingBtn || !messagingPanel) {
            console.warn('⚠️ Messaging panel elements not found');
            return;
        }

        // Inject animations
        injectAnimations();

        // Track panel state
        let panelWasOpen = false;

        // Load conversations when panel opens
        messagingBtn.addEventListener('click', function() {
            const isOpen = messagingPanel.classList.contains('open');
            if (isOpen && !panelWasOpen) {
                // Panel just opened
                panelWasOpen = true;
                loadAndDisplayConversations();
            } else if (!isOpen) {
                panelWasOpen = false;
            }
        });

        console.log('✓ Messaging panel initialized');
    }

    /**
     * Initialize when DOM is ready
     */
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initMessagingPanel);
    } else {
        initMessagingPanel();
    }

    // Export API for external use
    window.MessagingPanel = {
        loadConversations: loadAndDisplayConversations,
        refreshConversations: () => {
            cachedConversations = null;
            loadAndDisplayConversations();
        }
    };
})();
