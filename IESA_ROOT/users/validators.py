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
