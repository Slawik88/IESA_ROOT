"""REMOTE_ADDR comes from DigitalOcean's do-connecting-ip, never from a client-sent X-Forwarded-For."""
from django.test import RequestFactory, SimpleTestCase

from users import antispam
from users.middleware import RealClientIPMiddleware


class RealClientIPTests(SimpleTestCase):
    def _ip(self, **meta):
        seen = {}
        request = RequestFactory().get('/', **meta)
        RealClientIPMiddleware(lambda r: seen.setdefault('ip', antispam.client_ip(r)))(request)
        return seen['ip']

    def test_do_header_wins_over_spoofed_forwarded_for(self):
        self.assertEqual(self._ip(HTTP_DO_CONNECTING_IP='198.51.100.7', HTTP_X_FORWARDED_FOR='203.0.113.77',
                                  REMOTE_ADDR='203.0.113.77'), '198.51.100.7')

    def test_without_do_header_remote_addr_is_kept(self):
        self.assertEqual(self._ip(REMOTE_ADDR='10.0.0.5', HTTP_X_FORWARDED_FOR='203.0.113.77'), '10.0.0.5')

    def test_asgi_scope_exact_header_last_value_and_validation(self):
        def run(headers, remote='10.0.0.5'):
            request = RequestFactory().get('/', REMOTE_ADDR=remote)
            request.scope = {'headers': headers}
            RealClientIPMiddleware(lambda r: None)(request)
            return request.META['REMOTE_ADDR']
        # a client-sent underscore twin is not the proxy's header
        self.assertEqual(run([(b'do_connecting_ip', b'203.0.113.9')]), '10.0.0.5')
        self.assertEqual(run([(b'do-connecting-ip', b'203.0.113.9, 198.51.100.7')]), '198.51.100.7')
        self.assertEqual(run([(b'do-connecting-ip', b'not-an-ip')]), '10.0.0.5')

    def test_middleware_runs_first(self):
        from django.conf import settings
        self.assertEqual(settings.MIDDLEWARE[0], 'users.middleware.RealClientIPMiddleware')
