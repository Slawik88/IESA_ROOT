/**
 * Advanced Form Enhancements
 * Progress tracking, conditional fields, multi-step forms, inline validation feedback
 */

class FormProgress {
  constructor(formSelector, options = {}) {
    this.form = document.querySelector(formSelector);
    this.options = {
      showPercentage: true,
      animateBar: true,
      requiredFieldsOnly: true,
      ...options
    };

    if (this.form) {
      this.init();
    }
  }

  init() {
    // Create progress bar container
    this.progressContainer = document.createElement('div');
    this.progressContainer.className = 'form-progress-container';
    this.form.insertBefore(this.progressContainer, this.form.firstChild);

    // Create progress bar
    this.progressBar = document.createElement('div');
    this.progressBar.className = 'form-progress-bar';
    this.progressContainer.appendChild(this.progressBar);

    // Create percentage text
    if (this.options.showPercentage) {
      this.percentageText = document.createElement('span');
      this.percentageText.className = 'form-progress-text';
      this.progressContainer.appendChild(this.percentageText);
    }

    // Track changes
    const inputs = this.form.querySelectorAll('input, textarea, select');
    inputs.forEach(input => {
      input.addEventListener('input', () => this.updateProgress());
      input.addEventListener('change', () => this.updateProgress());
    });

    // Initial update
    this.updateProgress();
  }

  updateProgress() {
    const inputs = this.form.querySelectorAll('input, textarea, select');
    let filledCount = 0;
    let totalCount = 0;

    inputs.forEach(input => {
      // Skip hidden fields
      if (input.type === 'hidden') return;

      // Skip unless required or always count
      if (this.options.requiredFieldsOnly && !input.hasAttribute('data-validate')) {
        return;
      }

      totalCount++;

      // Check if filled
      if (input.type === 'checkbox' || input.type === 'radio') {
        if (input.checked) filledCount++;
      } else if (input.value.trim() !== '') {
        filledCount++;
      }
    });

    const percentage = totalCount > 0 ? Math.round((filledCount / totalCount) * 100) : 0;

    // Update bar
    this.progressBar.style.width = percentage + '%';
    this.progressBar.setAttribute('data-progress', percentage);

    // Update text
    if (this.percentageText) {
      this.percentageText.textContent = percentage + '%';
    }

    // Add animation class
    if (this.options.animateBar) {
      this.progressBar.classList.add('animate');
    }
  }
}

class ConditionalFields {
  constructor(formSelector) {
    this.form = document.querySelector(formSelector);
    this.rules = new Map();

    if (this.form) {
      this.init();
    }
  }

  init() {
    // Find all fields with conditions
    const conditionalFields = this.form.querySelectorAll('[data-show-if]');

    conditionalFields.forEach(field => {
      const condition = field.dataset.showIf;
      const [fieldName, expectedValue] = condition.split(':');

      // Store rule
      if (!this.rules.has(fieldName)) {
        this.rules.set(fieldName, []);
      }
      this.rules.get(fieldName).push({
        field: field,
        expectedValue: expectedValue || 'true'
      });

      // Listen to trigger field
      const triggerField = this.form.querySelector(`[name="${fieldName}"]`);
      if (triggerField) {
        triggerField.addEventListener('change', () => this.checkConditions(fieldName));
        triggerField.addEventListener('input', () => this.checkConditions(fieldName));
      }
    });

    // Check initial state
    this.rules.forEach((_, fieldName) => {
      this.checkConditions(fieldName);
    });
  }

  checkConditions(fieldName) {
    const rules = this.rules.get(fieldName);
    if (!rules) return;

    const triggerField = this.form.querySelector(`[name="${fieldName}"]`);
    const currentValue = this.getCurrentValue(triggerField);

    rules.forEach(rule => {
      const shouldShow = currentValue === rule.expectedValue ||
                        (rule.expectedValue === 'true' && currentValue) ||
                        (rule.expectedValue === 'false' && !currentValue);

      if (shouldShow) {
        rule.field.classList.add('show');
        rule.field.style.display = 'block';
        // Mark fields as visible for validation
        rule.field.querySelectorAll('input, textarea, select').forEach(input => {
          input.removeAttribute('disabled');
        });
      } else {
        rule.field.classList.remove('show');
        rule.field.style.display = 'none';
        // Disable fields to exclude from validation
        rule.field.querySelectorAll('input, textarea, select').forEach(input => {
          input.setAttribute('disabled', 'disabled');
        });
      }
    });
  }

  getCurrentValue(field) {
    if (!field) return null;

    if (field.type === 'checkbox') {
      return field.checked ? 'true' : 'false';
    } else if (field.type === 'radio') {
      const checked = this.form.querySelector(`[name="${field.name}"]:checked`);
      return checked ? checked.value : null;
    }
    return field.value;
  }
}

class MultiStepForm {
  constructor(formSelector, options = {}) {
    this.form = document.querySelector(formSelector);
    this.currentStep = 0;
    this.totalSteps = 0;
    this.validator = null;

    this.options = {
      stepSelector: '.form-step',
      validateOnNext: true,
      showStepIndicator: true,
      showNavigation: true,
      ...options
    };

    if (this.form) {
      this.init();
    }
  }

  init() {
    // Get all steps
    this.steps = this.form.querySelectorAll(this.options.stepSelector);
    this.totalSteps = this.steps.length;

    // Create step indicator
    if (this.options.showStepIndicator) {
      this.createStepIndicator();
    }

    // Create navigation
    if (this.options.showNavigation) {
      this.createNavigation();
    }

    // Show first step
    this.showStep(0);
  }

  createStepIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'form-step-indicator';

    for (let i = 0; i < this.totalSteps; i++) {
      const stepNum = document.createElement('div');
      stepNum.className = 'step-number';
      stepNum.dataset.step = i;
      stepNum.textContent = i + 1;
      stepNum.addEventListener('click', () => this.goToStep(i));
      indicator.appendChild(stepNum);
    }

    this.form.insertBefore(indicator, this.form.firstChild);
    this.stepIndicator = indicator;
  }

  createNavigation() {
    const nav = document.createElement('div');
    nav.className = 'form-step-navigation';

    const prevBtn = document.createElement('button');
    prevBtn.type = 'button';
    prevBtn.className = 'btn btn-secondary';
    prevBtn.textContent = 'Назад';
    prevBtn.addEventListener('click', () => this.previousStep());

    const nextBtn = document.createElement('button');
    nextBtn.type = 'button';
    nextBtn.className = 'btn btn-primary';
    nextBtn.textContent = 'Далее';
    nextBtn.addEventListener('click', () => this.nextStep());
    nextBtn.dataset.action = 'next';

    const submitBtn = document.createElement('button');
    submitBtn.type = 'submit';
    submitBtn.className = 'btn btn-success';
    submitBtn.textContent = 'Отправить';
    submitBtn.style.display = 'none';

    nav.appendChild(prevBtn);
    nav.appendChild(nextBtn);
    nav.appendChild(submitBtn);

    this.form.appendChild(nav);
    this.prevBtn = prevBtn;
    this.nextBtn = nextBtn;
    this.submitBtn = submitBtn;
  }

  showStep(stepIndex) {
    if (stepIndex < 0 || stepIndex >= this.totalSteps) return;

    // Hide all steps
    this.steps.forEach((step, index) => {
      step.classList.remove('active');
      step.style.display = 'none';
    });

    // Show current step
    this.steps[stepIndex].classList.add('active');
    this.steps[stepIndex].style.display = 'block';
    this.currentStep = stepIndex;

    // Update indicator
    if (this.stepIndicator) {
      this.stepIndicator.querySelectorAll('.step-number').forEach((num, index) => {
        num.classList.toggle('active', index === stepIndex);
        num.classList.toggle('completed', index < stepIndex);
      });
    }

    // Update buttons
    if (this.prevBtn) {
      this.prevBtn.style.display = stepIndex === 0 ? 'none' : 'block';
    }
    if (this.nextBtn && this.submitBtn) {
      const isLastStep = stepIndex === this.totalSteps - 1;
      this.nextBtn.style.display = isLastStep ? 'none' : 'block';
      this.submitBtn.style.display = isLastStep ? 'block' : 'none';
    }

    // Scroll to top
    this.form.scrollIntoView({ behavior: 'smooth' });
  }

  nextStep() {
    // Validate current step if enabled
    if (this.options.validateOnNext && this.validator) {
      const stepFields = this.steps[this.currentStep].querySelectorAll('input, textarea, select');
      let isValid = true;

      stepFields.forEach(field => {
        if (field.dataset.validate) {
          if (!this.validator.validateField(field.name)) {
            isValid = false;
          }
        }
      });

      if (!isValid) return;
    }

    if (this.currentStep < this.totalSteps - 1) {
      this.showStep(this.currentStep + 1);
    }
  }

  previousStep() {
    if (this.currentStep > 0) {
      this.showStep(this.currentStep - 1);
    }
  }

  goToStep(stepIndex) {
    this.showStep(stepIndex);
  }

  setValidator(validator) {
    this.validator = validator;
  }

  getCurrentStepNumber() {
    return this.currentStep + 1;
  }

  getTotalSteps() {
    return this.totalSteps;
  }
}

class FieldDependencies {
  constructor(formSelector) {
    this.form = document.querySelector(formSelector);
    this.dependencies = new Map();

    if (this.form) {
      this.init();
    }
  }

  init() {
    // Find fields with dependencies
    const fields = this.form.querySelectorAll('[data-depends-on]');

    fields.forEach(field => {
      const dependsOn = field.dataset.dependsOn;
      const dependentFields = dependsOn.split(',').map(f => f.trim());

      dependentFields.forEach(depFieldName => {
        const depField = this.form.querySelector(`[name="${depFieldName}"]`);
        if (depField) {
          if (!this.dependencies.has(depFieldName)) {
            this.dependencies.set(depFieldName, []);
          }
          this.dependencies.get(depFieldName).push(field);

          // Listen to changes
          depField.addEventListener('change', () => this.updateDependents(depFieldName));
          depField.addEventListener('input', () => this.updateDependents(depFieldName));
        }
      });
    });

    // Check initial state
    this.dependencies.forEach((_, fieldName) => {
      this.updateDependents(fieldName);
    });
  }

  updateDependents(fieldName) {
    const dependents = this.dependencies.get(fieldName);
    if (!dependents) return;

    dependents.forEach(field => {
      const action = field.dataset.dependentAction || 'enable';

      if (action === 'enable') {
        field.removeAttribute('disabled');
      } else if (action === 'disable') {
        field.setAttribute('disabled', 'disabled');
      } else if (action === 'show') {
        field.parentElement.style.display = 'block';
      } else if (action === 'hide') {
        field.parentElement.style.display = 'none';
      }
    });
  }
}

class InlineValidationFeedback {
  constructor(fieldSelector, validatorFunction) {
    this.field = document.querySelector(fieldSelector);
    this.validator = validatorFunction;
    this.feedbackEl = null;

    if (this.field) {
      this.init();
    }
  }

  init() {
    // Create feedback element
    this.feedbackEl = document.createElement('div');
    this.feedbackEl.className = 'inline-validation-feedback';
    this.field.parentElement.appendChild(this.feedbackEl);

    // Listen to input
    this.field.addEventListener('input', () => this.updateFeedback());
    this.field.addEventListener('change', () => this.updateFeedback());
  }

  updateFeedback() {
    const value = this.field.value;
    const result = this.validator(value);

    if (result.isValid) {
      this.feedbackEl.className = 'inline-validation-feedback valid';
      this.feedbackEl.innerHTML = `<i class="fas fa-check"></i> ${result.message || 'Хорошо'}`;
    } else {
      this.feedbackEl.className = 'inline-validation-feedback invalid';
      this.feedbackEl.innerHTML = `<i class="fas fa-times"></i> ${result.message || 'Ошибка'}`;
    }
  }
}

// Export for use
window.FormProgress = FormProgress;
window.ConditionalFields = ConditionalFields;
window.MultiStepForm = MultiStepForm;
window.FieldDependencies = FieldDependencies;
window.InlineValidationFeedback = InlineValidationFeedback;
