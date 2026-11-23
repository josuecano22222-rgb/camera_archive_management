from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestCameraType(FrappeTestCase):
	def test_type_name_is_trimmed(self):
		camera_type = frappe.get_doc({"doctype": "Camera Type", "type_name": "  Traffic Camera  "})
		camera_type.validate()
		self.assertEqual(camera_type.type_name, "Traffic Camera")

	def test_blank_type_name_is_rejected(self):
		camera_type = frappe.get_doc({"doctype": "Camera Type", "type_name": "   "})
		with self.assertRaises(frappe.ValidationError):
			camera_type.validate()
