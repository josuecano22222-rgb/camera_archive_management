from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestCameraPhoto(FrappeTestCase):
	def test_primary_photo_requires_image(self):
		photo = frappe.get_doc({"doctype": "Camera Photo", "is_primary": 1})
		with self.assertRaises(frappe.ValidationError):
			photo.validate()

	def test_rejects_non_frappe_file_url(self):
		photo = frappe.get_doc({"doctype": "Camera Photo", "image": "https://example.invalid/photo.jpg"})
		with self.assertRaises(frappe.ValidationError):
			photo.validate()

	def test_rejects_unregistered_local_file(self):
		photo = frappe.get_doc({"doctype": "Camera Photo", "image": "/private/files/missing-photo.jpg"})
		with self.assertRaises(frappe.ValidationError):
			photo.validate()
