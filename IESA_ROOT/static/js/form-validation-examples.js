/**
 * TIER 5: Form Validation & Auto-Save Usage Examples
 * 
 * This file demonstrates how to use the form validation system
 * in your Django templates and forms.
 */

/* ============================================================
   1. BASIC VALIDATION EXAMPLE
   ============================================================ */

HTML_EXAMPLE_1 = `
<form id="register-form">
  <!-- Required field -->
  <div class="form-group">
    <label for="username" class="required">Имя пользователя</label>
    <input 
      type="text" 
      id="username" 
      name="username" 
      class="form-control"
      data-validate="required|username"
      placeholder="3-20 символов"
      autocomplete="username"
    />
    <div class="invalid-feedback"></div>
  </div>

  <!-- Email field -->
  <div class="form-group">
    <label for="email" class="required">Email</label>
    <input 
      type="email" 
      id="email" 
      name="email" 
      class="form-control"
      data-validate="required|email"
      placeholder="your@email.com"
      autocomplete="email"
    />
    <div class="invalid-feedback"></div>
  </div>

  <!-- Password field -->
  <div class="form-group">
    <label for="password" class="required">Пароль</label>
    <input 
      type="password" 
      id="password" 
      name="password" 
      class="form-control"
      data-validate="required|password"
      placeholder="Минимум 8 символов"
    />
    <div class="invalid-feedback"></div>
    
    <!-- Password strength meter -->
    <div class="password-strength-meter">
      <div class="strength-bar"></div>
      <span class="strength-text">Вводите пароль</span>
    </div>
  </div>

  <!-- Confirm password -->
  <div class="form-group">
    <label for="password_confirm" class="required">Подтвердить пароль</label>
    <input 
      type="password" 
      id="password_confirm" 
      name="password_confirm" 
      class="form-control"
      data-validate="required|match:password"
      placeholder="Повторите пароль"
    />
    <div class="invalid-feedback"></div>
  </div>

  <button type="submit" class="btn btn-primary">Зарегистрироваться</button>
</form>

<script>
  // Initialize validator
  const validator = new FormValidator('#register-form', {
    debounceDelay: 300,
    showErrorsOnBlur: true,
    showSuccessState: true,
    validateOnInput: true,
    customMessages: {
      username: 'Используйте только буквы, цифры и подчеркивание'
    }
  });

  // Initialize password strength meter
  new PasswordStrengthMeter('#password', '.password-strength-meter');

  // Initialize auto-save
  const autoSave = new FormAutoSave('#register-form', {
    storageKey: 'register_form_draft',
    debounceDelay: 1000
  });

  // Form submission
  document.querySelector('#register-form').addEventListener('submit', function(e) {
    if (!validator.isValid()) {
      e.preventDefault();
      console.log('Form has errors:', validator.getErrors());
    }
  });
</script>
`;

/* ============================================================
   2. ADVANCED VALIDATION WITH CUSTOM RULES
   ============================================================ */

HTML_EXAMPLE_2 = `
<form id="profile-form">
  <!-- Phone number -->
  <div class="form-group">
    <label for="phone">Номер телефона</label>
    <input 
      type="tel" 
      id="phone" 
      name="phone" 
      class="form-control"
      data-validate="phone"
      placeholder="+7 (999) 123-45-67"
    />
    <div class="invalid-feedback"></div>
  </div>

  <!-- Website URL -->
  <div class="form-group">
    <label for="website">Сайт (опционально)</label>
    <input 
      type="url" 
      id="website" 
      name="website" 
      class="form-control"
      data-validate="url"
      placeholder="https://example.com"
    />
    <div class="invalid-feedback"></div>
  </div>

  <!-- Bio with min/max length -->
  <div class="form-group">
    <label for="bio">Биография</label>
    <textarea 
      id="bio" 
      name="bio" 
      class="form-control"
      rows="4"
      data-validate="minLength:10|maxLength:500"
      placeholder="Расскажите о себе (10-500 символов)"
    ></textarea>
    <div class="invalid-feedback"></div>
    <small class="text-muted">10-500 символов</small>
  </div>

  <!-- Accept terms checkbox -->
  <div class="form-check">
    <input 
      type="checkbox" 
      id="terms" 
      name="terms" 
      class="form-check-input"
      data-validate="required"
    />
    <label for="terms" class="form-check-label">
      Я принимаю условия использования <span class="required">*</span>
    </label>
    <div class="invalid-feedback d-block"></div>
  </div>

  <button type="submit" class="btn btn-primary">Сохранить профиль</button>
</form>

<script>
  const validator = new FormValidator('#profile-form', {
    customMessages: {
      minLength: 'Минимум {{min}} символов для этого поля',
      maxLength: 'Максимум {{max}} символов для этого поля'
    }
  });

  const autoSave = new FormAutoSave('#profile-form', {
    storageKey: 'profile_form_draft'
  });
</script>
`;

/* ============================================================
   3. COLLAPSIBLE FORM SECTIONS
   ============================================================ */

HTML_EXAMPLE_3 = `
<form id="settings-form">
  <!-- Account Settings - Collapsible -->
  <div class="form-field-group" data-group-type="collapsible">
    <button type="button" class="group-toggle">
      <span>Настройки аккаунта</span>
    </button>
    <div class="group-content">
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
        <label for="phone">Номер телефона</label>
        <input 
          type="tel" 
          id="phone" 
          name="phone" 
          class="form-control"
          data-validate="phone"
        />
        <div class="invalid-feedback"></div>
      </div>
    </div>
  </div>

  <!-- Privacy Settings - Collapsible -->
  <div class="form-field-group" data-group-type="collapsible">
    <button type="button" class="group-toggle">
      <span>Настройки конфиденциальности</span>
    </button>
    <div class="group-content">
      <div class="form-check">
        <input 
          type="checkbox" 
          id="public_profile" 
          name="public_profile" 
          class="form-check-input"
          checked
        />
        <label for="public_profile" class="form-check-label">
          Публичный профиль
        </label>
      </div>

      <div class="form-check">
        <input 
          type="checkbox" 
          id="show_email" 
          name="show_email" 
          class="form-check-input"
        />
        <label for="show_email" class="form-check-label">
          Показывать email
        </label>
      </div>

      <div class="form-check">
        <input 
          type="checkbox" 
          id="allow_messages" 
          name="allow_messages" 
          class="form-check-input"
          checked
        />
        <label for="allow_messages" class="form-check-label">
          Разрешить сообщения
        </label>
      </div>
    </div>
  </div>

  <button type="submit" class="btn btn-primary mt-3">Сохранить</button>
</form>

<script>
  new FormFieldGroup('[data-group-type="collapsible"]');
  new FormValidator('#settings-form');
  new FormAutoSave('#settings-form', { storageKey: 'settings_form_draft' });
</script>
`;

/* ============================================================
   4. TABBED FORM SECTIONS
   ============================================================ */

HTML_EXAMPLE_4 = `
<form id="event-form">
  <div class="form-field-group" data-group-type="tabs">
    <div class="group-tabs">
      <button type="button" class="group-tab active" data-target="#basic-info">
        Основная информация
      </button>
      <button type="button" class="group-tab" data-target="#location">
        Место проведения
      </button>
      <button type="button" class="group-tab" data-target="#details">
        Детали события
      </button>
    </div>

    <!-- Tab 1: Basic Info -->
    <div id="basic-info" class="group-pane active">
      <div class="form-group">
        <label for="title" class="required">Название события</label>
        <input 
          type="text" 
          id="title" 
          name="title" 
          class="form-control"
          data-validate="required|minLength:5"
          placeholder="Название события"
        />
        <div class="invalid-feedback"></div>
      </div>

      <div class="form-group">
        <label for="description" class="required">Описание</label>
        <textarea 
          id="description" 
          name="description" 
          class="form-control"
          rows="4"
          data-validate="required|minLength:20"
          placeholder="Описание события"
        ></textarea>
        <div class="invalid-feedback"></div>
      </div>
    </div>

    <!-- Tab 2: Location -->
    <div id="location" class="group-pane">
      <div class="form-group">
        <label for="city" class="required">Город</label>
        <input 
          type="text" 
          id="city" 
          name="city" 
          class="form-control"
          data-validate="required"
          placeholder="Город"
        />
        <div class="invalid-feedback"></div>
      </div>

      <div class="form-group">
        <label for="address" class="required">Адрес</label>
        <input 
          type="text" 
          id="address" 
          name="address" 
          class="form-control"
          data-validate="required"
          placeholder="Полный адрес"
        />
        <div class="invalid-feedback"></div>
      </div>
    </div>

    <!-- Tab 3: Details -->
    <div id="details" class="group-pane">
      <div class="form-group">
        <label for="date" class="required">Дата и время</label>
        <input 
          type="datetime-local" 
          id="date" 
          name="date" 
          class="form-control"
          data-validate="required"
        />
        <div class="invalid-feedback"></div>
      </div>

      <div class="form-group">
        <label for="max_guests">Максимум гостей</label>
        <input 
          type="number" 
          id="max_guests" 
          name="max_guests" 
          class="form-control"
          data-validate="number"
          placeholder="0 - неограниченно"
        />
        <div class="invalid-feedback"></div>
      </div>
    </div>
  </div>

  <button type="submit" class="btn btn-primary mt-3">Создать событие</button>
</form>

<script>
  new FormFieldGroup('[data-group-type="tabs"]');
  new FormValidator('#event-form');
  new FormAutoSave('#event-form', { storageKey: 'event_form_draft' });
</script>
`;

/* ============================================================
   5. ACCORDION FORM SECTIONS
   ============================================================ */

HTML_EXAMPLE_5 = `
<form id="product-form">
  <div class="form-field-group" data-group-type="accordion">
    <!-- Section 1 -->
    <div class="group-item">
      <div class="group-header">Основная информация о товаре</div>
      <div class="group-content">
        <div class="form-group">
          <label for="name" class="required">Название</label>
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
          <label for="sku">SKU (Артикул)</label>
          <input 
            type="text" 
            id="sku" 
            name="sku" 
            class="form-control"
            placeholder="Уникальный артикул"
          />
        </div>
      </div>
    </div>

    <!-- Section 2 -->
    <div class="group-item">
      <div class="group-header">Цена и запасы</div>
      <div class="group-content">
        <div class="form-group">
          <label for="price" class="required">Цена</label>
          <input 
            type="number" 
            id="price" 
            name="price" 
            class="form-control"
            data-validate="required|number"
            placeholder="0.00"
          />
          <div class="invalid-feedback"></div>
        </div>

        <div class="form-group">
          <label for="stock">Количество в запасе</label>
          <input 
            type="number" 
            id="stock" 
            name="stock" 
            class="form-control"
            data-validate="number"
            placeholder="0"
          />
        </div>
      </div>
    </div>

    <!-- Section 3 -->
    <div class="group-item">
      <div class="group-header">Описание и категория</div>
      <div class="group-content">
        <div class="form-group">
          <label for="description">Описание товара</label>
          <textarea 
            id="description" 
            name="description" 
            class="form-control"
            rows="4"
            data-validate="maxLength:1000"
          ></textarea>
          <div class="invalid-feedback"></div>
        </div>

        <div class="form-group">
          <label for="category">Категория</label>
          <select 
            id="category" 
            name="category" 
            class="form-select"
            data-validate="required"
          >
            <option value="">-- Выберите категорию --</option>
            <option value="electronics">Электроника</option>
            <option value="clothing">Одежда</option>
            <option value="books">Книги</option>
          </select>
          <div class="invalid-feedback"></div>
        </div>
      </div>
    </div>
  </div>

  <button type="submit" class="btn btn-success mt-3">Добавить товар</button>
</form>

<script>
  new FormFieldGroup('[data-group-type="accordion"]');
  new FormValidator('#product-form');
  new FormAutoSave('#product-form', { storageKey: 'product_form_draft' });
</script>
`;

/* ============================================================
   6. VALIDATION RULES REFERENCE
   ============================================================ */

VALIDATION_RULES = `
Доступные правила валидации (data-validate):

1. required
   - Проверяет, не пусто ли поле
   - Пример: data-validate="required"

2. email
   - Проверяет формат email
   - Пример: data-validate="email"

3. phone
   - Проверяет формат телефона (минимум 10 символов)
   - Пример: data-validate="phone"

4. password
   - Проверяет минимум 8 символов
   - Пример: data-validate="password"

5. passwordStrong
   - Проверяет: прописные, строчные, цифры, спец.символы, минимум 8 символов
   - Пример: data-validate="passwordStrong"

6. username
   - Проверяет: 3-20 символов, буквы, цифры, подчеркивание
   - Пример: data-validate="username"

7. url
   - Проверяет валидность URL
   - Пример: data-validate="url"

8. number
   - Проверяет, является ли значение числом
   - Пример: data-validate="number"

9. minLength:n
   - Проверяет минимум n символов
   - Пример: data-validate="minLength:5"

10. maxLength:n
    - Проверяет максимум n символов
    - Пример: data-validate="maxLength:100"

11. match:fieldName
    - Проверяет совпадение с другим полем
    - Пример: data-validate="match:password"

12. Комбинирование правил (через |)
    - Пример: data-validate="required|email|minLength:5"
`;

/* ============================================================
   7. JAVASCRIPT API REFERENCE
   ============================================================ */

API_REFERENCE = `
// ===== FormValidator =====

// Инициализация
const validator = new FormValidator('#form-id', {
  debounceDelay: 300,          // Задержка перед валидацией при вводе
  showErrorsOnBlur: true,      // Показывать ошибки при потере фокуса
  showSuccessState: true,      // Показывать иконку успеха
  validateOnInput: true,       // Валидировать при вводе
  customMessages: {}           // Пользовательские сообщения об ошибках
});

// Методы
validator.validateAll()        // Валидировать все поля
validator.validateField(name)  // Валидировать одно поле
validator.isValid()            // Проверить, форма ли валидна
validator.getErrors()          // Получить объект с ошибками
validator.reset()              // Очистить форму и ошибки

// ===== FormAutoSave =====

// Инициализация
const autoSave = new FormAutoSave('#form-id', {
  storageKey: 'form_autosave_key',  // Ключ для localStorage
  debounceDelay: 1000               // Задержка перед сохранением
});

// Методы
autoSave.saveData()            // Сохранить данные в localStorage
autoSave.restoreData()         // Восстановить данные из localStorage
autoSave.clearData()           // Очистить сохраненные данные
autoSave.getData()             // Получить сохраненные данные

// ===== PasswordStrengthMeter =====

// Инициализация
const meter = new PasswordStrengthMeter(
  '#password-input',           // Селектор поля пароля
  '.meter-container'           // Селектор контейнера метра
);

// ===== FormFieldGroup =====

// Инициализация
new FormFieldGroup('[data-group-type="collapsible"]');
new FormFieldGroup('[data-group-type="tabs"]');
new FormFieldGroup('[data-group-type="accordion"]');
`;

export { HTML_EXAMPLE_1, HTML_EXAMPLE_2, HTML_EXAMPLE_3, HTML_EXAMPLE_4, HTML_EXAMPLE_5 };
