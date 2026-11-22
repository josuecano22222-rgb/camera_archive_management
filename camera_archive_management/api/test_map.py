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

	def test_custom_map_coords_requires_read_permission(self):
		with patch.object(frappe, "has_permission", return_value=False) as has_permission:
			with self.assertRaises(frappe.PermissionError):
				map_api.get_custom_map_coords("Geo Boundary")
		has_permission.assert_called_once_with("Geo Boundary", "read")

	def test_custom_map_coords_adapts_centroids_and_skips_invalid_pairs(self):
		rows = [
			frappe._dict(name="BOUNDARY-1", centroid_lat="52.37", centroid_lon="4.89"),
			frappe._dict(name="BOUNDARY-2", centroid_lat="91", centroid_lon="4.89"),
			frappe._dict(name="BOUNDARY-3", centroid_lat=None, centroid_lon=None),
		]
		filters = '[["Geo Boundary","label","like","%Central%"]]'
		with patch.object(frappe, "has_permission", return_value=True), patch.object(
			frappe, "get_list", return_value=rows
		) as get_list:
			result = map_api.get_custom_map_coords("Geo Boundary", filters=filters)

		self.assertEqual(result["type"], "FeatureCollection")
		self.assertEqual(len(result["features"]), 1)
		self.assertEqual(result["features"][0]["properties"]["name"], "BOUNDARY-1")
		self.assertEqual(result["features"][0]["geometry"]["coordinates"], [4.89, 52.37])
		self.assertEqual(get_list.call_args.kwargs["filters"], [["Geo Boundary", "label", "like", "%Central%"]])

	def test_custom_map_coords_uses_motion_event_snapshots(self):
		row = frappe._dict(name="MOT-1", latitude_snapshot="52.37", longitude_snapshot="4.89")
		with patch.object(frappe, "has_permission", return_value=True), patch.object(
			frappe, "get_list", return_value=[row]
		) as get_list:
			result = map_api.get_custom_map_coords("Motion Event")

		self.assertEqual(result["features"][0]["properties"]["name"], "MOT-1")
		self.assertEqual(get_list.call_args.kwargs["fields"], ["name", "latitude_snapshot", "longitude_snapshot"])

	def test_custom_map_coords_rejects_unsupported_doctypes(self):
		with self.assertRaises(frappe.ValidationError):
			map_api.get_custom_map_coords("Camera Credential")
