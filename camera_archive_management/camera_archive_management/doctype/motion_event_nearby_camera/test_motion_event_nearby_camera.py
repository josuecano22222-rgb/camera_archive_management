from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestMotionEventNearbyCamera(FrappeTestCase):
	def test_rejects_negative_distance(self):
		row = frappe.get_doc({"doctype": "Motion Event Nearby Camera", "distance_m": -0.1})
		with self.assertRaises(frappe.ValidationError):
			row.validate()

	def test_bearing_is_normalized_range(self):
		row = frappe.get_doc(
			{"doctype": "Motion Event Nearby Camera", "distance_m": 100, "bearing_deg": 359.9}
		)
		row.validate()
		row.bearing_deg = 360
		with self.assertRaises(frappe.ValidationError):
			row.validate()
