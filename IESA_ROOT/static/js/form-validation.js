/**
 * Real-time Form Validation System
 * Validates form fields as user types with visual feedback
 * Features: Rules engine, custom validators, error animations, success states
 */

class FormValidator {
  constructor(formSelector, options = {}) {
    this.form = document.querySelector(formSelector);
    this.fields = new Map();
    this.errors = new Map();
    this.isSubmitting = false;
    
    this.options = {
      debounceDelay: 300,
      showErrorsOnBlur: true,
      showSuccessState: true,
      validateOnInput: true,
      customMessages: {},
      ...options
    };

    this.validationRules = {
      required: (value) => value.trim().length > 0,
      email: (value) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value),
      phone: (value) => /^[\d\s\-\+\(\)]{10,}$/.test(value),
      password: (value) => value.length >= 8,
      passwordStrong: (value) => /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$/.test(value),
      username: (value) => /^[a-zA-Z0-9_]{3,20}$/.test(value),
      url: (value) => {
        try {
          new URL(value);
          return true;
        } catch {
          return false;
        }
      },
      number: (value) => !isNaN(value) && value.trim() !== '',
      minLength: (value, min) => value.length >= min,
      maxLength: (value, max) => value.length <= max,
      match: (value, fieldName) => {
        const matchField = this.form.querySelector(`[name="${fieldName}"]`);
        return matchField && value === matchField.value;
      },
      custom: (value, validator) => validator(value)
    };

    this.errorMessages = {
      required: 'Это поле обязательно',
      email: 'Введите корректный email',
      phone: 'Введите корректный номер телефона',
      password: 'Пароль должен быть минимум 8 символов',
      passwordStrong: 'Пароль должен содержать: прописные, строчные буквы, цифры и символы',
      username: 'Имя пользователя: 3-20 символов, буквы, цифры и подчеркивание',
      url: 'Введите корректный URL',
      number: 'Введите число',
      minLength: 'Минимум {{min}} символов',
      maxLength: 'Максимум {{max}} символов',
      match: 'Поля не совпадают',
      custom: 'Поле заполнено неверно',
      ...this.options.customMessages
    };

    if (this.form) {
      this.init();
    }
  }

  init() {
    // Find all form fields
    const inputs = this.form.querySelectorAll('input, textarea, select');
    
    inputs.forEach(field => {
      const rules = this.parseFieldRules(field);
      if (rules.length > 0) {
        this.fields.set(field.name, {
          element: field,
          rules: rules,
          debounceTimer: null,
          isDirty: false,
          isValid: true
        });

        // Attach event listeners
        if (this.options.validateOnInput) {
          field.addEventListener('input', this.debounce(() => {
            this.validateField(field.name);
          }, this.options.debounceDelay));
        }

        if (this.options.showErrorsOnBlur) {
          field.addEventListener('blur', () => {
            this.validateField(field.name);
          });
        }

        field.addEventListener('focus', () => {
          this.clearFieldError(field.name);
        });
      }
    });

    // Form submission
    this.form.addEventListener('submit', (e) => this.handleSubmit(e));
  }

  parseFieldRules(field) {
    const rulesAttr = field.dataset.validate;
    if (!rulesAttr) return [];

    const rules = [];
    const ruleParts = rulesAttr.split('|');

    ruleParts.forEach(rulePart => {
      const [ruleName, ...params] = rulePart.trim().split(':');
      rules.push({
        name: ruleName.trim(),
        params: params.map(p => p.trim())
      });
    });

    return rules;
  }

  validateField(fieldName) {
    if (!this.fields.has(fieldName)) return true;

    const fieldData = this.fields.get(fieldName);
    const { element, rules } = fieldData;
    const value = element.value;

    fieldData.isDirty = true;
    let isValid = true;
    let errorMessage = '';

    for (const rule of rules) {
      const { name, params } = rule;
      const validator = this.validationRules[name];

      if (!validator) {
        console.warn(`Validation rule "${name}" not found`);
        continue;
      }

      let ruleResult = false;
      
      if (name === 'required') {
        ruleResult = validator(value);
      } else if (name === 'minLength') {
        ruleResult = validator(value, parseInt(params[0]));
      } else if (name === 'maxLength') {
        ruleResult = validator(value, parseInt(params[0]));
      } else if (name === 'match') {
        ruleResult = validator(value, params[0]);
      } else if (name === 'custom') {
        // Custom validators passed via callbacks
        const customValidator = element.dataset.customValidator;
        if (customValidator && window[customValidator]) {
          ruleResult = window[customValidator](value);
        }
      } else {
        ruleResult = validator(value);
      }

      if (!ruleResult) {
        isValid = false;
        errorMessage = this.getErrorMessage(name, params[0], element);
        break;
      }
    }

    fieldData.isValid = isValid;

    if (isValid && fieldData.isDirty) {
      this.showFieldSuccess(fieldName);
    } else if (!isValid && fieldData.isDirty) {
      this.showFieldError(fieldName, errorMessage);
    } else {
      this.clearFieldError(fieldName);
    }

    return isValid;
  }

  validateAll() {
    let isFormValid = true;

    this.fields.forEach((fieldData, fieldName) => {
      fieldData.isDirty = true;
      if (!this.validateField(fieldName)) {
        isFormValid = false;
      }
    });

    return isFormValid;
  }

  getErrorMessage(ruleName, param, field) {
    let message = this.errorMessages[ruleName] || ruleName;
    
    if (ruleName === 'minLength') {
      message = message.replace('{{min}}', param);
    } else if (ruleName === 'maxLength') {
      message = message.replace('{{max}}', param);
    }

    return message;
  }

  showFieldError(fieldName, errorMessage) {
    const fieldData = this.fields.get(fieldName);
    if (!fieldData) return;

    const { element } = fieldData;
    const errorEl = this.getOrCreateErrorElement(fieldName);

    element.classList.add('is-invalid');
    element.classList.remove('is-valid');
    errorEl.textContent = errorMessage;
    errorEl.classList.add('show');

    // Vibration feedback on mobile
    if (navigator.vibrate) {
      navigator.vibrate(50);
    }

    this.errors.set(fieldName, errorMessage);
  }

  showFieldSuccess(fieldName) {
    const fieldData = this.fields.get(fieldName);
    if (!fieldData) return;

    const { element } = fieldData;
    const errorEl = this.getOrCreateErrorElement(fieldName);

    element.classList.remove('is-invalid');
    if (this.options.showSuccessState) {
      element.classList.add('is-valid');
    }
    errorEl.classList.remove('show');
    this.errors.delete(fieldName);
  }

  clearFieldError(fieldName) {
    const fieldData = this.fields.get(fieldName);
    if (!fieldData) return;

    const { element } = fieldData;
    const errorEl = this.getOrCreateErrorElement(fieldName);

    if (!fieldData.isDirty) {
      element.classList.remove('is-invalid', 'is-valid');
      errorEl.classList.remove('show');
    }
  }

  getOrCreateErrorElement(fieldName) {
    const fieldData = this.fields.get(fieldName);
    const { element } = fieldData;
    const wrapper = element.closest('.form-group') || element.parentElement;
    let errorEl = wrapper.querySelector('.invalid-feedback');

    if (!errorEl) {
      errorEl = document.createElement('div');
      errorEl.className = 'invalid-feedback';
      wrapper.appendChild(errorEl);
    }

    return errorEl;
  }

  handleSubmit(e) {
    if (this.isSubmitting) return;

    if (!this.validateAll()) {
      e.preventDefault();
      this.scrollToFirstError();
    } else {
      this.isSubmitting = true;
      this.disableSubmitButton();
    }
  }

  scrollToFirstError() {
    let firstError = null;
    
    this.fields.forEach((fieldData) => {
      if (!fieldData.isValid && !firstError) {
        firstError = fieldData.element;
      }
    });

    if (firstError) {
      firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
      firstError.focus();
    }
  }

  disableSubmitButton() {
    const submitBtn = this.form.querySelector('button[type="submit"]');
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.classList.add('disabled');
      
      // Re-enable after 2 seconds (or when form resets)
      setTimeout(() => {
        submitBtn.disabled = false;
        submitBtn.classList.remove('disabled');
        this.isSubmitting = false;
      }, 2000);
    }
  }

  debounce(callback, delay) {
    return (...args) => {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = setTimeout(() => callback(...args), delay);
    };
  }

  // Public API
  isValid() {
    let valid = true;
    this.fields.forEach((fieldData) => {
      if (!fieldData.isValid) valid = false;
    });
    return valid;
  }

  getErrors() {
    return Object.fromEntries(this.errors);
  }

  reset() {
    this.form.reset();
    this.fields.forEach((fieldData) => {
      fieldData.isDirty = false;
      fieldData.isValid = true;
      const errorEl = fieldData.element.closest('.form-group')?.querySelector('.invalid-feedback');
      if (errorEl) errorEl.classList.remove('show');
      fieldData.element.classList.remove('is-invalid', 'is-valid');
    });
    this.errors.clear();
  }
}

// Auto-save form data
class FormAutoSave {
  constructor(formSelector, options = {}) {
    this.form = document.querySelector(formSelector);
    this.storageKey = options.storageKey || `form_autosave_${this.form.id}`;
    this.debounceDelay = options.debounceDelay || 1000;
    this.debounceTimer = null;
    this.autoSaveIndicator = null;

    if (this.form) {
      this.init();
    }
  }

  init() {
    // Find all form fields
    const inputs = this.form.querySelectorAll('input, textarea, select');
    
    inputs.forEach(field => {
      field.addEventListener('input', () => this.scheduleAutoSave());
      field.addEventListener('change', () => this.scheduleAutoSave());
    });

    // Restore saved data on page load
    this.restoreData();

    // Create auto-save indicator
    this.createIndicator();

    // Clear saved data on successful form submission
    this.form.addEventListener('submit', () => {
      if (!this.form.dataset.noAutosaveClear) {
        setTimeout(() => this.clearData(), 500);
      }
    });
  }

  scheduleAutoSave() {
    clearTimeout(this.debounceTimer);
    this.debounceTimer = setTimeout(() => this.saveData(), this.debounceDelay);
    this.showAutoSaveIndicator('saving');
  }

  saveData() {
    const formData = new FormData(this.form);
    const data = {};

    formData.forEach((value, key) => {
      if (data[key]) {
        if (Array.isArray(data[key])) {
          data[key].push(value);
        } else {
          data[key] = [data[key], value];
        }
      } else {
        data[key] = value;
      }
    });

    localStorage.setItem(this.storageKey, JSON.stringify({
      data: data,
      timestamp: new Date().toISOString()
    }));

    this.showAutoSaveIndicator('saved');
  }

  restoreData() {
    const saved = localStorage.getItem(this.storageKey);
    if (!saved) return;

    try {
      const { data } = JSON.parse(saved);
      
      Object.entries(data).forEach(([key, value]) => {
        const field = this.form.querySelector(`[name="${key}"]`);
        if (field) {
          if (field.type === 'checkbox' || field.type === 'radio') {
            field.checked = value === 'on' || value === field.value;
          } else {
            field.value = value;
          }
          // Trigger change event
          field.dispatchEvent(new Event('change', { bubbles: true }));
        }
      });
    } catch (error) {
      console.error('Error restoring form data:', error);
    }
  }

  createIndicator() {
    this.autoSaveIndicator = document.createElement('div');
    this.autoSaveIndicator.className = 'auto-save-indicator';
    this.autoSaveIndicator.innerHTML = '<span class="auto-save-text">Сохраняется...</span>';
    this.form.appendChild(this.autoSaveIndicator);
  }

  showAutoSaveIndicator(status) {
    if (!this.autoSaveIndicator) return;

    this.autoSaveIndicator.classList.remove('saving', 'saved', 'hidden');
    
    if (status === 'saving') {
      this.autoSaveIndicator.classList.add('saving');
    } else if (status === 'saved') {
      this.autoSaveIndicator.classList.add('saved');
      setTimeout(() => {
        this.autoSaveIndicator.classList.add('hidden');
      }, 2000);
    }
  }

  clearData() {
    localStorage.removeItem(this.storageKey);
  }

  getData() {
    const saved = localStorage.getItem(this.storageKey);
    return saved ? JSON.parse(saved) : null;
  }
}

// Password strength indicator
class PasswordStrengthMeter {
  constructor(inputSelector, meterSelector) {
    this.input = document.querySelector(inputSelector);
    this.meter = document.querySelector(meterSelector);

    if (this.input && this.meter) {
      this.input.addEventListener('input', () => this.updateMeter());
    }
  }

  updateMeter() {
    const value = this.input.value;
    const strength = this.calculateStrength(value);
    
    const meter = this.meter.querySelector('.strength-bar');
    const text = this.meter.querySelector('.strength-text');

    meter.className = 'strength-bar';
    meter.classList.add(`strength-${strength.level}`);
    text.textContent = strength.text;
  }

  calculateStrength(password) {
    let strength = 0;
    const feedback = [];

    if (password.length >= 8) strength++;
    if (password.length >= 12) strength++;
    if (/[a-z]/.test(password)) strength++;
    if (/[A-Z]/.test(password)) strength++;
    if (/\d/.test(password)) strength++;
    if (/[@$!%*?&]/.test(password)) strength++;

    if (strength < 2) return { level: 'weak', text: 'Слабый пароль' };
    if (strength < 4) return { level: 'fair', text: 'Средний пароль' };
    if (strength < 6) return { level: 'good', text: 'Хороший пароль' };
    return { level: 'strong', text: 'Сильный пароль' };
  }
}

// Form field grouping and organization
class FormFieldGroup {
  constructor(groupSelector) {
    this.group = document.querySelector(groupSelector);
    this.fields = this.group?.querySelectorAll('[data-group-item]');
    this.init();
  }

  init() {
    if (!this.group) return;

    const groupType = this.group.dataset.groupType;

    if (groupType === 'collapsible') {
      this.initCollapsible();
    } else if (groupType === 'tabs') {
      this.initTabs();
    } else if (groupType === 'accordion') {
      this.initAccordion();
    }
  }

  initCollapsible() {
    const toggle = this.group.querySelector('.group-toggle');
    const content = this.group.querySelector('.group-content');

    toggle?.addEventListener('click', () => {
      content?.classList.toggle('show');
      toggle.classList.toggle('collapsed');
      this.group.classList.toggle('is-collapsed');
    });
  }

  initTabs() {
    const tabs = this.group.querySelectorAll('.group-tab');
    const panes = this.group.querySelectorAll('.group-pane');

    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        const target = tab.dataset.target;
        
        tabs.forEach(t => t.classList.remove('active'));
        panes.forEach(p => p.classList.remove('active'));
        
        tab.classList.add('active');
        this.group.querySelector(target)?.classList.add('active');
      });
    });

    // Activate first tab
    tabs[0]?.click();
  }

  initAccordion() {
    const items = this.group.querySelectorAll('.group-item');

    items.forEach(item => {
      const header = item.querySelector('.group-header');
      const content = item.querySelector('.group-content');

      header?.addEventListener('click', () => {
        const isOpen = item.classList.contains('open');

        if (!item.dataset.allowMultiple) {
          items.forEach(i => i.classList.remove('open'));
        }

        if (!isOpen) {
          item.classList.add('open');
          content.style.maxHeight = content.scrollHeight + 'px';
        } else {
          item.classList.remove('open');
          content.style.maxHeight = '0';
        }
      });
    });
  }
}

// Export for use
window.FormValidator = FormValidator;
window.FormAutoSave = FormAutoSave;
window.PasswordStrengthMeter = PasswordStrengthMeter;
window.FormFieldGroup = FormFieldGroup;
