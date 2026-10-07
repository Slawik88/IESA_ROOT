"""Authentication backend that is forgiving about what phones type into the login form."""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class CaseInsensitiveModelBackend(ModelBackend):
    """Log in by username (any letter case) or by e-mail address.

    Phone keyboards capitalise the first letter of the username field and
    password managers fill the e-mail, so the exact-match lookup of Django's
    default backend rejects correct credentials on mobile. An exact username
    match always wins; the case-insensitive and e-mail fallbacks are used only
    when they resolve to exactly one account, so an ambiguous identifier never
    logs anyone in.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        user_model = get_user_model()
        if username is None:
            username = kwargs.get(user_model.USERNAME_FIELD)
        if username is None or password is None:
            return None

        user = self._find_user(user_model, username.strip())
        if user is None:
            # Run the hasher anyway so timing doesn't reveal which identifiers exist.
            user_model().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    @staticmethod
    def _find_user(user_model, identifier):
        if not identifier:
            return None
        manager = user_model._default_manager
        try:
            return manager.get(**{user_model.USERNAME_FIELD: identifier})
        except user_model.DoesNotExist:
            pass

        for lookup in (f'{user_model.USERNAME_FIELD}__iexact', 'email__iexact'):
            if lookup == 'email__iexact' and '@' not in identifier:
                continue
            matches = list(manager.filter(**{lookup: identifier})[:2])
            if len(matches) == 1:
                return matches[0]
        return None
