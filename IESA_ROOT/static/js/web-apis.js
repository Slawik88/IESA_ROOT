/**
 * Web APIs Integration
 * Geolocation, Camera, Microphone, Clipboard, Share, Device Motion, etc
 */

class GeoLocationManager {
  constructor(options = {}) {
    this.options = {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 0,
      ...options
    };

    this.currentPosition = null;
    this.watching = false;
    this.watchId = null;
    this.hasPermission = null;
  }

  async getCurrentPosition() {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        reject(new Error('Geolocation not supported'));
        return;
      }

      navigator.geolocation.getCurrentPosition(
        (position) => {
          this.currentPosition = position;
          resolve(position);
        },
        (error) => {
          console.error('Geolocation error:', error);
          reject(error);
        },
        this.options
      );
    });
  }

  async watchPosition(callback) {
    if (!navigator.geolocation) {
      throw new Error('Geolocation not supported');
    }

    this.watchId = navigator.geolocation.watchPosition(
      (position) => {
        this.currentPosition = position;
        callback(position);
      },
      (error) => {
        console.error('Geolocation watch error:', error);
      },
      this.options
    );

    this.watching = true;
    return this.watchId;
  }

  stopWatching() {
    if (this.watchId && navigator.geolocation) {
      navigator.geolocation.clearWatch(this.watchId);
      this.watching = false;
    }
  }

  getCoordinates() {
    if (!this.currentPosition) return null;
    return {
      latitude: this.currentPosition.coords.latitude,
      longitude: this.currentPosition.coords.longitude,
      accuracy: this.currentPosition.coords.accuracy,
      altitude: this.currentPosition.coords.altitude,
      altitudeAccuracy: this.currentPosition.coords.altitudeAccuracy,
      heading: this.currentPosition.coords.heading,
      speed: this.currentPosition.coords.speed,
      timestamp: this.currentPosition.timestamp
    };
  }

  calculateDistance(lat1, lon1, lat2, lon2) {
    const R = 6371; // Earth's radius in km
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
      Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
  }
}

class CameraCapture {
  constructor(videoElementSelector, options = {}) {
    this.videoElement = document.querySelector(videoElementSelector);
    this.options = {
      width: { ideal: 1280 },
      height: { ideal: 720 },
      facingMode: 'user',
      ...options
    };

    this.stream = null;
    this.canvas = null;
    this.context = null;
  }

  async startCamera() {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('Camera not supported');
      }

      this.stream = await navigator.mediaDevices.getUserMedia({
        video: this.options,
        audio: false
      });

      if (this.videoElement) {
        this.videoElement.srcObject = this.stream;
        await new Promise(resolve => {
          this.videoElement.onloadedmetadata = resolve;
        });
      }

      console.log('✅ Camera started');
      return this.stream;
    } catch (error) {
      console.error('❌ Failed to start camera:', error);
      throw error;
    }
  }

  stopCamera() {
    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
      this.stream = null;
      console.log('✅ Camera stopped');
    }
  }

  capturePhoto() {
    if (!this.videoElement) return null;

    const canvas = document.createElement('canvas');
    canvas.width = this.videoElement.videoWidth;
    canvas.height = this.videoElement.videoHeight;

    const context = canvas.getContext('2d');
    context.drawImage(this.videoElement, 0, 0);

    return canvas.toDataURL('image/jpeg', 0.8);
  }

  async switchCamera() {
    this.stopCamera();
    this.options.facingMode = 
      this.options.facingMode === 'user' ? 'environment' : 'user';
    await this.startCamera();
  }

  recordVideo(duration = 10000) {
    return new Promise((resolve) => {
      const chunks = [];
      const mediaRecorder = new MediaRecorder(this.stream);

      mediaRecorder.ondataavailable = (e) => {
        chunks.push(e.data);
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(chunks, { type: 'video/webm' });
        resolve(blob);
      };

      mediaRecorder.start();
      setTimeout(() => {
        mediaRecorder.stop();
      }, duration);
    });
  }
}

class ClipboardManager {
  static async copyText(text) {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        console.log('✅ Copied to clipboard');
        return true;
      } else {
        // Fallback for older browsers
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        console.log('✅ Copied to clipboard (fallback)');
        return true;
      }
    } catch (error) {
      console.error('❌ Failed to copy:', error);
      return false;
    }
  }

  static async readText() {
    try {
      if (!navigator.clipboard || !window.isSecureContext) {
        throw new Error('Clipboard read not supported');
      }
      const text = await navigator.clipboard.readText();
      return text;
    } catch (error) {
      console.error('❌ Failed to read clipboard:', error);
      throw error;
    }
  }

  static async copyImage(imageBlobOrUrl) {
    try {
      if (!navigator.clipboard || !window.isSecureContext) {
        throw new Error('Clipboard write not supported');
      }

      let blob = imageBlobOrUrl;
      if (typeof imageBlobOrUrl === 'string') {
        const response = await fetch(imageBlobOrUrl);
        blob = await response.blob();
      }

      await navigator.clipboard.write([
        new ClipboardItem({ [blob.type]: blob })
      ]);
      console.log('✅ Image copied to clipboard');
      return true;
    } catch (error) {
      console.error('❌ Failed to copy image:', error);
      return false;
    }
  }
}

class ShareManager {
  static async share(data) {
    try {
      if (!navigator.share) {
        throw new Error('Share API not supported');
      }

      await navigator.share({
        title: data.title || document.title,
        text: data.text || document.description || '',
        url: data.url || window.location.href,
        ...data
      });

      console.log('✅ Share successful');
      return true;
    } catch (error) {
      if (error.name !== 'AbortError') {
        console.error('❌ Share failed:', error);
      }
      return false;
    }
  }

  static async shareFile(files, title = 'Share') {
    try {
      if (!navigator.share) {
        throw new Error('Share API not supported');
      }

      await navigator.share({
        title: title,
        files: files
      });

      console.log('✅ File share successful');
      return true;
    } catch (error) {
      console.error('❌ File share failed:', error);
      return false;
    }
  }

  static canShare() {
    return !!navigator.share;
  }
}

class DeviceMotionDetector {
  constructor(options = {}) {
    this.options = {
      shakeSensitivity: 20,
      tiltThreshold: 30,
      ...options
    };

    this.lastX = 0;
    this.lastY = 0;
    this.lastZ = 0;
    this.shakeDetected = false;
  }

  startShakeDetection(callback) {
    if (!window.DeviceMotionEvent) {
      console.warn('⚠️ Device Motion not supported');
      return;
    }

    window.addEventListener('devicemotion', (event) => {
      const x = event.accelerationIncludingGravity.x;
      const y = event.accelerationIncludingGravity.y;
      const z = event.accelerationIncludingGravity.z;

      const acceleration = Math.sqrt(
        Math.pow(x - this.lastX, 2) +
        Math.pow(y - this.lastY, 2) +
        Math.pow(z - this.lastZ, 2)
      );

      if (acceleration > this.options.shakeSensitivity) {
        if (!this.shakeDetected) {
          this.shakeDetected = true;
          callback({ type: 'shake', acceleration });

          setTimeout(() => {
            this.shakeDetected = false;
          }, 500);
        }
      }

      this.lastX = x;
      this.lastY = y;
      this.lastZ = z;
    });
  }

  startTiltDetection(callback) {
    if (!window.DeviceOrientationEvent) {
      console.warn('⚠️ Device Orientation not supported');
      return;
    }

    window.addEventListener('deviceorientation', (event) => {
      const alpha = event.alpha; // Z axis
      const beta = event.beta;   // X axis
      const gamma = event.gamma; // Y axis

      callback({
        type: 'tilt',
        alpha: alpha,
        beta: beta,
        gamma: gamma,
        isPortrait: Math.abs(beta) < this.options.tiltThreshold
      });
    });
  }

  static async requestPermission() {
    if (typeof DeviceMotionEvent === 'undefined') {
      return { permission: 'denied' };
    }

    if (DeviceMotionEvent.requestPermission) {
      try {
        const permission = await DeviceMotionEvent.requestPermission();
        return { permission };
      } catch (error) {
        console.error('❌ Permission request failed:', error);
        return { permission: 'denied' };
      }
    }

    return { permission: 'granted' };
  }
}

class ScreenManager {
  static async requestFullscreen(element) {
    try {
      if (element.requestFullscreen) {
        await element.requestFullscreen();
      } else if (element.webkitRequestFullscreen) {
        element.webkitRequestFullscreen();
      } else if (element.mozRequestFullScreen) {
        element.mozRequestFullScreen();
      } else if (element.msRequestFullscreen) {
        element.msRequestFullscreen();
      }
      console.log('✅ Fullscreen mode enabled');
      return true;
    } catch (error) {
      console.error('❌ Fullscreen request failed:', error);
      return false;
    }
  }

  static exitFullscreen() {
    if (document.exitFullscreen) {
      document.exitFullscreen();
    } else if (document.webkitExitFullscreen) {
      document.webkitExitFullscreen();
    } else if (document.mozCancelFullScreen) {
      document.mozCancelFullScreen();
    } else if (document.msExitFullscreen) {
      document.msExitFullscreen();
    }
    console.log('✅ Fullscreen mode disabled');
  }

  static async requestScreenWakeLock() {
    try {
      if (!('wakeLock' in navigator)) {
        throw new Error('Screen Wake Lock not supported');
      }

      const wakeLock = await navigator.wakeLock.request('screen');
      console.log('✅ Screen will not sleep');

      wakeLock.addEventListener('release', () => {
        console.log('✅ Screen Wake Lock released');
      });

      return wakeLock;
    } catch (error) {
      console.error('❌ Wake Lock request failed:', error);
      throw error;
    }
  }
}

class BatteryManager {
  static async getBatteryStatus() {
    try {
      if (!navigator.getBattery) {
        throw new Error('Battery API not available');
      }

      const battery = await navigator.getBattery();
      return {
        level: battery.level,
        charging: battery.charging,
        chargingTime: battery.chargingTime,
        dischargingTime: battery.dischargingTime
      };
    } catch (error) {
      console.error('❌ Battery API error:', error);
      return null;
    }
  }

  static watchBatteryStatus(callback) {
    if (navigator.getBattery) {
      navigator.getBattery().then((battery) => {
        const updateBattery = () => {
          callback({
            level: battery.level,
            charging: battery.charging
          });
        };

        battery.addEventListener('levelchange', updateBattery);
        battery.addEventListener('chargingchange', updateBattery);
        updateBattery();
      });
    }
  }
}

// Export for use
window.GeoLocationManager = GeoLocationManager;
window.CameraCapture = CameraCapture;
window.ClipboardManager = ClipboardManager;
window.ShareManager = ShareManager;
window.DeviceMotionDetector = DeviceMotionDetector;
window.ScreenManager = ScreenManager;
window.BatteryManager = BatteryManager;
