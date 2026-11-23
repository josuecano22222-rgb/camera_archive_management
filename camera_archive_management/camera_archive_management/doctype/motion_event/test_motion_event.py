from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime


class TestMotionEvent(FrappeTestCase):
	def test_snapshots_camera_location_and_keeps_it_immutable(self):
		camera = frappe.get_doc(
			{
				"doctype": "Camera",
				"naming_series": "CAM-.####",
				"camera_name": "Snapshot test camera",
				"status": "Active",
				"importance": "Critical",
				"address": "Manual address",
				"latitude": "52.3",
				"longitude": "4.9",
				"location": '{"type":"Point","coordinates":[4.9,52.3]}',
				"camera_photos_json": "[]",
				"nearby_cameras": [],
			}
		).insert(ignore_permissions=True)
		event = frappe.get_doc(
			{
				"doctype": "Motion Event",
				"naming_series": "MOT-.#####",
				"camera": camera.name,
				"motion_type": "Entry",
				"detected_at": add_to_date(now_datetime(), days=-1),
			}
		).insert(ignore_permissions=True)

		self.assertEqual(event.address_snapshot, "Manual address")
		self.assertEqual(str(event.latitude_snapshot), "52.3")
		self.assertEqual(str(event.longitude_snapshot), "4.9")
		self.assertEqual(event.location_source_snapshot, "manual")
		self.assertEqual(event.location_snapshot, camera.location)
		self.assertEqual(event.importance, "Critical")
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

	def test_event_captures_cameras_within_configured_alert_radius(self):
		settings = frappe.get_single("Archive Settings")
		settings.enable_nearby_camera_alerts = 1
		settings.nearby_camera_radius = 200
		settings.save(ignore_permissions=True)

		camera = frappe.get_doc(
			{
				"doctype": "Camera",
				"naming_series": "CAM-.####",
				"camera_name": "Nearby alert source camera",
				"status": "Active",
				"latitude": "-70.123",
				"longitude": "-40.456",
				"camera_photos_json": "[]",
			}
		).insert(ignore_permissions=True)
		nearby = frappe.get_doc(
			{
				"doctype": "Camera",
				"naming_series": "CAM-.####",
				"camera_name": "Nearby alert target camera",
				"status": "Active",
				"latitude": "-70.124",
				"longitude": "-40.456",
				"camera_photos_json": "[]",
			}
		).insert(ignore_permissions=True)

		event = frappe.get_doc(
			{
				"doctype": "Motion Event",
				"naming_series": "MOT-.#####",
				"camera": camera.name,
				"motion_type": "Entry",
				"detected_at": add_to_date(now_datetime(), days=-1),
			}
		).insert(ignore_permissions=True)

		nearby_rows = {row.camera: row for row in event.nearby_cameras}
		self.assertIn(nearby.name, nearby_rows)
		self.assertLessEqual(nearby_rows[nearby.name].distance_m, 200)
		self.assertFalse(nearby_rows[nearby.name].note)

	def test_event_includes_explicitly_connected_camera_even_outside_radius(self):
		settings = frappe.get_single("Archive Settings")
		settings.enable_nearby_camera_alerts = 1
		settings.nearby_camera_radius = 100
		settings.save(ignore_permissions=True)

		source = frappe.get_doc(
			{
				"doctype": "Camera",
				"naming_series": "CAM-.####",
				"camera_name": "Connected alert source camera",
				"status": "Active",
				"latitude": "-70.123",
				"longitude": "-40.456",
				"camera_photos_json": "[]",
			}
		).insert(ignore_permissions=True)
		connected = frappe.get_doc(
			{
				"doctype": "Camera",
				"naming_series": "CAM-.####",
				"camera_name": "Connected camera outside radius",
				"status": "Active",
				"latitude": "-69.9",
				"longitude": "-40.456",
				"camera_photos_json": "[]",
				"nearby_cameras": [{"camera": source.name, "note": "Shared intersection"}],
			}
		).insert(ignore_permissions=True)

		event = frappe.get_doc(
			{
				"doctype": "Motion Event",
				"naming_series": "MOT-.#####",
				"camera": source.name,
				"motion_type": "Exit",
				"detected_at": add_to_date(now_datetime(), days=-1),
			}
		).insert(ignore_permissions=True)

		connected_rows = {row.camera: row for row in event.nearby_cameras}
		self.assertIn(connected.name, connected_rows)
		self.assertGreater(connected_rows[connected.name].distance_m, 100)
		self.assertEqual(connected_rows[connected.name].note, "Configured connection: Shared intersection")

	def test_explicit_importance_is_preserved_and_future_events_are_rejected(self):
		camera = frappe.get_doc(
			{
				"doctype": "Camera",
				"naming_series": "CAM-.####",
				"camera_name": "Importance and future-time test camera",
				"status": "Active",
				"importance": "Critical",
				"camera_photos_json": "[]",
			}
		).insert(ignore_permissions=True)
		past = add_to_date(now_datetime(), days=-1)
		event = frappe.get_doc(
			{
				"doctype": "Motion Event",
				"naming_series": "MOT-.#####",
				"camera": camera.name,
				"motion_type": "Entry",
				"detected_at": past,
				"importance": "Low",
			}
		).insert(ignore_permissions=True)
		self.assertEqual(event.importance, "Low")

		default_camera = frappe.get_doc(
			{
				"doctype": "Camera",
				"naming_series": "CAM-.####",
				"camera_name": "Default importance test camera",
				"status": "Active",
				"camera_photos_json": "[]",
			}
		).insert(ignore_permissions=True)
		default_event = frappe.get_doc(
			{
				"doctype": "Motion Event",
				"naming_series": "MOT-.#####",
				"camera": default_camera.name,
				"motion_type": "Entry",
				"detected_at": past,
			}
		).insert(ignore_permissions=True)
		default_importance = frappe.db.get_single_value("Archive Settings", "default_motion_importance") or "Medium"
		self.assertEqual(default_event.importance, default_importance)

		future = frappe.get_doc(
			{
				"doctype": "Motion Event",
				"naming_series": "MOT-.#####",
				"camera": camera.name,
				"motion_type": "Exit",
				"detected_at": add_to_date(now_datetime(), seconds=60),
			}
		)
		with self.assertRaises(frappe.ValidationError):
			future.insert(ignore_permissions=True)
		self.assertFalse(frappe.db.exists("Motion Event", future.name))
