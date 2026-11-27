from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestCAMGeoSettings(FrappeTestCase):
	def test_tile_fetch_controls_default_off_and_timeouts_bounded(self):
		settings = frappe.new_doc("CAM Geo Settings")
		self.assertFalse(settings.enable_online_tile_fetch)
		self.assertFalse(settings.allow_tile_cache_write)
		settings.tile_connect_timeout_seconds = 1
		settings.tile_read_timeout_seconds = 5
		settings.validate()

	def test_cache_write_requires_explicit_fetch_opt_in(self):
		settings = frappe.new_doc("CAM Geo Settings")
		settings.allow_tile_cache_write = 1
		with self.assertRaises(frappe.ValidationError):
			settings.validate()

	def test_tile_timeouts_outside_one_to_five_seconds_are_rejected(self):
		for fieldname, invalid_value in (
			("tile_connect_timeout_seconds", 0),
			("tile_connect_timeout_seconds", 6),
			("tile_read_timeout_seconds", 0),
			("tile_read_timeout_seconds", 6),
		):
			with self.subTest(fieldname=fieldname, value=invalid_value):
				settings = frappe.new_doc("CAM Geo Settings")
				setattr(settings, fieldname, invalid_value)
				with self.assertRaises(frappe.ValidationError):
					settings.validate()

	def test_motion_event_defaults_and_nearby_radius_bounds(self):
		settings = frappe.new_doc("CAM Geo Settings")
		self.assertEqual(settings.default_motion_importance, "Medium")
		self.assertTrue(settings.enable_nearby_camera_alerts)
		self.assertEqual(settings.nearby_camera_radius, 500)
		settings.nearby_camera_radius = 0
		settings.validate()
		settings.nearby_camera_radius = 100000
		settings.validate()
		for invalid_value in (-1, 100001):
			with self.subTest(value=invalid_value):
				settings.nearby_camera_radius = invalid_value
				with self.assertRaises(frappe.ValidationError):
					settings.validate()
