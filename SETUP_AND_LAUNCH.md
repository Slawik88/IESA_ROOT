# IESA_ROOT - Setup & Launch Guide
## Latest Update: December 28, 2025

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11.0
- Virtual environment activated

### Step 1: Activate Virtual Environment
```bash
# Windows
.\venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Run Migrations
```bash
cd IESA_ROOT
python manage.py migrate
```

### Step 4: Create Superuser (if needed)
```bash
python manage.py createsuperuser
```

### Step 5: Populate Test Data
```bash
python populate_fake_data_runner.py
```

### Step 6: Run Development Server
```bash
python manage.py runserver
```

Server will be available at: **http://localhost:8000**

---

## 📋 Current Test Credentials

### Admin Access
| Username | Password | Email |
|----------|----------|-------|
| root | 20041987 | root@iesa.com |

### Test Users (all with password: `password123`)
| Username | Email | Purpose |
|----------|-------|---------|
| alice | alice@example.com | Test user |
| bob | bob@example.com | Test user |
| charlie | charlie@example.com | Test user |
| diana | diana@example.com | Test user |
| evan | evan@example.com | Test user |

**Admin Panel:** `/admin/` (requires superuser login)

---

## 📊 Database Status

### Current State
- ✅ Fresh database with test data
- ✅ All migrations applied
- ✅ 26+ test records created
- ✅ Ready for testing

### Test Data Includes
- 5 test users
- 5 partners (with logos)
- 4 association members
- 4 products
- 5 blog posts
- 3 events

---

## 🎯 Key Features Implemented

### New in This Update

#### 1. Partners Section Redesign
- ✨ Modern gradient card design
- 📄 New contract photo field
- 📱 Improved mobile responsiveness
- 🎨 Better visual hierarchy

**Access:** Home page → Partners section or `/` → scroll to partners

#### 2. Activity Levels System
- 5 achievement levels (Beginner to Legend)
- Points-based progression
- Dedicated info page
- Profile integration

**Levels:**
- 🍃 Beginner (0-50 pts)
- 🔥 Intermediate (50-200 pts)
- 🚀 Advanced (200-500 pts)
- ⭐ Expert (500-1000 pts)
- 👑 Legend (1000+ pts)

**Points:**
- Post creation: +10
- Like received: +2
- Comment made: +1

**Access:** `/auth/profile/` → View profile to see current level
**Learn more:** `/auth/activity-levels/`

#### 3. New Routes

| Route | Purpose |
|-------|---------|
| `/auth/activity-levels/` | Activity levels information page |
| `/auth/profile/` | User profile with activity level |
| `/admin/` | Admin panel |
| `/partner/{id}/` | Partner details modal |

---

## 🔧 Maintenance

### Collect Static Files (Production)
```bash
python manage.py collectstatic --noinput
```

### Run Tests
```bash
python manage.py test
```

### System Check
```bash
python manage.py check
```

### Database Backup
```bash
# Windows
copy IESA_ROOT\db.sqlite3 IESA_ROOT\db.sqlite3.backup

# macOS/Linux
cp IESA_ROOT/db.sqlite3 IESA_ROOT/db.sqlite3.backup
```

### Reset Database
```bash
rm IESA_ROOT/db.sqlite3
python manage.py migrate
python populate_fake_data_runner.py
```

---

## 📝 File Structure

```
IESA_ROOT/
├── IESA_ROOT/              # Main project folder
│   ├── manage.py           # Django management
│   ├── db.sqlite3          # Database
│   ├── populate_fake_data.py           # Fake data generator
│   ├── populate_fake_data_runner.py    # Fake data runner
│   ├── core/               # Core app (Partners, Members)
│   ├── blog/               # Blog app (Posts, Events)
│   ├── users/              # Users app (Auth, Profiles)
│   ├── products/           # Products app
│   ├── gallery/            # Gallery app
│   ├── static/             # Static files (CSS, JS, images)
│   └── templates/          # HTML templates
├── venv/                   # Virtual environment
└── requirements.txt        # Python dependencies
```

---

## 🎨 Customization

### Change Partner Logo Upload Limit
Edit: `core/models.py`
```python
logo = models.ImageField(
    upload_to='partners/',
    max_upload_size=5242880  # 5MB
)
```

### Adjust Activity Level Thresholds
Edit: `users/models.py` → `get_achievement_level()` method
```python
def get_achievement_level(self):
    score = (self.total_posts * 10) + (self.total_likes_received * 2) + (self.total_comments_made * 1)
    
    if score >= 1000:  # Adjust these values
        return 'Legend'
    # ... etc
```

### Modify Point Values
Update in:
- `users/views.py` → `activity_levels_info()` view
- `users/templates/users/activity_levels_info.html`
- Display matches: Users model calculation

---

## 🐛 Troubleshooting

### Import Error: No module named 'django'
**Solution:** Activate virtual environment
```bash
.\venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux
```

### Database Locked Error
**Solution:** Delete old database and recreate
```bash
rm IESA_ROOT/db.sqlite3
python manage.py migrate
```

### Static Files Not Loading
**Solution:** Collect static files
```bash
python manage.py collectstatic --noinput
```

### Port 8000 Already in Use
**Solution:** Use different port
```bash
python manage.py runserver 8001
```

---

## 📚 Documentation Files

- [MAJOR_UPDATE_REPORT.md](MAJOR_UPDATE_REPORT.md) - Detailed update report
- [IMPROVEMENTS_REPORT.md](IMPROVEMENTS_REPORT.md) - All improvements implemented
- [BUG_FIXES_REPORT.md](BUG_FIXES_REPORT.md) - Bug fixes applied
- [UI_UX_ANALYSIS_REPORT.md](UI_UX_ANALYSIS_REPORT.md) - UI/UX analysis
- [QUICK_START.md](QUICK_START.md) - Quick start guide
- [DEPLOYMENT_REPORT.md](DEPLOYMENT_REPORT.md) - Deployment notes

---

## 🌐 Endpoints Reference

### Public Pages
- `/` - Home page
- `/blog/` - Blog posts list
- `/blog/events/` - Events list
- `/products/` - Products catalog
- `/gallery/` - Photo gallery
- `/auth/user/{username}/` - Public profile

### Authenticated Pages
- `/auth/profile/` - My profile (requires login)
- `/auth/profile/edit/` - Edit profile (requires login)
- `/auth/activity-levels/` - Activity levels info

### Admin
- `/admin/` - Admin panel (requires staff)

### API Endpoints
- `/blog/search/` - Post search via HTMX
- `/auth/search/` - User search via HTMX
- `/partner/{id}/` - Partner details (HTMX)
- `/notifications/` - User notifications (HTMX)

---

## 🔐 Security Notes

- Always use strong passwords in production
- Change default SECRET_KEY in settings
- Use environment variables for sensitive data
- Enable DEBUG=False in production
- Configure ALLOWED_HOSTS properly
- Use HTTPS in production
- Set proper CORS headers if needed

---

## 📞 Support

For issues or questions:
1. Check troubleshooting section above
2. Review error messages in terminal
3. Check Django log files
4. Refer to main Django documentation

---

## ✅ System Status

Last Check: December 28, 2025

```
✅ Django: 5.2.9
✅ Python: 3.11.0
✅ Database: SQLite
✅ Migrations: All applied
✅ Static files: Collected
✅ All tests: Passing (0 issues)
✅ Dependencies: Installed
```

---

**Project Status:** 🚀 **READY FOR TESTING**

Setup this project with the quick start guide above and all features will be immediately available!
