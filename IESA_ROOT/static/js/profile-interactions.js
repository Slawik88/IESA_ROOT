/**
 * PROFILE INTERACTIONS
 * Версия: 1.0
 * 
 * Функционал:
 * - Follow/Unfollow users
 * - Send messages from profile
 * - Update follow state
 */

(function() {
    'use strict';

    // ====================================================
    // 1. FOLLOW SYSTEM
    // ====================================================

    function initFollowButtons() {
        document.querySelectorAll('.follow-btn').forEach(btn => {
            btn.addEventListener('click', handleFollowClick);
        });
    }

    function handleFollowClick(e) {
        e.preventDefault();
        const btn = e.currentTarget;
        const userId = btn.dataset.userId;
        const username = btn.dataset.username;
        const isFollowing = btn.classList.contains('following');

        if (isFollowing) {
            unfollowUser(btn, userId, username);
        } else {
            followUser(btn, userId, username);
        }
    }

    function followUser(btn, userId, username) {
        // Show loading state
        const originalText = btn.querySelector('.follow-text').textContent;
        btn.querySelector('.follow-text').textContent = 'Following...';
        btn.disabled = true;

        // Simulate API call (replace with real endpoint)
        setTimeout(() => {
            btn.classList.add('following');
            btn.querySelector('.follow-text').textContent = 'Following';
            btn.disabled = false;

            // Store in localStorage (in real app, save to backend)
            const following = JSON.parse(localStorage.getItem('following') || '[]');
            if (!following.includes(userId)) {
                following.push(userId);
                localStorage.setItem('following', JSON.stringify(following));
            }

            // Show toast notification
            if (window.ToastNotifications && window.ToastNotifications.show) {
                window.ToastNotifications.show(`You are now following ${username}!`, 'success');
            }

            console.log(`Followed user: ${username} (ID: ${userId})`);
        }, 500);
    }

    function unfollowUser(btn, userId, username) {
        // Show loading state
        btn.querySelector('.follow-text').textContent = 'Unfollowing...';
        btn.disabled = true;

        // Simulate API call (replace with real endpoint)
        setTimeout(() => {
            btn.classList.remove('following');
            btn.querySelector('.follow-text').textContent = 'Follow';
            btn.disabled = false;

            // Remove from localStorage
            const following = JSON.parse(localStorage.getItem('following') || '[]');
            const index = following.indexOf(userId);
            if (index > -1) {
                following.splice(index, 1);
                localStorage.setItem('following', JSON.stringify(following));
            }

            // Show toast notification
            if (window.ToastNotifications && window.ToastNotifications.show) {
                window.ToastNotifications.show(`You unfollowed ${username}`, 'info');
            }

            console.log(`Unfollowed user: ${username} (ID: ${userId})`);
        }, 500);
    }

    // ====================================================
    // 2. MESSAGING SYSTEM
    // ====================================================

    function initMessageButtons() {
        document.querySelectorAll('.send-message-btn').forEach(btn => {
            btn.addEventListener('click', handleSendMessageClick);
        });
    }

    function handleSendMessageClick(e) {
        e.preventDefault();
        const btn = e.currentTarget;
        const userId = btn.dataset.userId;
        const username = btn.dataset.username;

        openMessagingPanel(userId, username);
    }

    function openMessagingPanel(userId, username) {
        const messagingPanel = document.getElementById('messaging-panel');
        const messagingBtn = document.getElementById('messagingToggle');
        
        if (!messagingPanel) {
            console.error('Messaging panel not found');
            return;
        }

        // Open panel
        messagingPanel.classList.add('open');
        if (messagingBtn) {
            messagingBtn.classList.add('active');
        }

        // Load or create conversation
        loadConversation(userId, username);

        // Show toast
        if (window.ToastNotifications && window.ToastNotifications.show) {
            window.ToastNotifications.show(`Opening chat with ${username}...`, 'info');
        }

        console.log(`Opening conversation with: ${username} (ID: ${userId})`);
    }

    function loadConversation(userId, username) {
        const conversationsList = document.getElementById('conversationsList');
        const emptyState = document.getElementById('messagingEmptyState');

        if (!conversationsList) return;

        // Hide empty state
        if (emptyState) {
            emptyState.style.display = 'none';
        }

        // Create conversation item
        const conversationHTML = `
            <div class="messaging-conversation-item active" data-user-id="${userId}">
                <div class="messaging-conversation-avatar">
                    <span style="font-weight: 600; color: #6b7280;">${username.charAt(0).toUpperCase()}</span>
                </div>
                <div class="messaging-conversation-info">
                    <div class="messaging-conversation-name">${username}</div>
                    <div class="messaging-conversation-preview">Start chatting...</div>
                </div>
            </div>
        `;

        conversationsList.innerHTML = conversationHTML;

        // In real app: load actual conversation history
        setTimeout(() => {
            conversationsList.innerHTML += `
                <div class="p-3 text-center">
                    <div class="alert alert-info mb-0" role="alert">
                        <i class="fas fa-info-circle me-2"></i>
                        <small>Direct messaging coming soon! This feature is under development.</small>
                    </div>
                </div>
            `;
        }, 300);
    }

    // ====================================================
    // 3. LOAD FOLLOW STATE
    // ====================================================

    function loadFollowState() {
        const following = JSON.parse(localStorage.getItem('following') || '[]');
        
        document.querySelectorAll('.follow-btn').forEach(btn => {
            const userId = btn.dataset.userId;
            if (following.includes(userId)) {
                btn.classList.add('following');
                btn.querySelector('.follow-text').textContent = 'Following';
            }
        });
    }

    // ====================================================
    // 4. INITIALIZATION
    // ====================================================

    function init() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                initFollowButtons();
                initMessageButtons();
                loadFollowState();
            });
        } else {
            initFollowButtons();
            initMessageButtons();
            loadFollowState();
        }

        console.log('✓ Profile Interactions initialized');
    }

    // Export API
    window.ProfileInteractions = {
        init,
        followUser: (userId, username) => {
            const btn = document.querySelector(`.follow-btn[data-user-id="${userId}"]`);
            if (btn) followUser(btn, userId, username);
        },
        unfollowUser: (userId, username) => {
            const btn = document.querySelector(`.follow-btn[data-user-id="${userId}"]`);
            if (btn) unfollowUser(btn, userId, username);
        },
        openMessage: (userId, username) => {
            openMessagingPanel(userId, username);
        }
    };

    // Auto-initialize
    init();

})();
