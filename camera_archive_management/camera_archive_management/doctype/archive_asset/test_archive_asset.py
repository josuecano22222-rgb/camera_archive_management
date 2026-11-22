from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestArchiveAsset(FrappeTestCase):
	def _asset(self, **values):
		fields = {
			"doctype": "Archive Asset",
			"title": "Unit test archive reference",
			"camera": "missing-camera-is-not-a-link-checked-by-validate",
			"storage_backend": "Frappe File",
			"file_url": "/etc/passwd",
			"retention_state": "Active",
		}
		fields.update(values)
		return frappe.get_doc(fields)

	def test_rejects_arbitrary_local_path(self):
		asset = self._asset()
		with self.assertRaises(frappe.ValidationError):
			asset.validate()

	def test_rejects_external_parent_traversal(self):
		asset = self._asset(
			storage_backend="External",
			file_url=None,
			external_reference="s3://archive-bucket/folder/%2e%2e/secret",
		)
		with self.assertRaises(frappe.ValidationError):
			asset.validate()

	def test_rejects_s3_reference_without_object_key(self):
		asset = self._asset(
			storage_backend="External",
			file_url=None,
			external_reference="s3://archive-bucket",
		)
		with self.assertRaises(frappe.ValidationError):
			asset.validate()
