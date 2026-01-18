/**
 * Messaging UI v2.0
 * Handles inbox and conversation pages using MessagingAPIClient.
 */

class MessagingUIV2 {
    constructor({ apiClient }) {
        this.apiClient = apiClient;
        this.conversations = [];
        this.filteredConversations = [];
        this.selectedConversationId = null;
        this.currentMessages = [];
        this.elements = {};
        this.searchDebounce = null;
    }

    init(options = {}) {
        this.cacheDom();
        this.bindStaticHandlers();

        const presetConversationId = options.conversationId || this.getConversationIdFromDom();
        if (presetConversationId) {
            this.selectedConversationId = presetConversationId;
        }

        if (this.elements.convList) {
            this.loadConversations();
        } else if (this.selectedConversationId) {
            this.enableComposer(this.selectedConversationId);
            this.loadMessages(this.selectedConversationId);
        }
    }

    cacheDom() {
        this.elements = {
            convList: document.getElementById('convList'),
            convSearchInput: document.getElementById('convSearchInput'),
            convEmpty: document.getElementById('convEmpty'),
            convLoading: document.getElementById('convLoading'),
            convError: document.getElementById('convError'),
            convTitle: document.getElementById('convTitle'),
            convSubtitle: document.getElementById('convSubtitle'),
            reloadConvBtn: document.getElementById('reloadConvBtn'),
            messagesContainer: document.getElementById('messagesContainer'),
            messagesEmpty: document.getElementById('messagesEmpty'),
            messagesError: document.getElementById('messagesError'),
            sendForm: document.getElementById('sendForm'),
            messageInput: document.getElementById('messageInput'),
            sendBtn: document.getElementById('sendBtn'),
            newChatBtn: document.getElementById('newChatBtnPage'),
            conversationPage: document.getElementById('conversationPage')
        };
    }

    bindStaticHandlers() {
        if (this.elements.sendForm) {
            this.elements.sendForm.addEventListener('submit', (e) => {
                e.preventDefault();
                if (!this.selectedConversationId) return;
                this.sendMessage(this.selectedConversationId);
            });
        }

        if (this.elements.reloadConvBtn) {
            this.elements.reloadConvBtn.addEventListener('click', () => {
                if (!this.selectedConversationId) return;
                this.loadMessages(this.selectedConversationId);
            });
        }

        if (this.elements.convSearchInput) {
            this.elements.convSearchInput.addEventListener('input', (e) => {
                const query = e.target.value.trim().toLowerCase();
                clearTimeout(this.searchDebounce);
                this.searchDebounce = setTimeout(() => {
                    this.applyConversationFilter(query);
                }, 200);
            });
        }

        if (this.elements.newChatBtn) {
            this.elements.newChatBtn.addEventListener('click', () => {
                const modalEl = document.getElementById('newChatModalV2');
                if (modalEl && window.bootstrap) {
                    const modalInstance = bootstrap.Modal.getOrCreateInstance(modalEl);
                    modalInstance.show();
                }
            });
        }

        if (this.elements.messagesContainer) {
            this.elements.messagesContainer.addEventListener('click', (e) => {
                const btn = e.target.closest('[data-msg-action]');
                if (!btn) return;
                const messageId = parseInt(btn.dataset.messageId, 10);
                const action = btn.dataset.msgAction;
                if (!messageId || !action) return;
                if (action === 'edit') {
                    this.handleEditMessage(messageId);
                } else if (action === 'delete') {
                    this.handleDeleteMessage(messageId);
                }
            });
        }
    }

    getConversationIdFromDom() {
        if (this.elements.conversationPage?.dataset.conversationId) {
            return parseInt(this.elements.conversationPage.dataset.conversationId, 10);
        }
        const formConvId = this.elements.sendForm?.dataset.conversationId;
        return formConvId ? parseInt(formConvId, 10) : null;
    }

    async loadConversations() {
        if (!this.elements.convList) return;
        this.setConversationState({ loading: true, error: null });
        try {
            const data = await this.apiClient.getConversations(50, 0);
            this.conversations = data.conversations || [];
            this.filteredConversations = this.conversations;
            this.renderConversations();

            if (!this.selectedConversationId && this.conversations.length > 0) {
                this.selectConversation(this.conversations[0].id);
            } else if (this.selectedConversationId) {
                this.selectConversation(this.selectedConversationId, false);
            }
        } catch (error) {
            this.setConversationState({ error: error.message || 'Failed to load conversations' });
        } finally {
            this.setConversationState({ loading: false });
        }
    }

    setConversationState({ loading = false, error = null }) {
        if (this.elements.convLoading) {
            this.elements.convLoading.classList.toggle('d-none', !loading);
        }
        if (this.elements.convError) {
            if (error) {
                this.elements.convError.textContent = error;
                this.elements.convError.classList.remove('d-none');
            } else {
                this.elements.convError.classList.add('d-none');
                this.elements.convError.textContent = '';
            }
        }
        if (this.elements.convList) {
            this.elements.convList.classList.toggle('opacity-50', loading);
        }
    }

    renderConversations() {
        if (!this.elements.convList) return;
        if (this.filteredConversations.length === 0) {
            this.elements.convList.innerHTML = '';
            this.elements.convEmpty?.classList.remove('d-none');
            return;
        }
        this.elements.convEmpty?.classList.add('d-none');

        const html = this.filteredConversations.map((conv) => {
            const title = conv.is_group ? (conv.group_name || `Group ${conv.id}`) : (conv.other_participant?.name || `Conversation ${conv.id}`);
            const lastText = conv.last_message?.text || 'No messages yet';
            const preview = lastText.length > 80 ? `${lastText.slice(0, 80)}...` : lastText;
            const activeClass = conv.id === this.selectedConversationId ? 'bg-light border-primary' : '';
            const unread = conv.unread_count && conv.unread_count > 0 ? `<span class="badge bg-primary ms-2">${conv.unread_count}</span>` : '';
            return `
                <button class="w-100 text-start border-0 bg-white conversation-row ${activeClass}" data-conversation-id="${conv.id}" style="padding: 12px 14px;">
                    <div class="d-flex justify-content-between align-items-start">
                        <div class="flex-grow-1">
                            <div class="fw-semibold">${this.escapeHtml(title)}</div>
                            <div class="text-muted small">${this.escapeHtml(preview)}</div>
                        </div>
                        ${unread}
                    </div>
                </button>
            `;
        }).join('');

        this.elements.convList.innerHTML = html;
        this.elements.convList.querySelectorAll('[data-conversation-id]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const id = parseInt(btn.dataset.conversationId, 10);
                this.selectConversation(id);
            });
        });
    }

    applyConversationFilter(query) {
        if (!query) {
            this.filteredConversations = this.conversations;
        } else {
            this.filteredConversations = this.conversations.filter((conv) => {
                const title = conv.is_group ? conv.group_name : conv.other_participant?.name;
                return title?.toLowerCase().includes(query);
            });
        }
        this.renderConversations();
    }

    selectConversation(conversationId, loadMessages = true) {
        this.selectedConversationId = conversationId;
        this.enableComposer(conversationId);
        this.currentMessages = [];
        this.clearUnread(conversationId);
        this.highlightActiveConversation();
        const conversation = this.conversations.find((c) => c.id === conversationId);
        if (conversation) {
            this.updateHeader(conversation);
        } else {
            this.updateHeader({ id: conversationId, group_name: `Conversation ${conversationId}`, is_group: true });
        }
        if (loadMessages) {
            this.loadMessages(conversationId);
        }
    }

    enableComposer(conversationId) {
        if (this.elements.sendForm) {
            this.elements.sendForm.dataset.conversationId = conversationId;
        }
        if (this.elements.messageInput) {
            this.elements.messageInput.disabled = false;
        }
        if (this.elements.sendBtn) {
            this.elements.sendBtn.disabled = false;
        }
        if (this.elements.reloadConvBtn) {
            this.elements.reloadConvBtn.disabled = false;
        }
    }

    highlightActiveConversation() {
        if (!this.elements.convList) return;
        this.elements.convList.querySelectorAll('[data-conversation-id]').forEach((btn) => {
            btn.classList.toggle('bg-light', parseInt(btn.dataset.conversationId, 10) === this.selectedConversationId);
            btn.classList.toggle('border-primary', parseInt(btn.dataset.conversationId, 10) === this.selectedConversationId);
        });
    }

    updateHeader(conversation) {
        if (this.elements.convTitle) {
            const name = conversation.is_group ? (conversation.group_name || `Group ${conversation.id}`) : (conversation.other_participant?.name || `Conversation ${conversation.id}`);
            this.elements.convTitle.textContent = name;
        }
        if (this.elements.convSubtitle) {
            const members = conversation.participants?.map((p) => p.name || p.username).join(', ');
            this.elements.convSubtitle.textContent = members || 'Messages will appear here';
        }
    }

    async loadMessages(conversationId) {
        if (!conversationId) return;
        this.setMessagesState({ loading: true, error: null });
        try {
            const data = await this.apiClient.getMessages(conversationId, 50, 0);
            this.currentMessages = data.messages || [];
            this.renderMessages(this.currentMessages);
        } catch (error) {
            this.setMessagesState({ error: error.message || 'Failed to load messages' });
        } finally {
            this.setMessagesState({ loading: false });
        }
    }

    setMessagesState({ loading = false, error = null }) {
        if (this.elements.messagesContainer && loading) {
            this.elements.messagesContainer.innerHTML = '<div class="text-center text-muted py-3">Loading messages...</div>';
        }
        if (this.elements.messagesError) {
            if (error) {
                this.elements.messagesError.textContent = error;
                this.elements.messagesError.classList.remove('d-none');
            } else {
                this.elements.messagesError.classList.add('d-none');
                this.elements.messagesError.textContent = '';
            }
        }
        if (this.elements.messagesEmpty) {
            if (loading) {
                this.elements.messagesEmpty.classList.add('d-none');
            }
        }
    }

    renderMessages(messages) {
        if (!this.elements.messagesContainer) return;
        if (!messages || messages.length === 0) {
            this.elements.messagesContainer.innerHTML = '';
            this.elements.messagesEmpty?.classList.remove('d-none');
            return;
        }
        this.elements.messagesEmpty?.classList.add('d-none');
        const fragments = document.createDocumentFragment();
        messages.slice().reverse().forEach((msg) => {
            const bubble = document.createElement('div');
            bubble.className = `d-flex ${msg.is_own_message ? 'justify-content-end' : 'justify-content-start'} mb-2`;

            const body = document.createElement('div');
            body.className = `p-2 rounded ${msg.is_own_message ? 'bg-primary text-white' : 'bg-light border'}`;
            const text = document.createElement('div');
            text.className = 'small';
            text.textContent = msg.text;

            const meta = document.createElement('div');
            meta.className = msg.is_own_message ? 'text-white-50 small mt-1' : 'text-muted small mt-1';
            const senderName = msg.is_own_message ? 'You' : msg.sender?.username || 'User';
            const time = this.formatTimestamp(msg.created_at);
            meta.textContent = `${senderName} • ${time}${msg.edited_at ? ' • edited' : ''}`;

            body.appendChild(text);
            body.appendChild(meta);
            if (msg.is_own_message) {
                const actions = document.createElement('div');
                actions.className = 'd-flex gap-3 mt-1';

                const editBtn = document.createElement('button');
                editBtn.type = 'button';
                editBtn.className = 'btn btn-link btn-sm p-0 text-decoration-none text-white';
                editBtn.dataset.msgAction = 'edit';
                editBtn.dataset.messageId = msg.id;
                editBtn.textContent = 'Edit';

                const deleteBtn = document.createElement('button');
                deleteBtn.type = 'button';
                deleteBtn.className = 'btn btn-link btn-sm p-0 text-decoration-none text-white';
                deleteBtn.dataset.msgAction = 'delete';
                deleteBtn.dataset.messageId = msg.id;
                deleteBtn.textContent = 'Delete';

                actions.appendChild(editBtn);
                actions.appendChild(deleteBtn);
                body.appendChild(actions);
            }
            bubble.appendChild(body);
            fragments.appendChild(bubble);
        });

        this.elements.messagesContainer.innerHTML = '';
        this.elements.messagesContainer.appendChild(fragments);
        this.elements.messagesContainer.scrollTop = this.elements.messagesContainer.scrollHeight;
    }

    async sendMessage(conversationId) {
        if (!this.elements.messageInput) return;
        const text = this.elements.messageInput.value.trim();
        if (!text) return;
        this.setComposerBusy(true);
        try {
            const message = await this.apiClient.sendMessage(conversationId, text);
            if (this.elements.messageInput) {
                this.elements.messageInput.value = '';
            }
            this.currentMessages = [
                ...this.currentMessages,
                {
                    id: message.id,
                    text: message.text,
                    sender: message.sender,
                    created_at: message.created_at,
                    edited_at: message.edited_at,
                    is_pinned: false,
                    is_own_message: true
                }
            ];
            this.renderMessages(this.currentMessages);
        } catch (error) {
            if (this.elements.messagesError) {
                this.elements.messagesError.textContent = error.message || 'Failed to send message';
                this.elements.messagesError.classList.remove('d-none');
            }
        } finally {
            this.setComposerBusy(false);
        }
    }

    async handleEditMessage(messageId) {
        const msg = this.currentMessages.find((m) => m.id === messageId);
        if (!msg) return;
        const newText = window.prompt('Edit message', msg.text);
        if (newText === null) return;
        const trimmed = newText.trim();
        if (!trimmed) {
            alert('Message text cannot be empty');
            return;
        }
        try {
            await this.apiClient.editMessage(messageId, trimmed);
            msg.text = trimmed;
            msg.edited_at = new Date().toISOString();
            this.renderMessages(this.currentMessages);
        } catch (error) {
            this.showMessagesError(error.message || 'Failed to edit message');
        }
    }

    async handleDeleteMessage(messageId) {
        const msg = this.currentMessages.find((m) => m.id === messageId);
        if (!msg) return;
        const confirmed = window.confirm('Delete this message?');
        if (!confirmed) return;
        try {
            await this.apiClient.deleteMessage(messageId, true);
            this.currentMessages = this.currentMessages.filter((m) => m.id !== messageId);
            this.renderMessages(this.currentMessages);
        } catch (error) {
            this.showMessagesError(error.message || 'Failed to delete message');
        }
    }

    showMessagesError(message) {
        if (this.elements.messagesError) {
            this.elements.messagesError.textContent = message;
            this.elements.messagesError.classList.remove('d-none');
        }
    }

    clearUnread(conversationId) {
        const conv = this.conversations.find((c) => c.id === conversationId);
        if (conv && conv.unread_count) {
            conv.unread_count = 0;
            this.renderConversations();
        }
    }

    setComposerBusy(busy) {
        if (this.elements.messageInput) {
            this.elements.messageInput.disabled = busy;
        }
        if (this.elements.sendBtn) {
            this.elements.sendBtn.disabled = busy;
        }
    }

    escapeHtml(value) {
        const div = document.createElement('div');
        div.textContent = value ?? '';
        return div.innerHTML;
    }

    formatTimestamp(ts) {
        try {
            const d = new Date(ts);
            return d.toLocaleString([], { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' });
        } catch (e) {
            return '';
        }
    }
}

window.MessagingUIV2 = MessagingUIV2;
