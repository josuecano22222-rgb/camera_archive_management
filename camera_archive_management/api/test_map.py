from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from camera_archive_management.api import map as map_api


class TestMapEndpoint(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.original_user = frappe.session.user
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, self.original_user)

	def test_map_requires_camera_read_permission(self):
		frappe.set_user("map-reader-without-access@example.invalid")
		with patch.object(frappe, "has_permission", return_value=False) as has_permission:
			with self.assertRaises(frappe.PermissionError):
				map_api.map_payload()
		has_permission.assert_called_once_with("Camera", "read")

	def test_map_rejects_malformed_filter_names(self):
		with self.assertRaises(frappe.ValidationError):
			map_api.map_payload(camera="x" * 141)
		with self.assertRaises(frappe.ValidationError):
			map_api.map_payload(vehicle="")

	def test_map_does_not_require_place_permission(self):
		with patch.object(frappe, "has_permission", return_value=True) as has_permission, patch.object(
			frappe, "get_list", return_value=[]
		):
			result = map_api.map_payload()
		self.assertEqual(result["cameras"], [])
		self.assertEqual(result["movements"], [])
		checked_doctypes = [call.args[0] for call in has_permission.call_args_list]
		self.assertIn("Camera", checked_doctypes)
		self.assertNotIn("Place", checked_doctypes)
