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

    def test_home_exposes_logout_url(self):
        # FE57: the SPA renders a "Sign out" link under "Signed in as"; the
        # template hands it Tethys's logout route so the path isn't hard-coded.
        c = self.get_test_client()
        user = self.create_test_user(
            username='erin', password='secret', email='erin@example.com'
        )
        c.force_login(user)

        response = c.get('/apps/fimeval-gui/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'data-logout-url="/accounts/logout/"', response.content)
