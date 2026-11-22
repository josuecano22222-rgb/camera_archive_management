from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestArchiveIngestBatch(FrappeTestCase):
	def test_idempotency_is_scoped_to_source(self):
		first = frappe.get_doc(
			{
				"doctype": "Archive Ingest Batch",
				"naming_series": "ING-.#####",
				"source_scope": "unit-test-source-a",
				"idempotency_key": "same-key",
				"manifest_json": '{"assets":[]}',
				"status": "Draft",
			}
		).insert(ignore_permissions=True)

		duplicate = frappe.get_doc(
			{
				"doctype": "Archive Ingest Batch",
				"naming_series": "ING-.#####",
				"source_scope": "unit-test-source-a",
				"idempotency_key": "same-key",
				"manifest_json": '{"assets":[]}',
				"status": "Draft",
			}
		)
		with self.assertRaises(frappe.DuplicateEntryError):
			duplicate.insert(ignore_permissions=True)

		other_source = frappe.get_doc(
			{
				"doctype": "Archive Ingest Batch",
				"naming_series": "ING-.#####",
				"source_scope": "unit-test-source-b",
				"idempotency_key": "same-key",
				"manifest_json": '{"assets":[]}',
				"status": "Draft",
			}
		).insert(ignore_permissions=True)
		self.assertNotEqual(first.name, other_source.name)
