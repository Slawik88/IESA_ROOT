"""Group grants work from both the User and Group sides of the relation."""
from django.contrib.auth.models import Group
from django.test import TestCase

from users.models import Partner, User


class PartnerGroupTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='group-partner')
        self.group = Group.objects.create(name='Partners')

    def test_forward_grant_creates_one_profile_and_sets_flag(self):
        self.user._is_partner_cached = False
        self.user.groups.add(self.group)
        self.user.groups.add(self.group)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_partner)
        self.assertEqual(Partner.objects.filter(user=self.user).count(), 1)
        self.assertNotIn('_is_partner_cached', self.user.__dict__)

    def test_reverse_grant_from_group_admin_initializes_every_user(self):
        other = User.objects.create_user(username='group-partner-other')
        self.group.user_set.add(self.user, other)
        for user in (self.user, other):
            user.refresh_from_db()
            self.assertTrue(user.is_partner)
            self.assertTrue(Partner.objects.filter(user=user).exists())

    def test_unrelated_group_does_not_grant_partner_access(self):
        other = Group.objects.create(name='Readers')
        other.user_set.add(self.user)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_partner)
        self.assertFalse(Partner.objects.filter(user=self.user).exists())

    def test_existing_company_profile_is_preserved_when_granting_group(self):
        Partner.objects.create(user=self.user, company_name='Existing company')
        self.user.groups.add(self.group)
        self.assertEqual(self.user.partner_profile.company_name, 'Existing company')
