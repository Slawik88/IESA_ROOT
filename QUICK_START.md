# Quick Start Guide - IESA Project New Features

## 🎉 Welcome to the Enhanced IESA Platform!

---

## 🚀 Getting Started

### 1. Run Migrations (if not done)
```bash
cd IESA_ROOT
..\venv\Scripts\python.exe manage.py migrate
```

### 2. Update User Statistics
```bash
..\venv\Scripts\python.exe manage.py update_user_stats
```

### 3. Start Development Server
```bash
..\venv\Scripts\python.exe manage.py runserver
```

---

## 📋 New Features Overview

### 1. 🔔 Notification System

**Access:** Click the bell icon 🔔 in the top navigation bar

**Features:**
- Real-time notification counter (red badge shows unread count)
- Notifications for: post approval/rejection, new comments, likes, followers, event reminders
- Mark individual or all notifications as read
- Paginated list (20 per page)

**URL:** `http://localhost:8000/notifications/`

**How to test:**
1. Create a post (it will trigger notifications when approved)
2. Like someone's post
3. Comment on a post
4. Check your notifications page

---

### 2. 📊 User Statistics & Achievements

**Where to see:** Visit any user profile

**Displays:**
- Total posts published
- Total likes received on posts
- Total comments made
- Achievement level (Beginner → Legend)

**Achievement Levels:**
- 🥉 Beginner: 0-49 points
- 🥈 Intermediate: 50-199 points
- 🥇 Advanced: 200-499 points
- 🏆 Expert: 500-999 points
- 👑 Legend: 1000+ points

**Scoring Formula:**
- Posts: 10 points each
- Likes received: 2 points each
- Comments made: 1 point each

**Manual Update:**
```bash
..\venv\Scripts\python.exe manage.py update_user_stats
```

---

### 3. 📅 Enhanced Events

**Access:** `Community → Events` in navigation

**New Capabilities:**
- Event status tracking (Upcoming, Ongoing, Completed, Cancelled)
- Registration system with capacity limits
- Registration deadlines
- Participant tracking
- Available spots counter

**Admin Features:**
- View all registrations in admin panel
- Change registration status
- Track attendance
- Export registration data

**Event Properties:**
- `is_registration_open` - Checks if registration is still available
- `is_full` - Checks if event reached max capacity
- `available_spots` - Number of remaining spots

---

### 4. 🔍 Improved Search

**Access:** Search icon 🔍 in navigation bar

**Enhancements:**
- Relevance-based ranking
- Exact username matches appear first
- Title matches prioritized over content matches
- Search across posts, users, events, and partners simultaneously
- Real-time HTMX search results (400ms delay)

**Search Tips:**
- Use exact usernames for precise user search
- Search post titles for better accuracy
- Try event names to find upcoming events
- Partner names return organization results

---

### 5. ✏️ Rich Text Editor (CKEditor 5)

**Access:** Create or edit a blog post

**New Features:**
- Tables with customization
- Text color picker
- Background color picker
- Font family selection
- Font size adjustment
- Advanced alignment options
- Media embedding
- Code blocks
- Horizontal rules
- Special characters

**Toolbar includes:**
- Bold, Italic, Underline, Strikethrough
- Headings (H1-H6)
- Lists (ordered, unordered)
- Blockquotes
- Links and images
- Tables
- Undo/Redo

---

### 6. 🔐 Enhanced Security

**Password Requirements (new registrations):**
- Minimum 8 characters
- At least 1 uppercase letter
- At least 1 special character (!@#$%^&*(),.?":{}|<>)

**Rate Limiting:**
- Login: 20 attempts per hour
- Registration: 10 attempts per hour
- Post creation: 30 posts per hour
- Comments: 60 comments per hour

**CSRF Protection:**
- Configured for production domain (iesasport.ch)
- Works with localhost for development

---

### 7. 📸 Image Optimization

**Automatic Processing:**
- Avatars auto-resized to 300×300
- Blog preview images resized to 800×600
- Event images resized to 1200×800
- HEIF format support (iPhone images)
- Automatic thumbnail generation

**File Size Benefits:**
- Up to 70% reduction in file sizes
- Faster page loading
- Reduced bandwidth usage

---

### 8. 📊 Logging System

**Log Location:** `IESA_ROOT/logs/django.log`

**What's Logged:**
- Application errors
- Database queries (DEBUG mode)
- User authentication events
- Request/response cycles
- Python warnings

**Log Rotation:**
- Max file size: 10MB
- Backup files: 5 rotations
- Automatic cleanup

**View Logs:**
```bash
# View last 50 lines
Get-Content logs\django.log -Tail 50

# Follow logs in real-time
Get-Content logs\django.log -Wait -Tail 20
```

---

## 🎨 Design Improvements

### User Profile
- Statistics cards with color gradients
- Achievement badge with emoji
- Responsive grid layout
- Social media links with icons

### Notifications
- Color-coded notification types
- Icon-based categories
- Hover effects
- Unread indicators

### Events
- Event date chips
- Status badges
- Capacity indicators
- Registration buttons

---

## 🌍 Language Support

**Current Language:** English (en-us)

**Localized Components:**
- All model field names
- Admin interface labels
- Form labels
- Status choices
- Achievement levels

---

## 🛠️ Admin Panel Features

### Events Management
**URL:** `/admin/blog/event/`

**Features:**
- View registration count
- List registrations inline
- Filter by status
- Search by title/location
- Export registration data

### Notifications Management
**URL:** `/admin/notifications/notification/`

**Features:**
- Filter by type, read status
- Search by user
- Bulk actions
- View notification content

### User Statistics
**URL:** `/admin/users/user/`

**Features:**
- View user statistics in list
- Filter by verification status
- Search by username/email
- View achievement levels

---

## 📖 Common Tasks

### Create a Post with Rich Formatting
1. Go to Community → Create Post
2. Use CKEditor toolbar for formatting
3. Add images, tables, colors
4. Submit for moderation

### Check Notifications
1. Click bell icon in navbar
2. View unread count
3. Click notification to view details
4. Mark as read or mark all read

### Register for Event
1. Browse Events
2. Click event details
3. Check available spots
4. Click "Register" button
5. Confirm registration

### Update Your Statistics
1. Admin runs: `python manage.py update_user_stats`
2. Or statistics update automatically when:
   - You publish a post
   - Someone likes your post
   - You make a comment

### View Logs
```bash
# Windows PowerShell
cd IESA_ROOT
Get-Content logs\django.log -Tail 100

# Search for errors
Select-String -Path logs\django.log -Pattern "ERROR"
```

---

## 🐛 Troubleshooting

### Notifications Not Appearing
1. Check if signals are enabled in `notifications/apps.py`
2. Verify context processor in settings.py
3. Create test notification in admin panel

### Statistics Not Updating
1. Run: `python manage.py update_user_stats`
2. Check database for statistics fields
3. Verify migrations applied

### CKEditor Not Loading
1. Clear browser cache
2. Check static files: `python manage.py collectstatic`
3. Verify CKEDITOR_5_CONFIGS in settings.py

### Rate Limiting Issues
1. Check IP address in request
2. Wait for rate limit window to reset
3. Adjust limits in `users/ratelimit_utils.py`

---

## 📚 Technical Documentation

### Dependencies
```
Django 5.2.9
django-ckeditor-5 0.2.18
django-ratelimit 4.2.0
django-imagekit 5.0.1
pillow-heif 0.22.0
django-htmx 1.21.0
```

### Database Models
- **EventRegistration:** Event signup tracking
- **Notification:** User notification system
- **User (enhanced):** Statistics fields

### New URL Patterns
```
/notifications/ - Notification list
/notifications/<id>/read/ - Mark notification read
/notifications/mark-all-read/ - Mark all read
```

### Context Processors
- `notifications.context_processors.unread_notifications` - Badge counter

---

## 🎯 Best Practices

1. **Post Creation:**
   - Use rich formatting sparingly
   - Add preview images for better engagement
   - Write descriptive titles for better search ranking

2. **Event Management:**
   - Set realistic participant limits
   - Configure registration deadlines
   - Update status as event progresses

3. **User Engagement:**
   - Check notifications regularly
   - Interact with posts (likes, comments)
   - Build achievement levels through activity

4. **Security:**
   - Use strong passwords (follows new validation)
   - Don't share admin credentials
   - Monitor logs for suspicious activity

---

## 📞 Support

For issues or questions:
1. Check `IMPROVEMENTS_REPORT.md` for detailed implementation info
2. Review `logs/django.log` for error messages
3. Consult Django documentation: https://docs.djangoproject.com/

---

**Version:** 1.0  
**Last Updated:** 2024  
**Status:** Production Ready ✅
