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
