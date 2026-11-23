from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from camera_archive_management.api.workspace import get_workspace_summary


class TestWorkspaceSummary(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.original_user = frappe.session.user
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, self.original_user)

	def test_summary_is_permission_aware_and_returns_chart_series(self):
		def get_list(doctype, **kwargs):
			fields = kwargs.get("fields", [])
			if fields == ["count(name) as total"]:
				return [frappe._dict(total={"Camera": 12, "Motion Event": 48, "CAM Vehicle": 7}.get(doctype, 3))]
			if fields == ["status", "count(name) as total"]:
				return [frappe._dict(status="Active", total=10), frappe._dict(status="Inactive", total=2)]
			if fields == ["motion_type", "count(name) as total"]:
				return [frappe._dict(motion_type="Entry", total=25), frappe._dict(motion_type="Exit", total=23)]
			if fields == ["DATE(detected_at) as day", "count(name) as total"]:
				return [frappe._dict(day="2026-11-22", total=8)]
			if fields == ["vehicle", "count(name) as total"]:
				return [frappe._dict(vehicle="VEH-1", total=18)]
			if fields == ["name", "vehicle_name"]:
				return [frappe._dict(name="VEH-1", vehicle_name="Blue Van")]
			return []

		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_list", side_effect=get_list),
		):
			result = get_workspace_summary()

		self.assertEqual(result["counts"]["cameras"], 12)
		self.assertEqual(result["counts"]["movements"], 48)
		self.assertEqual(result["camera_status"][0], {"label": "Active", "value": 10})
		self.assertEqual(result["movement_types"][1], {"label": "Exit", "value": 23})
		self.assertEqual(result["daily_movements"][0], {"label": "2026-11-22", "value": 8})
		self.assertEqual(result["top_vehicles"][0], {"label": "Blue Van", "value": 18})

	def test_counts_skip_doctypes_without_read_permission(self):
		with patch.object(frappe, "has_permission", return_value=False), patch.object(frappe, "get_list") as get_list:
			result = get_workspace_summary()
		self.assertEqual(result["counts"], {})
		self.assertEqual(result["camera_status"], [])
		self.assertEqual(result["movement_types"], [])
		self.assertEqual(result["daily_movements"], [])
		self.assertEqual(result["top_vehicles"], [])
		get_list.assert_not_called()
