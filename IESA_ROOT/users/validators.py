from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
import re


class UppercaseValidator:
    """
    Validate that the password contains at least one uppercase letter.
    """
    def validate(self, password, user=None):
        if not re.search(r'[A-Z]', password):
            raise ValidationError(
                _("Password must contain at least one uppercase letter (A-Z)."),
                code='password_no_upper',
            )

    def get_help_text(self):
        return _("Your password must contain at least one uppercase letter (A-Z).")


class SpecialCharacterValidator:
    """
    Validate that the password contains at least one special character.
    """
    def validate(self, password, user=None):
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            raise ValidationError(
                _("Password must contain at least one special character (!@#$%^&*(),.?\":{}|<>)."),
                code='password_no_special',
            )

    def get_help_text(self):
        return _("Your password must contain at least one special character (!@#$%^&*(),.?\":{}|<>).")


# Phone number validator
PHONE_ALLOWED_PATTERN = re.compile(r'^[0-9\s\-+()]{7,20}$')


def validate_phone_number(value: str):
    """Validate phone number with permissive international format.
    Allows digits, spaces, plus, dashes and parentheses. Length 7-20.
    """
    if not value:
        return
    cleaned = value.strip()
    if not PHONE_ALLOWED_PATTERN.match(cleaned):
        raise ValidationError(
            _("Некорректный номер телефона. Допустимы цифры, пробелы, '+', '-', '()'."),
            code='invalid_phone_number'
        )


# Social links validators
def validate_github_url(value: str):
    """Validate GitHub profile URL"""
    if not value:
        return
    cleaned = value.strip()
    if not re.match(r'^https?://(www\.)?github\.com/[\w-]+/?$', cleaned, re.IGNORECASE):
        raise ValidationError(
            _("Введите корректную ссылку на профиль GitHub (например: https://github.com/username)"),
            code='invalid_github_url'
        )


def validate_discord_url(value: str):
    """Validate Discord username (username or username#1234)"""
    if not value:
        return
    cleaned = value.strip()
    # Поддержка как старого формата (username#1234), так и нового (username)
    if not re.match(r'^[\w]{2,32}(#\d{4})?$', cleaned):
        raise ValidationError(
            _("Введите корректное имя Discord (например: username или username#1234)"),
            code='invalid_discord'
        )


def validate_telegram_url(value: str):
    """Validate Telegram username or URL"""
    if not value:
        return
    cleaned = value.strip()
    # Разрешаем как @username, так и полные ссылки t.me/username
    if not re.match(r'^(@[\w]{5,32}|(https?://)?(t\.me|telegram\.me)/[\w]{5,32})$', cleaned, re.IGNORECASE):
        raise ValidationError(
            _("Введите корректную ссылку Telegram (например: @username или t.me/username)"),
            code='invalid_telegram'
        )


def validate_website_url(value: str):
    """Validate website URL"""
    if not value:
        return
    cleaned = value.strip()
    # Более гибкое регулярное выражение для URL с query параметрами, якорями и специальными символами
    if not re.match(r'^https?://[\w\-.]+(?::\d+)?(?:/[\w\-._~:/?#\[\]@!$&\'()*+,;=%]*)?$', cleaned, re.IGNORECASE):
        raise ValidationError(
            _("Введите корректную ссылку на сайт (должна начинаться с http:// или https://)"),
            code='invalid_website_url'
        )


def validate_other_links(value: str):
    """Validate other links (one per line)"""
    if not value:
        return
    lines = value.strip().split('\n')
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        # Каждая строка должна быть валидной ссылкой (более гибкая валидация)
        if not re.match(r'^https?://[\w\-.]+(?::\d+)?(?:/[\w\-._~:/?#\[\]@!$&\'()*+,;=%]*)?$', line, re.IGNORECASE):
            raise ValidationError(
                _(f"Строка {i}: '{line}' - некорректная ссылка. Используйте формат http://... или https://..."),
                code='invalid_other_link'
            )
