from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestArchiveSettings(FrappeTestCase):
	def test_rejects_out_of_range_report_window(self):
		settings = frappe.get_doc({"doctype": "Archive Settings", "default_report_days": 0})
		with self.assertRaises(frappe.ValidationError):
			settings.validate()

	def test_rejects_negative_retention(self):
		settings = frappe.get_doc({"doctype": "Archive Settings", "default_retention_days": -1})
		with self.assertRaises(frappe.ValidationError):
			settings.validate()

	def test_accepts_valid_radius_and_report_window(self):
		settings = frappe.get_doc(
			{
				"doctype": "Archive Settings",
				"default_report_days": 30,
				"nearby_camera_radius": 500,
				"default_retention_days": 0,
			}
		)
		settings.validate()
