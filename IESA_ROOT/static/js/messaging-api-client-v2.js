/**
 * Messaging API Client v2.0
 * Clean, well-documented API wrapper for messaging system
 * No silent failures - all errors logged and handled properly
 */

class MessagingAPIClient {
    constructor(csrfToken) {
        this.csrfToken = csrfToken;
        this.baseUrl = '/messages';
        this.cache = new Map();
        this.listeners = new Map();
    }

    /**
     * Make authenticated API request
     * @param {string} method - HTTP method
     * @param {string} endpoint - API endpoint path
     * @param {object} data - Request data
     * @returns {Promise<object>} - API response
     */
    async request(method, endpoint, data = null) {
        const url = `${this.baseUrl}${endpoint}`;
        const options = {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin'
        };

        if (data && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
            options.body = JSON.stringify(data);
        }

        try {
            const response = await fetch(url, options);
            
            // Parse response
            const responseData = await response.json();
            
            // Log response
            console.log(`📡 [${method}] ${endpoint}:`, {
                status: response.status,
                success: responseData.success,
                message: responseData.message
            });

            // Handle errors
            if (!response.ok) {
                const error = {
                    status: response.status,
                    message: responseData.message || 'Unknown error',
                    data: responseData.data || {}
                };

                switch (response.status) {
                    case 401:
                        console.error('❌ Unauthorized - redirecting to login');
                        window.location.href = '/auth/login/?next=' + window.location.pathname;
                        break;
                    case 403:
                        console.error('❌ Forbidden - access denied');
                        this.emit('error', {
                            title: 'Access Denied',
                            message: 'You do not have permission to perform this action'
                        });
                        break;
                    case 404:
                        console.error('❌ Not found:', error.message);
                        this.emit('error', {
                            title: 'Not Found',
                            message: error.message
                        });
                        break;
                    case 400:
                        console.error('❌ Bad request:', error.message);
                        this.emit('error', {
                            title: 'Invalid Request',
                            message: error.message
                        });
                        break;
                    case 500:
                        console.error('❌ Server error');
                        this.emit('error', {
                            title: 'Server Error',
                            message: 'An error occurred on the server. Please try again.'
                        });
                        break;
                    default:
                        console.error(`❌ HTTP ${response.status}:`, error.message);
                }

                throw error;
            }

            return responseData;

        } catch (error) {
            if (error.status) {
                throw error; // Already handled above
            }

            console.error('❌ Network error:', error);
            this.emit('error', {
                title: 'Network Error',
                message: 'Failed to connect to server. Please check your connection.'
            });
            throw error;
        }
    }

    /**
     * Get conversations list
     * @param {number} limit - Number of conversations
     * @param {number} offset - Pagination offset
     * @returns {Promise<object>}
     */
    async getConversations(limit = 20, offset = 0) {
        console.log('📥 Fetching conversations...');
        const response = await this.request('GET', `/api/conversations/?limit=${limit}&offset=${offset}`);
        if (response.success) {
            console.log(`✅ Loaded ${response.data.conversations.length} conversations`);
            return response.data;
        }
        throw new Error(response.message);
    }

    /**
     * Get messages for a conversation
     * @param {number} conversationId - Conversation ID
     * @param {number} limit - Number of messages
     * @param {number} offset - Pagination offset
     * @returns {Promise<object>}
     */
    async getMessages(conversationId, limit = 20, offset = 0) {
        console.log(`📥 Fetching messages for conversation ${conversationId}...`);
        const response = await this.request(
            'GET',
            `/api/conversations/${conversationId}/messages/?limit=${limit}&offset=${offset}`
        );
        if (response.success) {
            console.log(`✅ Loaded ${response.data.messages.length} messages`);
            return response.data;
        }
        throw new Error(response.message);
    }

    /**
     * Search users
     * @param {string} query - Search query
     * @param {number} limit - Max results
     * @returns {Promise<object>}
     */
    async searchUsers(query, limit = 10) {
        if (!query.trim()) {
            return { users: [] };
        }

        console.log(`🔍 Searching for users: "${query}"`);
        const response = await this.request(
            'GET',
            `/api/users/search/?q=${encodeURIComponent(query)}&limit=${limit}`
        );
        if (response.success) {
            console.log(`✅ Found ${response.data.users.length} users`);
            return response.data;
        }
        throw new Error(response.message);
    }

    /**
     * Send a message
     * @param {number} conversationId - Conversation ID
     * @param {string} text - Message text
     * @returns {Promise<object>}
     */
    async sendMessage(conversationId, text) {
        if (!text.trim()) {
            throw new Error('Message text cannot be empty');
        }

        console.log(`📤 Sending message to conversation ${conversationId}...`);
        const response = await this.request(
            'POST',
            `/api/conversations/${conversationId}/send/`,
            { text: text.trim() }
        );
        if (response.success) {
            console.log('✅ Message sent');
            this.emit('message-sent', response.data.message);
            return response.data.message;
        }
        throw new Error(response.message);
    }

    /**
     * Edit a message
     * @param {number} messageId - Message ID
     * @param {string} newText - New message text
     * @returns {Promise<object>}
     */
    async editMessage(messageId, newText) {
        if (!newText.trim()) {
            throw new Error('Message text cannot be empty');
        }

        console.log(`✏️ Editing message ${messageId}...`);
        const response = await this.request(
            'POST',
            `/api/messages/${messageId}/edit/`,
            { text: newText.trim() }
        );
        if (response.success) {
            console.log('✅ Message edited');
            this.emit('message-edited', { messageId });
            return response.data;
        }
        throw new Error(response.message);
    }

    /**
     * Delete a message
     * @param {number} messageId - Message ID
     * @param {boolean} forEveryone - Delete for all participants
     * @returns {Promise<object>}
     */
    async deleteMessage(messageId, forEveryone = false) {
        console.log(`🗑️ Deleting message ${messageId}...`);
        const response = await this.request(
            'POST',
            `/api/messages/${messageId}/delete/`,
            { for_everyone: forEveryone }
        );
        if (response.success) {
            console.log('✅ Message deleted');
            this.emit('message-deleted', { messageId });
            return response.data;
        }
        throw new Error(response.message);
    }

    /**
     * Mark message as read
     * @param {number} messageId - Message ID
     * @returns {Promise<object>}
     */
    async markRead(messageId) {
        const response = await this.request(
            'POST',
            `/api/messages/${messageId}/read/`
        );
        return response.data;
    }

    /**
     * Create 1-to-1 conversation
     * @param {number} participantId - Other participant ID
     * @returns {Promise<object>}
     */
    async createConversation(participantId) {
        console.log(`💬 Creating conversation with user ${participantId}...`);
        const response = await this.request(
            'POST',
            '/api/conversations/create/one-to-one/',
            { participant_id: participantId }
        );
        if (response.success) {
            console.log(`✅ Conversation created/found: ${response.data.conversation_id}`);
            this.emit('conversation-created', response.data);
            return response.data;
        }
        throw new Error(response.message);
    }

    /**
     * Create group conversation
     * @param {string} name - Group name
     * @param {array} participantIds - List of participant IDs
     * @returns {Promise<object>}
     */
    async createGroup(name, participantIds = []) {
        console.log(`👥 Creating group: "${name}"...`);
        const response = await this.request(
            'POST',
            '/api/conversations/create/group/',
            {
                name: name,
                participant_ids: participantIds
            }
        );
        if (response.success) {
            console.log(`✅ Group created: ${response.data.conversation_id}`);
            this.emit('group-created', response.data);
            return response.data;
        }
        throw new Error(response.message);
    }

    /**
     * Event listener system
     */
    on(event, callback) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, []);
        }
        this.listeners.get(event).push(callback);
    }

    off(event, callback) {
        if (this.listeners.has(event)) {
            const callbacks = this.listeners.get(event);
            const index = callbacks.indexOf(callback);
            if (index > -1) {
                callbacks.splice(index, 1);
            }
        }
    }

    emit(event, data) {
        console.log(`📢 Event: ${event}`, data);
        if (this.listeners.has(event)) {
            this.listeners.get(event).forEach(callback => {
                try {
                    callback(data);
                } catch (error) {
                    console.error(`Error in ${event} listener:`, error);
                }
            });
        }
    }
}

// Export for use in other modules
window.MessagingAPIClient = MessagingAPIClient;
