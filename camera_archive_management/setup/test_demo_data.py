from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from camera_archive_management.setup import demo_data


class TestDemoDataSafety(FrappeTestCase):
	def test_disabled_flag_returns_a_clear_refusal_without_database_writes(self):
		with (
			patch.object(frappe, "conf", frappe._dict(camera_archive_allow_demo_data=False)),
			patch.object(frappe, "session", frappe._dict(user="Administrator")),
			patch.object(frappe.db, "count") as count,
		):
			created = demo_data.create_demo_scenario()
			deleted = demo_data.delete_demo_scenario()

		self.assertFalse(created["created"])
		self.assertIn("camera_archive_allow_demo_data=true", created["reason"])
		self.assertFalse(deleted["deleted"])
		self.assertIn("camera_archive_allow_demo_data=true", deleted["reason"])
		count.assert_not_called()

	def test_production_site_allows_explicit_opt_in_for_authorized_operator(self):
		with (
			patch.object(frappe, "conf", frappe._dict(camera_archive_allow_demo_data=True)),
			patch.object(frappe, "session", frappe._dict(user="Administrator")),
		):
			self.assertIsNone(demo_data._guard_demo_generation())
