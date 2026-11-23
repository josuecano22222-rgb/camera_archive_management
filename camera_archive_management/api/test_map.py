from __future__ import annotations

import json
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
			importance="High",
			area="North",
			serial_number="SN-EXACT-1",
			camera_number="CAM-01",
			installation_date="2024-02-03",
			address="",
			latitude="52.370000000",
			longitude="4.8900",
			field_of_view="North entrance",
			description="Exact precision test",
			lookup_source="manual",
			lookup_confidence=1.0,
			lookup_ambiguous=0,
			lookup_resolved_at=None,
			geo_admin_area=None,
			geo_boundary=None,
			primary_image="/private/files/north-gate.jpg",
			is_demo_record=0,
			camera_photos_json='[{"url":"/private/files/north-gate.jpg","caption":"Main","description":"","is_primary":true,"sort_order":0},{"url":"/files/missing-side-view.jpg","caption":"Side view","description":"Retained when offline or missing","is_primary":false,"sort_order":1}]',
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
		self.assertEqual(result["cameras"][0]["latitude"], "52.370000000")
		self.assertEqual(result["cameras"][0]["longitude"], "4.8900")
		self.assertEqual(result["cameras"][0]["serial_number"], "SN-EXACT-1")
		self.assertEqual(result["cameras"][0]["field_of_view"], "North entrance")
		self.assertEqual(len(result["cameras"][0]["photos"]), 2)
		self.assertTrue(result["cameras"][0]["photos"][1]["unavailable"])
		self.assertEqual(result["cameras"][0]["photos"][1]["caption"], "Side view")

	def test_map_hides_synthetic_records_by_default_and_can_include_them_explicitly(self):
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_list", side_effect=[[], [], [], []]) as get_list,
		):
			map_api.map_payload()
			map_api.map_payload(include_demo="1")

		camera_filters = [call.kwargs["filters"] for call in get_list.call_args_list if call.args[0] == "Camera"]
		event_filters = [call.kwargs["filters"] for call in get_list.call_args_list if call.args[0] == "Motion Event"]
		self.assertEqual(camera_filters[0], {"status": "Active", "is_demo_record": 0})
		self.assertEqual(camera_filters[1], {"status": "Active"})
		self.assertEqual(event_filters[0], {"is_demo_record": 0})
		self.assertEqual(event_filters[1], {})

	def test_map_filters_camera_status_area_and_scopes_movements(self):
		camera = frappe._dict(
			name="CAM-AREA-1",
			camera_name="Maintenance Depot",
			status="Maintenance",
			camera_type="Fixed",
			area="AREA-1",
			address="",
			latitude="52.37",
			longitude="4.89",
			geo_admin_area=None,
			geo_boundary=None,
			primary_image=None,
			is_demo_record=0,
			camera_photos_json="[]",
		)
		event = frappe._dict(
			name="MOT-AREA-1",
			camera=camera.name,
			motion_type="Entry",
			detected_at="2026-01-01 10:00:00",
			vehicle=None,
			latitude_snapshot="52.37",
			longitude_snapshot="4.89",
			address_snapshot="",
			importance="Low",
			notes="",
			is_demo_record=0,
		)
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_list", side_effect=[[camera], [event]]) as get_list,
		):
			result = map_api.map_payload(camera_status="Maintenance", area="AREA-1")

		self.assertEqual(result["cameras"][0]["status"], "Maintenance")
		self.assertEqual(result["movements"][0]["camera"], camera.name)
		self.assertEqual(get_list.call_args_list[0].kwargs["filters"], {
			"status": "Maintenance", "area": "AREA-1", "is_demo_record": 0,
		})
		self.assertEqual(get_list.call_args_list[1].kwargs["filters"]["camera"], ["in", [camera.name]])

	def test_movement_payload_includes_camera_snapshots_and_nearby_camera_context(self):
		event = frappe._dict(
			name="MOT-CONTEXT-1", camera="CAM-1", camera_name_snapshot="Canal North",
			camera_type_snapshot="PTZ", camera_area_snapshot="AREA-1", geo_admin_area_snapshot="Amsterdam",
			motion_type="Entry", detected_at="2026-02-04 10:15:00", vehicle=None,
			latitude_snapshot="52.3700000001", longitude_snapshot="4.8900000002", address_snapshot="Canal road",
			importance="High", notes="Observed", is_demo_record=0,
		)
		nearby = frappe._dict(
			parent=event.name, camera="CAM-NEAR-1", distance_m=125.5,
			bearing_compass="NE", area="AREA-1", camera_status="Active", note="Adjacent",
		)
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_list", side_effect=[[], [event]]),
			patch.object(frappe, "get_all", return_value=[nearby]),
		):
			result = map_api.map_payload(start="2026-02-04T10:00", end="2026-02-04T11:00")

		movement = result["movements"][0]
		self.assertEqual(movement["camera_name"], "Canal North")
		self.assertEqual(movement["camera_type"], "PTZ")
		self.assertEqual(movement["camera_area"], "AREA-1")
		self.assertEqual(movement["latitude"], "52.3700000001")
		self.assertEqual(movement["longitude"], "4.8900000002")
		self.assertEqual(movement["nearby_cameras"][0]["camera"], "CAM-NEAR-1")
		self.assertEqual(movement["nearby_cameras"][0]["distance_m"], "125.5")

	def test_empty_area_scope_skips_events_even_with_vehicle_filter(self):
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_list", return_value=[]) as get_list,
		):
			result = map_api.map_payload(area="EMPTY-AREA", vehicle="VEH-1")
		self.assertEqual(result["movements"], [])
		self.assertEqual(get_list.call_count, 1)

	def test_map_rejects_invalid_camera_status(self):
		with self.assertRaises(frappe.ValidationError):
			map_api.map_payload(camera_status="Broken")

	def test_datetime_filters_keep_time_precision_and_accept_date_only_bounds(self):
		self.assertEqual(
			map_api._date_filter("2026-01-02T09:15", "2026-01-03"),
			{"detected_at": ["between", ["2026-01-02 09:15:00", "2026-01-03 23:59:59"]]},
		)
		self.assertEqual(
			map_api._date_filter(None, "2026-01-03T10:30"),
			{"detected_at": ["<=", "2026-01-03 10:30:00"]},
		)

	def test_map_rejects_reversed_datetime_range(self):
		with self.assertRaises(frappe.ValidationError):
			map_api._date_filter("2026-01-03T10:00", "2026-01-03T09:59")

	def test_map_preserves_all_photos_in_large_gallery(self):
		photos = [
			{
				"url": f"/files/gallery-{index:03}.jpg",
				"caption": f"Photo {index}",
				"description": "",
				"is_primary": index == 0,
				"sort_order": index,
			}
			for index in range(251)
		]
		camera = frappe._dict(
			name="CAM-LARGE-GALLERY",
			camera_name="Large Gallery",
			status="Active",
			camera_type="Fixed",
			area=None,
			address="",
			latitude="52.37",
			longitude="4.89",
			geo_admin_area=None,
			geo_boundary=None,
			primary_image=photos[0]["url"],
			is_demo_record=0,
			camera_photos_json=json.dumps(photos),
		)
		files = [frappe._dict(name=f"FILE-{index}", file_url=photo["url"], is_private=0) for index, photo in enumerate(photos)]
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_list", side_effect=[[camera], []]),
			patch.object(frappe, "get_all", return_value=files),
		):
			result = map_api.map_payload(camera=camera.name)
		self.assertEqual(len(result["cameras"][0]["photos"]), 251)
		self.assertEqual(result["cameras"][0]["photos"][-1]["caption"], "Photo 250")

	def test_file_lookup_batches_without_a_gallery_count_cap(self):
		urls = {f"/files/gallery-{index:04}.jpg" for index in range(1201)}

		def get_all(doctype, filters, **kwargs):
			self.assertEqual(doctype, "File")
			return [frappe._dict(name=url.rsplit("/", 1)[-1], file_url=url, is_private=0) for url in filters["file_url"][1]]

		with patch.object(frappe, "get_all", side_effect=get_all) as get_all_mock:
			file_map = map_api._load_file_map(urls)
		self.assertEqual(len(file_map), len(urls))
		self.assertEqual(get_all_mock.call_count, 3)
		self.assertTrue(all(call.kwargs["limit_page_length"] == 0 for call in get_all_mock.call_args_list))

	def test_map_rejects_invalid_synthetic_data_flag(self):
		with self.assertRaises(frappe.ValidationError):
			map_api.map_payload(include_demo="yes")

	def test_custom_map_coords_rejects_unsupported_doctypes(self):
		with self.assertRaises(frappe.ValidationError):
			map_api.get_custom_map_coords("Camera Credential")
