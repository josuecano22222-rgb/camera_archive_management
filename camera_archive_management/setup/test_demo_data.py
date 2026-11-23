from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from camera_archive_management.setup import demo_data


class TestDemoDataSafety(FrappeTestCase):
	def test_production_site_returns_a_clear_refusal_without_database_writes(self):
		with patch.object(frappe.local, "site", "frappe.com"), patch.object(frappe.db, "count") as count:
			created = demo_data.create_demo_scenario()
			deleted = demo_data.delete_demo_scenario()

		self.assertFalse(created["created"])
		self.assertIn("never allowed on the production site", created["reason"])
		self.assertFalse(deleted["deleted"])
		self.assertIn("never allowed on the production site", deleted["reason"])
		count.assert_not_called()
