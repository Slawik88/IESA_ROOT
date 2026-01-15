/**
 * TIER 5 Part 2: Form Enhancements Usage Examples
 * Multi-step forms, conditional fields, progress tracking
 */

/* ============================================================
   1. FORM WITH PROGRESS BAR
   ============================================================ */

HTML_PROGRESS_EXAMPLE = `
<form id="survey-form">
  <div class="form-group">
    <label for="name">Имя</label>
    <input 
      type="text" 
      id="name" 
      name="name" 
      class="form-control"
      data-validate="required"
    />
    <div class="invalid-feedback"></div>
  </div>

  <div class="form-group">
    <label for="email">Email</label>
    <input 
      type="email" 
      id="email" 
      name="email" 
      class="form-control"
      data-validate="required|email"
    />
    <div class="invalid-feedback"></div>
  </div>

  <div class="form-group">
    <label for="experience">Опыт</label>
    <select id="experience" name="experience" class="form-select" data-validate="required">
      <option value="">-- Выберите --</option>
      <option value="beginner">Новичок</option>
      <option value="intermediate">Средний уровень</option>
      <option value="advanced">Продвинутый</option>
    </select>
    <div class="invalid-feedback"></div>
  </div>

  <div class="form-group">
    <label for="feedback">Отзыв</label>
    <textarea 
      id="feedback" 
      name="feedback" 
      class="form-control"
      rows="4"
      data-validate="required|minLength:20"
    ></textarea>
    <div class="invalid-feedback"></div>
  </div>

  <button type="submit" class="btn btn-primary">Отправить</button>
</form>

<script>
  const validator = new FormValidator('#survey-form');
  const progress = new FormProgress('#survey-form', {
    showPercentage: true,
    requiredFieldsOnly: true
  });
</script>
`;

/* ============================================================
   2. MULTI-STEP REGISTRATION FORM
   ============================================================ */

HTML_MULTISTEP_EXAMPLE = `
<form id="registration-form">
  <!-- Step 1 -->
  <div class="form-step">
    <h4 class="mb-3">Личная информация</h4>

    <div class="form-group">
      <label for="first_name" class="required">Имя</label>
      <input 
        type="text" 
        id="first_name" 
        name="first_name" 
        class="form-control"
        data-validate="required|minLength:2"
      />
      <div class="invalid-feedback"></div>
    </div>

    <div class="form-group">
      <label for="last_name" class="required">Фамилия</label>
      <input 
        type="text" 
        id="last_name" 
        name="last_name" 
        class="form-control"
        data-validate="required|minLength:2"
      />
      <div class="invalid-feedback"></div>
    </div>

    <div class="form-group">
      <label for="birth_date">Дата рождения</label>
      <input 
        type="date" 
        id="birth_date" 
        name="birth_date" 
        class="form-control"
      />
    </div>
  </div>

  <!-- Step 2 -->
  <div class="form-step">
    <h4 class="mb-3">Контактная информация</h4>

    <div class="form-group">
      <label for="email" class="required">Email</label>
      <input 
        type="email" 
        id="email" 
        name="email" 
        class="form-control"
        data-validate="required|email"
      />
      <div class="invalid-feedback"></div>
    </div>

    <div class="form-group">
      <label for="phone">Телефон</label>
      <input 
        type="tel" 
        id="phone" 
        name="phone" 
        class="form-control"
        data-validate="phone"
      />
      <div class="invalid-feedback"></div>
    </div>

    <div class="form-group">
      <label for="country">Страна</label>
      <input 
        type="text" 
        id="country" 
        name="country" 
        class="form-control"
        placeholder="Страна"
      />
    </div>
  </div>

  <!-- Step 3 -->
  <div class="form-step">
    <h4 class="mb-3">Пароль и безопасность</h4>

    <div class="form-group">
      <label for="password" class="required">Пароль</label>
      <input 
        type="password" 
        id="password" 
        name="password" 
        class="form-control"
        data-validate="required|passwordStrong"
      />
      <div class="invalid-feedback"></div>
      <div class="password-strength-meter">
        <div class="strength-bar"></div>
        <span class="strength-text">Вводите пароль</span>
      </div>
    </div>

    <div class="form-group">
      <label for="password_confirm" class="required">Подтвердить пароль</label>
      <input 
        type="password" 
        id="password_confirm" 
        name="password_confirm" 
        class="form-control"
        data-validate="required|match:password"
      />
      <div class="invalid-feedback"></div>
    </div>

    <div class="form-check">
      <input 
        type="checkbox" 
        id="agree_terms" 
        name="agree_terms" 
        class="form-check-input"
        data-validate="required"
      />
      <label for="agree_terms" class="form-check-label">
        Я согласен с условиями использования <span class="required">*</span>
      </label>
      <div class="invalid-feedback d-block"></div>
    </div>
  </div>
</form>

<script>
  const validator = new FormValidator('#registration-form');
  const multiStep = new MultiStepForm('#registration-form', {
    validateOnNext: true,
    showStepIndicator: true
  });
  multiStep.setValidator(validator);

  new PasswordStrengthMeter('#password', '.password-strength-meter');
  new FormAutoSave('#registration-form', { 
    storageKey: 'registration_draft' 
  });
</script>
`;

/* ============================================================
   3. FORM WITH CONDITIONAL FIELDS
   ============================================================ */

HTML_CONDITIONAL_EXAMPLE = `
<form id="job-application-form">
  <div class="form-group">
    <label for="employment_type" class="required">Тип занятости</label>
    <select 
      id="employment_type" 
      name="employment_type" 
      class="form-select"
      data-validate="required"
    >
      <option value="">-- Выберите --</option>
      <option value="full_time">Полный рабочий день</option>
      <option value="part_time">Неполный рабочий день</option>
      <option value="freelance">Фриланс</option>
      <option value="other">Другое</option>
    </select>
    <div class="invalid-feedback"></div>
  </div>

  <!-- Show only if part_time is selected -->
  <div class="form-group" data-show-if="employment_type:part_time">
    <label for="hours_per_week">Часов в неделю</label>
    <input 
      type="number" 
      id="hours_per_week" 
      name="hours_per_week" 
      class="form-control"
      data-validate="number"
      placeholder="20-30"
    />
    <div class="invalid-feedback"></div>
  </div>

  <!-- Show only if freelance is selected -->
  <div class="form-group" data-show-if="employment_type:freelance">
    <label for="rate">Почасовая ставка ($)</label>
    <input 
      type="number" 
      id="rate" 
      name="rate" 
      class="form-control"
      data-validate="number"
      placeholder="0.00"
    />
    <div class="invalid-feedback"></div>
  </div>

  <!-- Show only if other is selected -->
  <div class="form-group" data-show-if="employment_type:other">
    <label for="other_type">Уточните</label>
    <input 
      type="text" 
      id="other_type" 
      name="other_type" 
      class="form-control"
      data-validate="required"
      placeholder="Опишите тип занятости"
    />
    <div class="invalid-feedback"></div>
  </div>

  <div class="form-group">
    <label for="start_date">Желаемая дата начала</label>
    <input 
      type="date" 
      id="start_date" 
      name="start_date" 
      class="form-control"
    />
  </div>

  <button type="submit" class="btn btn-primary">Отправить заявку</button>
</form>

<script>
  const validator = new FormValidator('#job-application-form');
  const conditional = new ConditionalFields('#job-application-form');
</script>
`;

/* ============================================================
   4. FORM WITH FIELD DEPENDENCIES
   ============================================================ */

HTML_DEPENDENCIES_EXAMPLE = `
<form id="shipping-form">
  <div class="form-group">
    <label for="shipping_method" class="required">Способ доставки</label>
    <select 
      id="shipping_method" 
      name="shipping_method" 
      class="form-select"
      data-validate="required"
    >
      <option value="">-- Выберите --</option>
      <option value="standard">Стандартная (5-7 дней)</option>
      <option value="express">Экспресс (1-2 дня)</option>
      <option value="pickup">Самовывоз из офиса</option>
    </select>
    <div class="invalid-feedback"></div>
  </div>

  <!-- Depends on shipping_method -->
  <div class="form-group" data-depends-on="shipping_method" data-dependent-action="enable">
    <label for="tracking">Отслеживание посылки</label>
    <input 
      type="text" 
      id="tracking" 
      name="tracking" 
      class="form-control"
      disabled
      placeholder="Будет заполнено автоматически"
    />
  </div>

  <!-- Depends on shipping_method -->
  <div class="form-group" data-depends-on="shipping_method" data-dependent-action="show">
    <label for="delivery_date">Ожидаемая дата доставки</label>
    <input 
      type="date" 
      id="delivery_date" 
      name="delivery_date" 
      class="form-control"
      disabled
    />
  </div>

  <div class="form-group">
    <label for="address">Адрес доставки</label>
    <textarea 
      id="address" 
      name="address" 
      class="form-control"
      rows="3"
      data-validate="required"
      placeholder="Полный адрес"
    ></textarea>
    <div class="invalid-feedback"></div>
  </div>

  <button type="submit" class="btn btn-primary">Подтвердить доставку</button>
</form>

<script>
  const validator = new FormValidator('#shipping-form');
  const dependencies = new FieldDependencies('#shipping-form');
</script>
`;

/* ============================================================
   5. FORM WITH INLINE VALIDATION
   ============================================================ */

HTML_INLINE_VALIDATION_EXAMPLE = `
<form id="domain-form">
  <div class="form-group">
    <label for="domain" class="required">Доменное имя</label>
    <input 
      type="text" 
      id="domain" 
      name="domain" 
      class="form-control"
      data-validate="required"
      placeholder="example.com"
    />
    <div class="invalid-feedback"></div>
  </div>

  <div class="form-group">
    <label for="username" class="required">Имя пользователя</label>
    <input 
      type="text" 
      id="username" 
      name="username" 
      class="form-control"
      data-validate="required|username"
      placeholder="username123"
    />
    <div class="invalid-feedback"></div>
  </div>

  <button type="submit" class="btn btn-primary">Зарегистрировать</button>
</form>

<script>
  const validator = new FormValidator('#domain-form');

  // Inline validator for domain availability
  new InlineValidationFeedback('#domain', (value) => {
    if (!value) return { isValid: false, message: 'Введите доменное имя' };
    
    // Simple check: just check if it looks like a domain
    const domainRegex = /^([a-z0-9]+(-[a-z0-9]+)*\\.)+[a-z]{2,}$/i;
    if (domainRegex.test(value)) {
      return { isValid: true, message: 'Формат валидный' };
    }
    return { isValid: false, message: 'Некорректный формат домена' };
  });

  // Inline validator for username availability (simulated)
  new InlineValidationFeedback('#username', (value) => {
    if (!value) return { isValid: false, message: 'Введите имя пользователя' };
    
    // Simulate API check
    const taken = ['admin', 'root', 'user', 'test']; // Reserved names
    if (taken.includes(value.toLowerCase())) {
      return { isValid: false, message: 'Имя уже занято' };
    }
    return { isValid: true, message: 'Имя доступно!' };
  });
</script>
`;

export { 
  HTML_PROGRESS_EXAMPLE, 
  HTML_MULTISTEP_EXAMPLE, 
  HTML_CONDITIONAL_EXAMPLE,
  HTML_DEPENDENCIES_EXAMPLE,
  HTML_INLINE_VALIDATION_EXAMPLE
};
