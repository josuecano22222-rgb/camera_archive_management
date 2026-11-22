from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestCameraNearbyCamera(FrappeTestCase):
	def test_rejects_parent_camera_as_its_own_neighbor(self):
		row = frappe.get_doc(
			{
				"doctype": "Camera Nearby Camera",
				"parent": "CAM-0001",
				"camera": "CAM-0001",
		}
		)
		with self.assertRaises(frappe.ValidationError):
			row.validate()
