from tethys_sdk.testing import TethysTestCase


class TestCase(TethysTestCase):

    def test_home_controller(self):
        c = self.get_test_client()
        user = self.create_test_user(
            username='joe', password='secret', email='joe@example.com'
        )
        c.force_login(user)

        response = c.get('/apps/fimeval-gui/')
        self.assertEqual(response.status_code, 200)

    def test_home_exposes_signed_in_username(self):
        # FE56: the SPA reads the signed-in user's name from the root element so
        # the sidebar can show "Signed in as <username>" (works with zero runs and
        # for any account, not just admin).
        c = self.get_test_client()
        user = self.create_test_user(
            username='erin', password='secret', email='erin@example.com'
        )
        c.force_login(user)

        response = c.get('/apps/fimeval-gui/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'data-username="erin"', response.content)

    def test_home_redirects_anonymous_to_login(self):
        # BE51: the SPA shell must never render for an anonymous request, so the
        # browser's Back button after sign-out cannot land on a user-less workspace.
        c = self.get_test_client()
        response = c.get('/apps/fimeval-gui/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response['Location'])

    def test_home_is_never_cached(self):
        # BE51: without no-store the browser serves the signed-in shell from its
        # cache on Back after sign-out, showing "Signed in as <user>" with no runs.
        c = self.get_test_client()
        user = self.create_test_user(
            username='kim', password='secret', email='kim@example.com'
        )
        c.force_login(user)

        response = c.get('/apps/fimeval-gui/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response.get('Cache-Control', ''))
