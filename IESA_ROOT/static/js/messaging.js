/**
 * TIER 8: MESSAGING SYSTEM
 * Версия: 1.0
 * 
 * Функционал:
 * - Direct messages между пользователями
 * - Real-time typing indicators
 * - Message threads (conversations)
 * - Read receipts
 * - Auto-scroll to latest message
 */

(function() {
    'use strict';

    // ====================================================
    // 1. STATE MANAGEMENT
    // ====================================================

    let currentConversationId = null;
    let typingTimeout = null;
    let conversations = {};
    let messages = {};

    // ====================================================
    // 2. MESSAGING UI
    // ====================================================

    function initMessaging() {
        // Check if we're on messages page
        const container = document.querySelector('.messages-container');
        if (!container) return;

        loadConversations();
        setupEventListeners();
        loadSampleData(); // For demo purposes

        console.log('✓ Messaging System (TIER 8) initialized');
    }

    function setupEventListeners() {
        // Conversation selection
        document.addEventListener('click', (e) => {
            const conversationItem = e.target.closest('.conversation-item');
            if (conversationItem) {
                const conversationId = conversationItem.dataset.conversationId;
                selectConversation(conversationId);
            }
        });

        // Send message
        const sendBtn = document.querySelector('.chat-send-btn');
        if (sendBtn) {
            sendBtn.addEventListener('click', sendMessage);
        }

        // Input handling
        const input = document.querySelector('.chat-input');
        if (input) {
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });

            input.addEventListener('input', handleTyping);
        }

        // Mobile back button
        const backBtn = document.querySelector('.chat-back-btn');
        if (backBtn) {
            backBtn.addEventListener('click', () => {
                document.querySelector('.chat-view').classList.remove('show');
                document.querySelector('.conversations-sidebar').classList.add('show');
            });
        }

        // Search conversations
        const searchInput = document.querySelector('.conversations-search input');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                filterConversations(e.target.value);
            });
        }
    }

    function selectConversation(conversationId) {
        currentConversationId = conversationId;

        // Update UI
        document.querySelectorAll('.conversation-item').forEach(item => {
            item.classList.remove('active');
        });
        
        const selectedItem = document.querySelector(`.conversation-item[data-conversation-id="${conversationId}"]`);
        if (selectedItem) {
            selectedItem.classList.add('active');
            selectedItem.classList.remove('unread');
            
            // Remove unread badge
            const badge = selectedItem.querySelector('.unread-badge');
            if (badge) badge.remove();
        }

        // Load messages
        loadMessages(conversationId);

        // Mobile: show chat view
        if (window.innerWidth < 768) {
            document.querySelector('.conversations-sidebar').classList.remove('show');
            document.querySelector('.chat-view').classList.add('show');
        }
    }

    function loadMessages(conversationId) {
        const chatMessages = document.querySelector('.chat-messages');
        if (!chatMessages) return;

        chatMessages.innerHTML = '';

        const conversationMessages = messages[conversationId] || [];
        let lastDate = null;

        conversationMessages.forEach((msg, index) => {
            // Add date divider if date changed
            const msgDate = new Date(msg.timestamp).toDateString();
            if (msgDate !== lastDate) {
                chatMessages.appendChild(createDateDivider(msg.timestamp));
                lastDate = msgDate;
            }

            chatMessages.appendChild(createMessageBubble(msg));
        });

        // Scroll to bottom
        scrollToBottom(chatMessages);
    }

    function createDateDivider(timestamp) {
        const div = document.createElement('div');
        div.className = 'message-date-divider';
        
        const date = new Date(timestamp);
        const today = new Date();
        const yesterday = new Date(today);
        yesterday.setDate(yesterday.getDate() - 1);

        let dateText;
        if (date.toDateString() === today.toDateString()) {
            dateText = 'Today';
        } else if (date.toDateString() === yesterday.toDateString()) {
            dateText = 'Yesterday';
        } else {
            dateText = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        }

        div.innerHTML = `<span>${dateText}</span>`;
        return div;
    }

    function createMessageBubble(msg) {
        const bubble = document.createElement('div');
        bubble.className = `message-bubble ${msg.sent ? 'sent' : 'received'}`;

        if (!msg.sent) {
            const avatar = document.createElement('img');
            avatar.className = 'message-avatar';
            avatar.src = msg.avatar || '/static/img/default-avatar.png';
            avatar.alt = msg.senderName;
            bubble.appendChild(avatar);
        }

        const wrapper = document.createElement('div');
        wrapper.className = 'message-content-wrapper';

        const content = document.createElement('div');
        content.className = 'message-content';
        content.textContent = msg.text;

        const meta = document.createElement('div');
        meta.className = 'message-meta';
        
        const time = new Date(msg.timestamp).toLocaleTimeString('en-US', { 
            hour: '2-digit', 
            minute: '2-digit' 
        });
        meta.innerHTML = `<span>${time}</span>`;

        if (msg.sent) {
            const receipt = document.createElement('span');
            receipt.className = `message-read-receipt ${msg.read ? 'read' : ''}`;
            receipt.innerHTML = msg.read ? '<i class="fas fa-check-double"></i>' : '<i class="fas fa-check"></i>';
            meta.appendChild(receipt);
        }

        wrapper.appendChild(content);
        wrapper.appendChild(meta);
        bubble.appendChild(wrapper);

        return bubble;
    }

    function sendMessage() {
        const input = document.querySelector('.chat-input');
        if (!input || !currentConversationId) return;

        const text = input.value.trim();
        if (!text) return;

        const message = {
            id: Date.now(),
            conversationId: currentConversationId,
            text: text,
            timestamp: new Date().toISOString(),
            sent: true,
            read: false
        };

        // Add to messages
        if (!messages[currentConversationId]) {
            messages[currentConversationId] = [];
        }
        messages[currentConversationId].push(message);

        // Update UI
        const chatMessages = document.querySelector('.chat-messages');
        if (chatMessages) {
            chatMessages.appendChild(createMessageBubble(message));
            scrollToBottom(chatMessages);
        }

        // Clear input
        input.value = '';
        input.style.height = 'auto';

        // Update conversation preview
        updateConversationPreview(currentConversationId, text);

        // Show toast
        showToast('Message sent!', 'success');

        // Simulate read receipt after 2 seconds
        setTimeout(() => {
            message.read = true;
            const receipt = chatMessages.querySelector('.message-bubble:last-child .message-read-receipt');
            if (receipt) {
                receipt.classList.add('read');
                receipt.innerHTML = '<i class="fas fa-check-double"></i>';
            }
        }, 2000);
    }

    function handleTyping() {
        const input = document.querySelector('.chat-input');
        if (!input) return;

        // Auto-resize textarea
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 120) + 'px';

        // Enable/disable send button
        const sendBtn = document.querySelector('.chat-send-btn');
        if (sendBtn) {
            sendBtn.disabled = !input.value.trim();
        }

        // Typing indicator (would send to server in real app)
        clearTimeout(typingTimeout);
        typingTimeout = setTimeout(() => {
            // Stop typing indicator
        }, 1000);
    }

    function scrollToBottom(container, smooth = true) {
        if (smooth) {
            container.scrollTo({
                top: container.scrollHeight,
                behavior: 'smooth'
            });
        } else {
            container.scrollTop = container.scrollHeight;
        }
    }

    function updateConversationPreview(conversationId, text) {
        const item = document.querySelector(`.conversation-item[data-conversation-id="${conversationId}"]`);
        if (item) {
            const preview = item.querySelector('.conversation-preview');
            if (preview) {
                preview.textContent = text;
            }

            const time = item.querySelector('.conversation-time');
            if (time) {
                time.textContent = 'Just now';
            }

            // Move to top
            const list = item.parentElement;
            list.insertBefore(item, list.firstChild);
        }
    }

    function filterConversations(query) {
        const items = document.querySelectorAll('.conversation-item');
        const lowerQuery = query.toLowerCase();

        items.forEach(item => {
            const name = item.querySelector('.conversation-name').textContent.toLowerCase();
            const preview = item.querySelector('.conversation-preview').textContent.toLowerCase();
            
            if (name.includes(lowerQuery) || preview.includes(lowerQuery)) {
                item.style.display = 'flex';
            } else {
                item.style.display = 'none';
            }
        });
    }

    // ====================================================
    // 3. DATA LOADING (DEMO)
    // ====================================================

    function loadConversations() {
        // In real app, fetch from backend
        conversations = {
            '1': {
                id: '1',
                name: 'John Doe',
                avatar: null,
                lastMessage: 'Hey, how are you?',
                lastMessageTime: '10:30 AM',
                unread: 2,
                online: true
            },
            '2': {
                id: '2',
                name: 'Jane Smith',
                avatar: null,
                lastMessage: 'See you tomorrow!',
                lastMessageTime: 'Yesterday',
                unread: 0,
                online: false
            }
        };
    }

    function loadSampleData() {
        // Sample messages for demo
        messages = {
            '1': [
                {
                    id: 1,
                    text: 'Hey, how are you?',
                    timestamp: new Date(Date.now() - 3600000).toISOString(),
                    sent: false,
                    read: true,
                    senderName: 'John Doe'
                },
                {
                    id: 2,
                    text: 'I\'m good, thanks! How about you?',
                    timestamp: new Date(Date.now() - 3000000).toISOString(),
                    sent: true,
                    read: true
                },
                {
                    id: 3,
                    text: 'Great! Want to grab coffee later?',
                    timestamp: new Date(Date.now() - 1800000).toISOString(),
                    sent: false,
                    read: true,
                    senderName: 'John Doe'
                }
            ]
        };
    }

    // ====================================================
    // 4. UTILITY FUNCTIONS
    // ====================================================

    function showToast(message, type = 'info') {
        if (window.ToastNotifications && window.ToastNotifications.show) {
            window.ToastNotifications.show(message, type);
        } else {
            console.log(`[${type.toUpperCase()}] ${message}`);
        }
    }

    // ====================================================
    // 5. INITIALIZATION
    // ====================================================

    function init() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initMessaging);
        } else {
            initMessaging();
        }
    }

    // Export for global access
    window.MessagingSystem = {
        init,
        selectConversation,
        sendMessage,
        conversations,
        messages
    };

    // Auto-initialize
    init();

})();
