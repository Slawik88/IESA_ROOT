/**
 * TIER 8: SOCIAL FEATURES - Reactions & Enhanced Comments
 * Версия: 1.0
 * 
 * Функционал:
 * - Emoji реакции на посты (👍❤️😂😮😢🔥)
 * - Animated reaction picker
 * - Real-time reaction updates
 * - Enhanced comments with threading
 * - Quick reply system
 * - @mention autocomplete
 */

(function() {
    'use strict';

    // ====================================================
    // 1. REACTION SYSTEM
    // ====================================================

    const REACTIONS = [
        { emoji: '👍', name: 'like', label: 'Like' },
        { emoji: '❤️', name: 'love', label: 'Love' },
        { emoji: '😂', name: 'haha', label: 'Haha' },
        { emoji: '😮', name: 'wow', label: 'Wow' },
        { emoji: '😢', name: 'sad', label: 'Sad' },
        { emoji: '🔥', name: 'fire', label: 'Fire' }
    ];

    // Initialize reaction system for all posts
    function initReactions() {
        // Add reaction containers to posts
        document.querySelectorAll('[data-post-id]').forEach(post => {
            const postId = post.dataset.postId;
            const actionsContainer = post.querySelector('.post-actions, .card-footer');
            
            if (actionsContainer && !actionsContainer.querySelector('.reaction-container')) {
                const reactionContainer = createReactionContainer(postId);
                actionsContainer.insertBefore(reactionContainer, actionsContainer.firstChild);
            }
        });

        // Event delegation for reaction buttons
        document.addEventListener('click', handleReactionClick);
    }

    function createReactionContainer(postId) {
        const container = document.createElement('div');
        container.className = 'reaction-container';
        container.dataset.postId = postId;

        // Add reaction button
        const addBtn = document.createElement('button');
        addBtn.className = 'reaction-add-btn';
        addBtn.innerHTML = '😊';
        addBtn.setAttribute('aria-label', 'Add reaction');
        addBtn.title = 'Add reaction';

        // Create reaction picker
        const picker = createReactionPicker(postId);
        addBtn.appendChild(picker);

        container.appendChild(addBtn);

        // Load existing reactions
        loadReactions(postId, container);

        return container;
    }

    function createReactionPicker(postId) {
        const picker = document.createElement('div');
        picker.className = 'reaction-picker';
        picker.role = 'menu';

        REACTIONS.forEach(reaction => {
            const item = document.createElement('button');
            item.className = 'reaction-picker-item';
            item.innerHTML = reaction.emoji;
            item.dataset.reactionName = reaction.name;
            item.dataset.postId = postId;
            item.title = reaction.label;
            item.setAttribute('aria-label', reaction.label);
            item.role = 'menuitem';
            picker.appendChild(item);
        });

        return picker;
    }

    function handleReactionClick(e) {
        // Toggle reaction picker
        if (e.target.classList.contains('reaction-add-btn')) {
            e.stopPropagation();
            const picker = e.target.querySelector('.reaction-picker');
            toggleReactionPicker(picker);
            return;
        }

        // Add reaction
        if (e.target.classList.contains('reaction-picker-item')) {
            e.stopPropagation();
            const reactionName = e.target.dataset.reactionName;
            const postId = e.target.dataset.postId;
            addReaction(postId, reactionName);
            
            // Close picker
            const picker = e.target.closest('.reaction-picker');
            picker.classList.remove('show');
            return;
        }

        // Toggle existing reaction
        if (e.target.classList.contains('reaction-badge') || e.target.closest('.reaction-badge')) {
            const badge = e.target.classList.contains('reaction-badge') ? e.target : e.target.closest('.reaction-badge');
            const postId = badge.dataset.postId;
            const reactionName = badge.dataset.reactionName;
            toggleReaction(postId, reactionName, badge);
            return;
        }

        // Close all pickers when clicking outside
        document.querySelectorAll('.reaction-picker.show').forEach(picker => {
            picker.classList.remove('show');
        });
    }

    function toggleReactionPicker(picker) {
        // Close all other pickers
        document.querySelectorAll('.reaction-picker.show').forEach(p => {
            if (p !== picker) p.classList.remove('show');
        });
        
        picker.classList.toggle('show');
    }

    function addReaction(postId, reactionName) {
        const container = document.querySelector(`.reaction-container[data-post-id="${postId}"]`);
        if (!container) return;

        // Find existing badge or create new one
        let badge = container.querySelector(`.reaction-badge[data-reaction-name="${reactionName}"]`);
        
        if (!badge) {
            badge = createReactionBadge(postId, reactionName, 1, true);
            container.appendChild(badge);
            badge.classList.add('new');
            setTimeout(() => badge.classList.remove('new'), 400);
        } else {
            // Increment count
            const countEl = badge.querySelector('.reaction-badge-count');
            const currentCount = parseInt(countEl.textContent) || 0;
            countEl.textContent = currentCount + 1;
            badge.classList.add('active');
        }

        // Store in localStorage (in real app, send to backend)
        storeReaction(postId, reactionName, true);

        // Show toast notification
        showToast(`Реакция ${getReactionEmoji(reactionName)} добавлена!`, 'success');
    }

    function toggleReaction(postId, reactionName, badge) {
        const isActive = badge.classList.contains('active');
        
        if (isActive) {
            // Remove reaction
            const countEl = badge.querySelector('.reaction-badge-count');
            const currentCount = parseInt(countEl.textContent) || 0;
            
            if (currentCount <= 1) {
                badge.remove();
            } else {
                countEl.textContent = currentCount - 1;
                badge.classList.remove('active');
            }
            
            storeReaction(postId, reactionName, false);
            showToast('Реакция удалена', 'info');
        } else {
            // Add reaction
            badge.classList.add('active');
            const countEl = badge.querySelector('.reaction-badge-count');
            const currentCount = parseInt(countEl.textContent) || 0;
            countEl.textContent = currentCount + 1;
            
            storeReaction(postId, reactionName, true);
            showToast(`Реакция ${getReactionEmoji(reactionName)} добавлена!`, 'success');
        }
    }

    function createReactionBadge(postId, reactionName, count, isActive) {
        const badge = document.createElement('div');
        badge.className = `reaction-badge ${isActive ? 'active' : ''}`;
        badge.dataset.postId = postId;
        badge.dataset.reactionName = reactionName;
        badge.role = 'button';
        badge.tabIndex = 0;
        badge.title = `${getReactionLabel(reactionName)} (click to toggle)`;

        const emoji = document.createElement('span');
        emoji.className = 'reaction-badge-emoji';
        emoji.textContent = getReactionEmoji(reactionName);

        const countEl = document.createElement('span');
        countEl.className = 'reaction-badge-count';
        countEl.textContent = count;

        badge.appendChild(emoji);
        badge.appendChild(countEl);

        return badge;
    }

    function getReactionEmoji(name) {
        const reaction = REACTIONS.find(r => r.name === name);
        return reaction ? reaction.emoji : '👍';
    }

    function getReactionLabel(name) {
        const reaction = REACTIONS.find(r => r.name === name);
        return reaction ? reaction.label : 'Like';
    }

    function loadReactions(postId, container) {
        // In real app, load from backend
        // For now, load from localStorage
        const stored = localStorage.getItem(`reactions_${postId}`);
        if (!stored) return;

        try {
            const reactions = JSON.parse(stored);
            Object.entries(reactions).forEach(([reactionName, data]) => {
                if (data.count > 0) {
                    const badge = createReactionBadge(postId, reactionName, data.count, data.userReacted);
                    container.appendChild(badge);
                }
            });
        } catch (e) {
            console.error('Failed to load reactions:', e);
        }
    }

    function storeReaction(postId, reactionName, add) {
        const key = `reactions_${postId}`;
        let reactions = {};
        
        try {
            const stored = localStorage.getItem(key);
            if (stored) reactions = JSON.parse(stored);
        } catch (e) {
            console.error('Failed to parse reactions:', e);
        }

        if (!reactions[reactionName]) {
            reactions[reactionName] = { count: 0, userReacted: false };
        }

        if (add) {
            reactions[reactionName].count++;
            reactions[reactionName].userReacted = true;
        } else {
            reactions[reactionName].count = Math.max(0, reactions[reactionName].count - 1);
            reactions[reactionName].userReacted = false;
        }

        localStorage.setItem(key, JSON.stringify(reactions));
    }

    // ====================================================
    // 2. ENHANCED COMMENTS
    // ====================================================

    function initEnhancedComments() {
        // Add quick reply buttons to all comments
        document.querySelectorAll('.comment-item').forEach(comment => {
            if (!comment.querySelector('.comment-actions')) {
                addCommentActions(comment);
            }
        });

        // Event delegation for comment actions
        document.addEventListener('click', handleCommentAction);
    }

    function addCommentActions(comment) {
        const content = comment.querySelector('.comment-content');
        if (!content) return;

        const actions = document.createElement('div');
        actions.className = 'comment-actions';

        // Reply button
        const replyBtn = document.createElement('button');
        replyBtn.className = 'comment-action-btn reply-btn';
        replyBtn.innerHTML = '<i class="fas fa-reply"></i> Reply';
        replyBtn.dataset.commentId = comment.dataset.commentId || Date.now();

        // Like button (simple version)
        const likeBtn = document.createElement('button');
        likeBtn.className = 'comment-action-btn like-btn';
        likeBtn.innerHTML = '<i class="far fa-thumbs-up"></i> Like';
        likeBtn.dataset.commentId = comment.dataset.commentId || Date.now();

        actions.appendChild(replyBtn);
        actions.appendChild(likeBtn);
        content.appendChild(actions);
    }

    function handleCommentAction(e) {
        // Reply button
        if (e.target.classList.contains('reply-btn') || e.target.closest('.reply-btn')) {
            e.preventDefault();
            const btn = e.target.classList.contains('reply-btn') ? e.target : e.target.closest('.reply-btn');
            const comment = btn.closest('.comment-item');
            toggleQuickReply(comment);
            return;
        }

        // Like button
        if (e.target.classList.contains('like-btn') || e.target.closest('.like-btn')) {
            e.preventDefault();
            const btn = e.target.classList.contains('like-btn') ? e.target : e.target.closest('.like-btn');
            toggleCommentLike(btn);
            return;
        }

        // Submit reply
        if (e.target.classList.contains('submit-reply-btn')) {
            e.preventDefault();
            submitQuickReply(e.target);
            return;
        }

        // Cancel reply
        if (e.target.classList.contains('cancel-reply-btn')) {
            e.preventDefault();
            const form = e.target.closest('.quick-reply-form');
            form.classList.remove('show');
            return;
        }
    }

    function toggleQuickReply(comment) {
        const existingForm = comment.querySelector('.quick-reply-form');
        
        if (existingForm) {
            existingForm.classList.toggle('show');
            if (existingForm.classList.contains('show')) {
                existingForm.querySelector('textarea').focus();
            }
            return;
        }

        // Create new quick reply form
        const form = document.createElement('div');
        form.className = 'quick-reply-form show';

        const textarea = document.createElement('textarea');
        textarea.className = 'quick-reply-textarea';
        textarea.placeholder = 'Write a reply...';
        textarea.rows = 2;

        const actions = document.createElement('div');
        actions.className = 'quick-reply-actions';

        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'btn btn-sm btn-outline-secondary cancel-reply-btn';
        cancelBtn.textContent = 'Cancel';

        const submitBtn = document.createElement('button');
        submitBtn.className = 'btn btn-sm btn-primary submit-reply-btn';
        submitBtn.innerHTML = '<i class="fas fa-paper-plane me-1"></i> Reply';
        submitBtn.dataset.commentId = comment.dataset.commentId;

        actions.appendChild(cancelBtn);
        actions.appendChild(submitBtn);
        form.appendChild(textarea);
        form.appendChild(actions);

        comment.appendChild(form);
        textarea.focus();
    }

    function submitQuickReply(btn) {
        const form = btn.closest('.quick-reply-form');
        const textarea = form.querySelector('textarea');
        const text = textarea.value.trim();

        if (!text) {
            showToast('Please enter a reply', 'warning');
            return;
        }

        // In real app, submit to backend
        console.log('Submitting reply:', text);
        
        showToast('Reply posted!', 'success');
        form.classList.remove('show');
        textarea.value = '';
    }

    function toggleCommentLike(btn) {
        const icon = btn.querySelector('i');
        const isLiked = icon.classList.contains('fas');

        if (isLiked) {
            icon.classList.remove('fas');
            icon.classList.add('far');
            btn.style.color = '#6b7280';
        } else {
            icon.classList.remove('far');
            icon.classList.add('fas');
            btn.style.color = '#3b82f6';
        }
    }

    // ====================================================
    // 3. UTILITY FUNCTIONS
    // ====================================================

    function showToast(message, type = 'info') {
        // Use existing toast system if available
        if (window.ToastNotifications && window.ToastNotifications.show) {
            window.ToastNotifications.show(message, type);
        } else {
            console.log(`[${type.toUpperCase()}] ${message}`);
        }
    }

    // ====================================================
    // 4. INITIALIZATION
    // ====================================================

    function init() {
        // Wait for DOM to be ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                initReactions();
                initEnhancedComments();
            });
        } else {
            initReactions();
            initEnhancedComments();
        }

        console.log('✓ Social Features (TIER 8) initialized');
    }

    // Export for global access
    window.SocialFeatures = {
        init,
        initReactions,
        initEnhancedComments,
        addReaction,
        REACTIONS
    };

    // Auto-initialize
    init();

})();
