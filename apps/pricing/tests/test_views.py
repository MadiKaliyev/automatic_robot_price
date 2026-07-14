from django.test import TestCase
from django.urls import reverse


class PublicViewsTests(TestCase):
    def test_dashboard_contains_search_metadata(self):
        response = self.client.get(reverse("pricing:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<meta name="description"')
        self.assertContains(response, '<link rel="canonical"')
        self.assertContains(response, 'type="application/ld+json"')
        self.assertContains(response, "Island Price Monitor")

    def test_dashboard_supports_head_requests(self):
        response = self.client.head(reverse("pricing:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")

    def test_robots_points_to_sitemap(self):
        response = self.client.get(reverse("pricing:robots"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        self.assertContains(response, "Disallow: /admin/")
        self.assertContains(response, "/sitemap.xml")

    def test_sitemap_contains_dashboard(self):
        response = self.client.get(reverse("pricing:sitemap"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xml; charset=utf-8")
        self.assertContains(response, "<loc>http://testserver/</loc>")
