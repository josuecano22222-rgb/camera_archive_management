from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestVehicleType(FrappeTestCase):
	def test_strips_type_name_and_accepts_no_optional_image(self):
		vehicle_type = frappe.get_doc(
			{"doctype": "Vehicle Type", "type_name": "  Patrol Vehicle  ", "is_active": 1}
		)
		vehicle_type.validate()
		self.assertEqual(vehicle_type.type_name, "Patrol Vehicle")

	def test_rejects_external_vehicle_type_image(self):
		vehicle_type = frappe.get_doc(
			{"doctype": "Vehicle Type", "type_name": "Patrol Vehicle", "vehicle_type_image": "https://example.invalid/icon.png"}
		)
		with self.assertRaises(frappe.ValidationError):
			vehicle_type.validate()
