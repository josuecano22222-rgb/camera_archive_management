from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestCamera(FrappeTestCase):
	def test_rejects_out_of_range_wgs84_coordinates(self):
		camera = frappe.get_doc(
			{
				"doctype": "Camera",
				"naming_series": "CAM-.####",
				"camera_name": "Coordinate validation test",
				"status": "Active",
				"latitude": "91",
				"longitude": "4.9",
				"camera_photos": [],
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
				"camera_photos": [],
				"nearby_cameras": [],
			}
		).insert(ignore_permissions=True)
		reloaded = frappe.get_doc("Camera", camera.name)
		self.assertEqual(reloaded.latitude, latitude)
		self.assertEqual(reloaded.longitude, longitude)

	def test_before_save_preserves_manual_address_and_location(self):
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
				"camera_photos": [],
				"nearby_cameras": [],
			}
		)
		camera.before_save()
		self.assertEqual(camera.address, address)
		self.assertEqual(camera.location, location)
