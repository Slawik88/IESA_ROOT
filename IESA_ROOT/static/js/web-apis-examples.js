/**
 * TIER 7: Web APIs Usage Examples
 * Geolocation, Camera, Microphone, Clipboard, Share, Device Motion
 */

/* ============================================================
   1. GEOLOCATION - GET USER LOCATION
   ============================================================ */

GEOLOCATION_EXAMPLE = `
// Initialize geolocation manager
const geoManager = new GeoLocationManager({
  enableHighAccuracy: true,
  timeout: 10000,
  maximumAge: 0
});

// Get current position
async function getUserLocation() {
  try {
    const position = await geoManager.getCurrentPosition();
    console.log('User location:', position.coords);
    
    const coords = geoManager.getCoordinates();
    console.log(coords);
    // { latitude, longitude, accuracy, altitude, heading, speed, timestamp }
    
    // Display on map or use for location-based features
    displayUserOnMap(coords.latitude, coords.longitude);
  } catch (error) {
    console.error('Failed to get location:', error);
    // Handle permission denied, timeout, etc
  }
}

// Watch user position (continuous tracking)
geoManager.watchPosition((position) => {
  const coords = geoManager.getCoordinates();
  updateUserMarker(coords.latitude, coords.longitude);
  console.log('User moved to:', coords);
});

// Calculate distance between two points
const distance = geoManager.calculateDistance(
  55.7558,  // Moscow lat
  37.6173,  // Moscow lon
  51.5074,  // London lat
  -0.1278   // London lon
);
console.log('Distance:', distance, 'km');

// Stop tracking
// geoManager.stopWatching();
`;

/* ============================================================
   2. CAMERA - CAPTURE PHOTOS/VIDEO
   ============================================================ */

CAMERA_EXAMPLE = `
<!-- HTML -->
<div class="camera-container">
  <video id="camera-video" playsinline autoplay></video>
  <button id="capture-photo">📷 Фото</button>
  <button id="switch-camera">🔄 Переключить камеру</button>
  <button id="record-video">📹 Запись видео</button>
  <img id="captured-image" style="display:none;">
</div>

<script>
  const camera = new CameraCapture('#camera-video', {
    width: { ideal: 1280 },
    height: { ideal: 720 },
    facingMode: 'user'
  });

  // Start camera
  async function startCamera() {
    try {
      await camera.startCamera();
      console.log('✅ Camera started');
    } catch (error) {
      console.error('❌ Camera error:', error);
      alert('Не удалось получить доступ к камере');
    }
  }

  // Capture photo
  document.getElementById('capture-photo').addEventListener('click', () => {
    const photoDataUrl = camera.capturePhoto();
    
    // Display photo
    const img = document.getElementById('captured-image');
    img.src = photoDataUrl;
    img.style.display = 'block';
    
    // Upload to server
    fetch('/api/upload-photo/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body: JSON.stringify({
        image: photoDataUrl
      })
    });
  });

  // Switch camera (front/back)
  document.getElementById('switch-camera').addEventListener('click', async () => {
    await camera.switchCamera();
  });

  // Record video
  document.getElementById('record-video').addEventListener('click', async () => {
    const blob = await camera.recordVideo(10000); // 10 seconds
    
    const formData = new FormData();
    formData.append('video', blob, 'video.webm');
    
    fetch('/api/upload-video/', {
      method: 'POST',
      body: formData,
      headers: {
        'X-CSRFToken': getCsrfToken()
      }
    });
  });

  startCamera();

  // Cleanup on page leave
  window.addEventListener('beforeunload', () => {
    camera.stopCamera();
  });
</script>
`;

/* ============================================================
   3. CLIPBOARD - COPY/PASTE
   ============================================================ */

CLIPBOARD_EXAMPLE = `
<!-- HTML -->
<div class="clipboard-demo">
  <button class="copy-btn" data-copy="Hello, World!">📋 Копировать текст</button>
  
  <div class="share-code" id="share-link">
    https://example.com/invite/ABC123
  </div>
  <button class="copy-btn" onclick="copyShareLink()">Копировать ссылку</button>
  
  <button onclick="pasteFromClipboard()">📌 Вставить из буфера</button>
</div>

<script>
  // Copy text to clipboard
  document.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const text = btn.dataset.copy || btn.nextElementSibling?.textContent;
      const success = await ClipboardManager.copyText(text);
      
      if (success) {
        // Show success feedback
        btn.textContent = '✅ Скопировано!';
        setTimeout(() => {
          btn.textContent = '📋 Копировать';
        }, 2000);
      }
    });
  });

  async function copyShareLink() {
    const link = document.getElementById('share-link').textContent;
    await ClipboardManager.copyText(link);
  }

  // Paste from clipboard
  async function pasteFromClipboard() {
    try {
      const text = await ClipboardManager.readText();
      console.log('Pasted:', text);
      // Use pasted text
    } catch (error) {
      console.error('Failed to read clipboard');
    }
  }

  // Copy image to clipboard
  async function copyImageToClipboard(imageUrl) {
    const success = await ClipboardManager.copyImage(imageUrl);
    if (success) {
      console.log('Image copied!');
    }
  }
</script>
`;

/* ============================================================
   4. SHARE API - NATIVE SHARE DIALOG
   ============================================================ */

SHARE_EXAMPLE = `
<!-- HTML -->
<div class="share-buttons">
  <button id="share-post-btn" class="btn btn-primary">
    <i class="fas fa-share-alt"></i> Поделиться
  </button>
</div>

<script>
  // Check if share is available
  if (ShareManager.canShare()) {
    document.getElementById('share-post-btn').style.display = 'block';
  }

  // Share post
  document.getElementById('share-post-btn').addEventListener('click', async () => {
    const postTitle = document.querySelector('h1').textContent;
    const postUrl = window.location.href;
    const postImage = document.querySelector('img.post-image')?.src;

    const success = await ShareManager.share({
      title: postTitle,
      text: 'Посмотри этот интересный пост!',
      url: postUrl,
      image: postImage // iOS only
    });

    if (success) {
      console.log('Post shared!');
      // Track share analytics
      trackEvent('post_shared', { postId: getPostId() });
    }
  });

  // Share multiple files
  async function shareFiles(files) {
    const success = await ShareManager.shareFile(files, 'Share Media');
    if (success) {
      console.log('Files shared!');
    }
  }

  // Share to specific app (fallback)
  function shareViaFallback(text, url) {
    const whatsappUrl = `https://wa.me/?text=${encodeURIComponent(text + ' ' + url)}`;
    const twitterUrl = `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${url}`;
    
    // Create share popup
    const shareModal = document.createElement('div');
    shareModal.innerHTML = \`
      <a href="\${whatsappUrl}" target="_blank">📱 WhatsApp</a>
      <a href="\${twitterUrl}" target="_blank">🐦 Twitter</a>
    \`;
  }
</script>
`;

/* ============================================================
   5. DEVICE MOTION - DETECT SHAKE & TILT
   ============================================================ */

DEVICE_MOTION_EXAMPLE = `
<script>
  const motionDetector = new DeviceMotionDetector({
    shakeSensitivity: 20,
    tiltThreshold: 30
  });

  // Request permission first (iOS)
  const permission = await DeviceMotionDetector.requestPermission();

  // Detect shake gesture
  motionDetector.startShakeDetection((event) => {
    console.log('🤖 Device shaken!', event.acceleration);
    
    // Trigger action on shake
    // Shuffle posts
    reloadFeed();
    
    // Show toast
    new Toast('success', 'Обновлено!');
  });

  // Detect tilt/orientation
  motionDetector.startTiltDetection((event) => {
    console.log('Tilt:', event);
    
    if (event.isPortrait) {
      console.log('Device is portrait');
    } else {
      console.log('Device is tilted');
    }
    
    // Use for parallax effects, tilting cards, etc
    applyTiltEffect(event.gamma, event.beta);
  });
</script>
`;

/* ============================================================
   6. FULLSCREEN - REQUEST FULLSCREEN MODE
   ============================================================ */

FULLSCREEN_EXAMPLE = `
<!-- HTML -->
<div id="video-player" class="video-container">
  <video id="my-video" controls>
    <source src="/video.mp4" type="video/mp4">
  </video>
  <button id="fullscreen-btn">
    <i class="fas fa-expand"></i> На весь экран
  </button>
</div>

<script>
  document.getElementById('fullscreen-btn').addEventListener('click', async () => {
    const videoPlayer = document.getElementById('video-player');
    const success = await ScreenManager.requestFullscreen(videoPlayer);
    if (!success) {
      console.error('Fullscreen request failed');
    }
  });

  // Exit fullscreen with ESC key or button
  document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement) {
      console.log('Exited fullscreen');
    }
  });
</script>
`;

/* ============================================================
   7. SCREEN WAKE LOCK - KEEP SCREEN ON
   ============================================================ */

SCREEN_WAKE_LOCK_EXAMPLE = `
<script>
  // Request wake lock (for video playback, fitness apps, etc)
  async function keepScreenOn() {
    try {
      const wakeLock = await ScreenManager.requestScreenWakeLock();
      console.log('✅ Screen will stay on');
      
      // Release wake lock when done
      // wakeLock.release();
    } catch (error) {
      console.error('Wake lock failed:', error);
    }
  }

  // Use for video streaming, live events, fitness tracking
  document.getElementById('start-livestream').addEventListener('click', () => {
    keepScreenOn();
  });

  // Auto-release on page visibility change
  document.addEventListener('visibilitychange', async () => {
    if (document.hidden) {
      // Page is hidden
    } else {
      // Page is visible, re-acquire wake lock if needed
    }
  });
</script>
`;

/* ============================================================
   8. BATTERY API - CHECK BATTERY STATUS
   ============================================================ */

BATTERY_EXAMPLE = `
<script>
  // Get battery status
  async function checkBattery() {
    const status = await BatteryManager.getBatteryStatus();
    if (status) {
      console.log('Battery level:', status.level * 100 + '%');
      console.log('Charging:', status.charging);
      
      // Optimize features based on battery level
      if (status.level < 0.2) {
        // Low battery - disable animations, reduce quality
        disableExpensiveFeatures();
      }
    }
  }

  // Watch battery status
  BatteryManager.watchBatteryStatus((status) => {
    console.log('Battery:', status.level * 100 + '%', status.charging ? '🔌 Charging' : '🔋');
    
    const batteryIndicator = document.getElementById('battery-indicator');
    if (batteryIndicator) {
      batteryIndicator.textContent = Math.round(status.level * 100) + '%';
      batteryIndicator.classList.toggle('charging', status.charging);
    }
  });

  checkBattery();
</script>
`;

/* ============================================================
   9. COMBINED EXAMPLE - AVATAR UPLOAD WITH CAMERA
   ============================================================ */

AVATAR_UPLOAD_EXAMPLE = `
<!-- HTML -->
<div class="avatar-upload">
  <img id="current-avatar" src="/user/avatar.jpg" alt="Avatar">
  
  <!-- Buttons -->
  <div class="upload-options">
    <button id="camera-btn" class="btn btn-secondary">
      <i class="fas fa-camera"></i> Фото
    </button>
    <button id="gallery-btn" class="btn btn-secondary">
      <i class="fas fa-images"></i> Галерея
    </button>
  </div>

  <!-- Camera modal -->
  <div id="camera-modal" style="display: none;">
    <video id="upload-camera" playsinline autoplay></video>
    <button id="capture-btn">Сфотографировать</button>
  </div>
</div>

<script>
  let uploadCamera = null;

  // Open camera
  document.getElementById('camera-btn').addEventListener('click', async () => {
    uploadCamera = new CameraCapture('#upload-camera', {
      facingMode: 'user'
    });
    
    try {
      await uploadCamera.startCamera();
      document.getElementById('camera-modal').style.display = 'block';
    } catch (error) {
      alert('Не удалось открыть камеру');
    }
  });

  // Capture avatar photo
  document.getElementById('capture-btn').addEventListener('click', async () => {
    const photoDataUrl = uploadCamera.capturePhoto();
    
    // Upload to server
    const response = await fetch('/api/users/avatar/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body: JSON.stringify({
        image: photoDataUrl
      })
    });

    if (response.ok) {
      const data = await response.json();
      document.getElementById('current-avatar').src = data.avatar_url;
      document.getElementById('camera-modal').style.display = 'none';
      uploadCamera.stopCamera();
      new Toast('success', 'Аватар обновлен!');
    }
  });

  // Gallery upload
  document.getElementById('gallery-btn').addEventListener('click', () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      const reader = new FileReader();
      reader.onload = async (event) => {
        const response = await fetch('/api/users/avatar/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
          },
          body: JSON.stringify({
            image: event.target.result
          })
        });
        
        if (response.ok) {
          const data = await response.json();
          document.getElementById('current-avatar').src = data.avatar_url;
          new Toast('success', 'Аватар обновлен!');
        }
      };
      reader.readAsDataURL(file);
    });
    input.click();
  });
</script>
`;

export { 
  GEOLOCATION_EXAMPLE,
  CAMERA_EXAMPLE,
  CLIPBOARD_EXAMPLE,
  SHARE_EXAMPLE,
  DEVICE_MOTION_EXAMPLE,
  FULLSCREEN_EXAMPLE,
  SCREEN_WAKE_LOCK_EXAMPLE,
  BATTERY_EXAMPLE,
  AVATAR_UPLOAD_EXAMPLE
};
