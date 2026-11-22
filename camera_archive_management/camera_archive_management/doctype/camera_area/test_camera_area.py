from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestCameraArea(FrappeTestCase):
	def test_rejects_self_as_parent(self):
		area = frappe.get_doc(
			{
				"doctype": "Camera Area",
				"area_name": "self-parent-test",
				"parent_camera_area": "self-parent-test",
			}
		)
		with self.assertRaises(frappe.ValidationError):
			area.validate()

	def test_parent_must_exist_and_be_a_group(self):
		area = frappe.get_doc(
			{"doctype": "Camera Area", "area_name": "child-area", "parent_camera_area": "parent-area"}
		)
		with patch.object(frappe.db, "get_value", return_value=0):
			with self.assertRaises(frappe.ValidationError):
				area.validate()
		with patch.object(frappe.db, "get_value", return_value=1):
			area.validate()
