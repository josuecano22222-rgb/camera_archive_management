from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestMotionEvent(FrappeTestCase):
	def test_snapshots_camera_location_and_keeps_it_immutable(self):
		camera = frappe.get_doc(
			{
				"doctype": "Camera",
				"naming_series": "CAM-.####",
				"camera_name": "Snapshot test camera",
				"status": "Active",
				"address": "Manual address",
				"latitude": "52.3",
				"longitude": "4.9",
				"location": '{"type":"Point","coordinates":[4.9,52.3]}',
				"camera_photos": [],
				"nearby_cameras": [],
			}
		).insert(ignore_permissions=True)
		event = frappe.get_doc(
			{
				"doctype": "Motion Event",
				"naming_series": "MOT-.#####",
				"camera": camera.name,
				"motion_type": "Entry",
				"detected_at": "2026-11-22 12:00:00",
			}
		).insert(ignore_permissions=True)

		self.assertEqual(event.address_snapshot, "Manual address")
		self.assertEqual(str(event.latitude_snapshot), "52.3")
		self.assertEqual(str(event.longitude_snapshot), "4.9")
		self.assertEqual(event.location_source_snapshot, "manual")
		self.assertEqual(event.location_snapshot, camera.location)
		original_location_snapshot = event.location_snapshot

		camera.latitude = "52.4"
		camera.longitude = "5.0"
		camera.location = '{"type":"Point","coordinates":[5.0,52.4]}'
		camera.save(ignore_permissions=True)
		event.reload()
		self.assertEqual(str(event.latitude_snapshot), "52.3")
		self.assertEqual(str(event.longitude_snapshot), "4.9")
		self.assertEqual(event.location_snapshot, original_location_snapshot)

		event.notes = "Additional description"
		event.save(ignore_permissions=True)
		event.latitude_snapshot = "52.4"
		with self.assertRaises(frappe.PermissionError):
			event.save(ignore_permissions=True)
