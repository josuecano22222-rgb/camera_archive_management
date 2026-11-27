from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from camera_archive_management.camera_archive_management.doctype.camera.camera import _gallery_items


class TestCamera(FrappeTestCase):
	def test_gallery_requires_one_main_image_and_contiguous_order(self):
		valid = [
			{
				"url": "/private/files/one.jpg",
				"caption": "One",
				"description": "",
				"is_primary": True,
				"sort_order": 0,
			}
		]
		self.assertEqual(_gallery_items(valid)[0]["is_primary"], True)
		with self.assertRaises(frappe.ValidationError):
			_gallery_items([*valid, {**valid[0], "url": "/private/files/two.jpg", "sort_order": 1}])
		with self.assertRaises(frappe.ValidationError):
			_gallery_items([{**valid[0], "sort_order": 2}])

	def test_gallery_has_no_artificial_image_count_cap(self):
		photos = [
			{
				"url": f"/private/files/camera-{index}.jpg",
				"caption": "",
				"description": "",
				"is_primary": index == 0,
				"sort_order": index,
			}
			for index in range(51)
		]
		self.assertEqual(len(_gallery_items(photos)), 51)

	def test_gallery_syncs_primary_image_from_json(self):
		camera = frappe.get_doc(
			{
				"doctype": "Camera",
				"naming_series": "CAM-.####",
				"camera_name": "Gallery main image test",
				"status": "Active",
				"camera_photos_json": '[{"url":"/private/files/main.webp","caption":"Main","description":"","is_primary":true,"sort_order":0}]',
			}
		)
		camera.name = "CAM-GALLERY-TEST"
		file_doc = frappe._dict(file_url="/private/files/main.webp", file_name="main.webp")
		with patch.object(frappe, "get_all", return_value=[file_doc]):
			camera._validate_image_gallery()
		self.assertEqual(camera.primary_image, "/private/files/main.webp")

	def test_credential_profile_requires_at_least_one_credential_value(self):
		camera = frappe.get_doc(
			{
				"doctype": "Camera",
				"naming_series": "CAM-.####",
				"camera_name": "Credential profile validation test",
				"status": "Active",
				"camera_photos_json": "[]",
				"nearby_cameras": [],
				"credential_label": "Main account",
			}
		)
		with self.assertRaises(frappe.ValidationError):
			camera.validate()
		camera.username = "operator"
		camera.validate()

	def test_camera_without_credentials_stays_valid(self):
		camera = frappe.get_doc(
			{
				"doctype": "Camera",
				"naming_series": "CAM-.####",
				"camera_name": "No credentials validation test",
				"status": "Active",
				"camera_photos_json": "[]",
				"nearby_cameras": [],
			}
		)
		camera.validate()
		self.assertFalse(camera.username)
		self.assertFalse(camera.password)

	def test_rejects_out_of_range_wgs84_coordinates(self):
		camera = frappe.get_doc(
			{
				"doctype": "Camera",
				"naming_series": "CAM-.####",
				"camera_name": "Coordinate validation test",
				"status": "Active",
				"latitude": "91",
				"longitude": "4.9",
				"camera_photos_json": "[]",
				"nearby_cameras": [],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			camera.validate()

	def test_coordinate_data_fields_preserve_long_decimal_strings(self):
		latitude = "52.123456789012345678901234567890"
		longitude = "4.987654321098765432109876543210"
		camera = frappe.get_doc(
			{
				"doctype": "Camera",
				"naming_series": "CAM-.####",
				"camera_name": "Exact coordinate precision test",
				"status": "Active",
				"latitude": latitude,
				"longitude": longitude,
				"camera_photos_json": "[]",
				"nearby_cameras": [],
			}
		).insert(ignore_permissions=True)
		reloaded = frappe.get_doc("Camera", camera.name)
		self.assertEqual(reloaded.latitude, latitude)
		self.assertEqual(reloaded.longitude, longitude)
		location = frappe.parse_json(reloaded.location)
		self.assertEqual(location["type"], "FeatureCollection")
		self.assertIn(f"[{longitude},{latitude}]", reloaded.location)
		self.assertEqual(location["features"][0]["properties"]["point_type"], "marker")

	def test_camera_point_is_normalized_for_frappe_geolocation_without_touching_address(self):
		address = "User-entered address"
		location = '{"type":"Point","coordinates":[4.9,52.3]}'
		camera = frappe.get_doc(
			{
				"doctype": "Camera",
				"naming_series": "CAM-.####",
				"camera_name": "Manual location test",
				"status": "Active",
				"address": address,
				"location": location,
				"latitude": "52.3",
				"longitude": "4.9",
				"camera_photos_json": "[]",
				"nearby_cameras": [],
			}
		)
		camera.validate()
		camera.before_save()
		self.assertEqual(camera.address, address)
		parsed = frappe.parse_json(camera.location)
		self.assertEqual(parsed["type"], "FeatureCollection")
		self.assertEqual(parsed["features"][0]["properties"]["point_type"], "marker")
		self.assertEqual(camera.location.count("FeatureCollection"), 1)
