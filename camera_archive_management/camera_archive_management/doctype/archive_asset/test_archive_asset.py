from __future__ import annotations

from unittest.mock import patch

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

	def test_accepts_only_private_frappe_file_record(self):
		asset = self._asset(file_url="/private/files/camera-recording.mp4")
		with patch.object(
			frappe.db,
			"get_value",
			return_value=frappe._dict(name="FILE-PRIVATE", is_private=1),
		):
			asset.validate()

		public_asset = self._asset(file_url="/files/public-camera-recording.mp4")
		with patch.object(
			frappe.db,
			"get_value",
			return_value=frappe._dict(name="FILE-PUBLIC", is_private=0),
		), self.assertRaises(frappe.ValidationError):
			public_asset.validate()

	def test_accepts_safe_external_reference_only_when_enabled(self):
		asset = self._asset(
			storage_backend="External",
			file_url=None,
			external_reference="s3://archive-bucket/camera/2026/recording.mp4",
		)
		with patch.object(frappe, "get_single", return_value=frappe._dict(allow_external_archive_references=1)):
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
