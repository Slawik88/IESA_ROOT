/**
 * Skeleton Loading System
 * Provides beautiful skeleton screens while content is loading
 * Used with HTMX for smooth loading states
 */

(function() {
    'use strict';

    const SkeletonLoading = {
        /**
         * Initialize skeleton loading
         */
        init() {
            // Listen for HTMX request start
            document.addEventListener('htmx:beforeRequest', this.showSkeleton.bind(this));
            
            // Hide skeleton when content arrives
            document.addEventListener('htmx:afterSwap', this.hideSkeleton.bind(this));
            
            // Handle request errors
            document.addEventListener('htmx:responseError', this.hideSkeletonError.bind(this));
        },

        /**
         * Show skeleton placeholder
         */
        showSkeleton(event) {
            const target = event.detail.target;
            if (!target) return;

            // Create skeleton container
            const skeleton = this.createSkeleton(target);
            if (skeleton) {
                target.innerHTML = '';
                target.appendChild(skeleton);
            }
        },

        /**
         * Hide skeleton and show actual content
         */
        hideSkeleton(event) {
            // Content is already swapped by HTMX
            // Just ensure skeleton classes are removed
            const target = event.detail.target;
            if (!target) return;

            // Remove any remaining skeleton elements
            target.querySelectorAll('.skeleton, .skeleton-pulse').forEach(el => {
                el.style.display = 'none';
            });
        },

        /**
         * Hide skeleton on error
         */
        hideSkeletonError(event) {
            const target = event.detail.xhr?.response;
            if (target) {
                target.querySelectorAll('.skeleton').forEach(el => {
                    el.remove();
                });
            }
        },

        /**
         * Create appropriate skeleton based on target
         */
        createSkeleton(target) {
            const classes = target.className || '';
            
            if (classes.includes('post-list') || classes.includes('posts-container')) {
                return this.createPostListSkeleton();
            } else if (classes.includes('card-grid') || classes.includes('gallery-grid')) {
                return this.createCardGridSkeleton();
            } else if (classes.includes('user-profile')) {
                return this.createProfileSkeleton();
            } else if (classes.includes('comment-list') || classes.includes('comments')) {
                return this.createCommentListSkeleton();
            } else if (classes.includes('event-detail')) {
                return this.createEventDetailSkeleton();
            } else {
                return this.createGenericSkeleton();
            }
        },

        /**
         * Create post list skeleton
         */
        createPostListSkeleton() {
            const fragment = document.createDocumentFragment();
            for (let i = 0; i < 3; i++) {
                const post = document.createElement('div');
                post.className = 'skeleton skeleton-post mb-4';
                post.innerHTML = `
                    <div class="skeleton-item skeleton-avatar skeleton-pulse"></div>
                    <div class="skeleton-content">
                        <div class="skeleton-item skeleton-title skeleton-pulse"></div>
                        <div class="skeleton-item skeleton-text skeleton-pulse"></div>
                        <div class="skeleton-item skeleton-text skeleton-pulse" style="width: 85%"></div>
                    </div>
                    <div class="skeleton-item skeleton-image skeleton-pulse mt-3"></div>
                    <div class="skeleton-footer">
                        <div class="skeleton-item skeleton-action skeleton-pulse"></div>
                        <div class="skeleton-item skeleton-action skeleton-pulse"></div>
                    </div>
                `;
                fragment.appendChild(post);
            }
            return fragment;
        },

        /**
         * Create card/gallery grid skeleton
         */
        createCardGridSkeleton() {
            const fragment = document.createDocumentFragment();
            const grid = document.createElement('div');
            grid.className = 'skeleton skeleton-grid';
            
            for (let i = 0; i < 6; i++) {
                const card = document.createElement('div');
                card.className = 'skeleton-card';
                card.innerHTML = `
                    <div class="skeleton-item skeleton-image skeleton-pulse" style="height: 200px;"></div>
                    <div class="p-3">
                        <div class="skeleton-item skeleton-title skeleton-pulse mb-2"></div>
                        <div class="skeleton-item skeleton-text skeleton-pulse" style="width: 80%"></div>
                    </div>
                `;
                grid.appendChild(card);
            }
            
            fragment.appendChild(grid);
            return fragment;
        },

        /**
         * Create profile skeleton
         */
        createProfileSkeleton() {
            const fragment = document.createDocumentFragment();
            const profile = document.createElement('div');
            profile.className = 'skeleton skeleton-profile';
            profile.innerHTML = `
                <div class="skeleton-header">
                    <div class="skeleton-item skeleton-avatar skeleton-pulse" style="width: 150px; height: 150px; border-radius: 50%;"></div>
                    <div class="skeleton-info">
                        <div class="skeleton-item skeleton-title skeleton-pulse mb-2" style="width: 200px;"></div>
                        <div class="skeleton-item skeleton-text skeleton-pulse" style="width: 150px;"></div>
                    </div>
                </div>
                <div class="skeleton-actions">
                    <div class="skeleton-item skeleton-button skeleton-pulse"></div>
                    <div class="skeleton-item skeleton-button skeleton-pulse"></div>
                </div>
                <div class="skeleton-bio">
                    <div class="skeleton-item skeleton-text skeleton-pulse mb-2"></div>
                    <div class="skeleton-item skeleton-text skeleton-pulse"></div>
                </div>
            `;
            fragment.appendChild(profile);
            return fragment;
        },

        /**
         * Create comment list skeleton
         */
        createCommentListSkeleton() {
            const fragment = document.createDocumentFragment();
            for (let i = 0; i < 4; i++) {
                const comment = document.createElement('div');
                comment.className = 'skeleton skeleton-comment mb-3';
                comment.innerHTML = `
                    <div class="d-flex gap-2">
                        <div class="skeleton-item skeleton-avatar skeleton-pulse" style="width: 40px; height: 40px; border-radius: 50%;"></div>
                        <div class="flex-grow-1">
                            <div class="skeleton-item skeleton-text skeleton-pulse" style="width: 100px; margin-bottom: 0.5rem;"></div>
                            <div class="skeleton-item skeleton-text skeleton-pulse mb-2"></div>
                            <div class="skeleton-item skeleton-text skeleton-pulse" style="width: 90%;"></div>
                        </div>
                    </div>
                `;
                fragment.appendChild(comment);
            }
            return fragment;
        },

        /**
         * Create event detail skeleton
         */
        createEventDetailSkeleton() {
            const fragment = document.createDocumentFragment();
            const event = document.createElement('div');
            event.className = 'skeleton skeleton-event';
            event.innerHTML = `
                <div class="skeleton-item skeleton-image skeleton-pulse" style="height: 300px; margin-bottom: 2rem;"></div>
                <div class="skeleton-content">
                    <div class="skeleton-item skeleton-title skeleton-pulse mb-3" style="width: 70%;"></div>
                    <div class="skeleton-item skeleton-text skeleton-pulse mb-2"></div>
                    <div class="skeleton-item skeleton-text skeleton-pulse mb-2"></div>
                    <div class="skeleton-item skeleton-button skeleton-pulse" style="width: 150px; margin-top: 2rem;"></div>
                </div>
            `;
            fragment.appendChild(event);
            return fragment;
        },

        /**
         * Create generic skeleton
         */
        createGenericSkeleton() {
            const skeleton = document.createElement('div');
            skeleton.className = 'skeleton skeleton-generic';
            skeleton.innerHTML = `
                <div class="skeleton-item skeleton-text skeleton-pulse mb-2"></div>
                <div class="skeleton-item skeleton-text skeleton-pulse mb-2"></div>
                <div class="skeleton-item skeleton-text skeleton-pulse" style="width: 80%;"></div>
            `;
            return skeleton;
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => SkeletonLoading.init());
    } else {
        SkeletonLoading.init();
    }

    // Export for use in other scripts
    window.SkeletonLoading = SkeletonLoading;
})();
