from __future__ import annotations

from unittest.mock import call, patch

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

	def test_core_country_boundaries_use_only_authorized_bundled_data(self):
		boundary = frappe._dict(name="BOUNDARY-1", boundary_code="JOR", label="Jordan")
		geometry = '{"type":"Polygon","coordinates":[[[35.0,29.0],[36.0,29.0],[36.0,33.5],[35.0,33.5],[35.0,29.0]]]}'
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe.db, "get_value", return_value="natural-earth-admin0-110m"),
			patch.object(
				frappe,
				"get_all",
				side_effect=[[boundary], [frappe._dict(parent=boundary.name, geojson=geometry)]],
			),
		):
			result = map_api.get_core_country_boundaries()
		self.assertEqual(result["features"][0]["properties"]["label"], "Jordan")
		self.assertEqual(result["features"][0]["geometry"]["type"], "Polygon")

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

	def test_camera_main_image_is_returned_from_embedded_gallery(self):
		camera = frappe._dict(
			name="CAM-0001",
			camera_name="North Gate",
			status="Active",
			camera_type="PTZ",
			area="North",
			address="",
			latitude="52.37",
			longitude="4.89",
			geo_admin_area=None,
			geo_boundary=None,
			primary_image="/private/files/north-gate.jpg",
			is_demo_record=0,
			camera_photos_json='[{"url":"/private/files/north-gate.jpg","caption":"Main","description":"","is_primary":true,"sort_order":0}]',
		)
		file_doc = frappe._dict(
			name="FILE-1", file_url=camera.primary_image, is_private=0
		)
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_list", side_effect=[[camera], []]),
			patch.object(frappe, "get_all", return_value=[file_doc]),
		):
			result = map_api.map_payload(camera=camera.name)

		self.assertEqual(result["cameras"][0]["photos"][0]["url"], camera.primary_image)
		self.assertTrue(result["cameras"][0]["photos"][0]["primary"])
		self.assertEqual(result["cameras"][0]["photos"][0]["caption"], "Main")

	def test_map_hides_synthetic_records_by_default_and_can_include_them_explicitly(self):
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_list", side_effect=[[], []]) as get_list,
		):
			map_api.map_payload()
			map_api.map_payload(include_demo="1")

		camera_filters = [call.kwargs["filters"] for call in get_list.call_args_list if call.args[0] == "Camera"]
		event_filters = [call.kwargs["filters"] for call in get_list.call_args_list if call.args[0] == "Motion Event"]
		self.assertEqual(camera_filters[0], {"status": "Active", "is_demo_record": 0})
		self.assertEqual(camera_filters[1], {"status": "Active"})
		self.assertEqual(event_filters[0], {"is_demo_record": 0})
		self.assertEqual(event_filters[1], {})

	def test_map_rejects_invalid_synthetic_data_flag(self):
		with self.assertRaises(frappe.ValidationError):
			map_api.map_payload(include_demo="yes")

	def test_custom_map_coords_rejects_unsupported_doctypes(self):
		with self.assertRaises(frappe.ValidationError):
			map_api.get_custom_map_coords("Camera Credential")
