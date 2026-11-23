from __future__ import annotations

import json
import re

import frappe
from frappe.model.document import Document

_IDEMPOTENCY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ArchiveIngestBatch(Document):
	def validate(self) -> None:
		previous = self.get_doc_before_save()
		status_changed = not previous or previous.status != self.status
		if (
			status_changed
			and self.status in {"Running", "Complete", "Failed"}
			and not self.flags.get("worker_update")
		):
			frappe.throw(
				"Only the ingest worker may set Running, Complete, or Failed status.", frappe.PermissionError
			)
		self.source_scope = (self.source_scope or "").strip()
		self.idempotency_key = (self.idempotency_key or "").strip()
		if not self.source_scope or len(self.source_scope) > 140:
			frappe.throw(
				"Source scope is required and must be at most 140 characters.", frappe.ValidationError
			)
		if not _IDEMPOTENCY.fullmatch(self.idempotency_key):
			frappe.throw("Idempotency key must be 1-128 safe ASCII characters.", frappe.ValidationError)
		if bool(self.source_manifest) == bool(self.manifest_json):
			frappe.throw("Provide exactly one of source_manifest or manifest_json.", frappe.ValidationError)
		if self.manifest_json:
			if len(self.manifest_json.encode("utf-8")) > 2 * 1024 * 1024:
				frappe.throw("Inline ingest manifest exceeds the 2 MiB limit.", frappe.ValidationError)
			try:
				payload = json.loads(self.manifest_json)
			except (TypeError, json.JSONDecodeError) as exc:
				frappe.throw(f"Manifest JSON is invalid: {exc}", frappe.ValidationError)
			if not isinstance(payload, dict) or not isinstance(payload.get("assets"), list):
				frappe.throw("Manifest must be a JSON object with an assets array.", frappe.ValidationError)

		duplicate = frappe.db.exists(
			"Archive Ingest Batch",
			{"source_scope": self.source_scope, "idempotency_key": self.idempotency_key},
		)
		if duplicate and duplicate != self.name:
			frappe.throw(
				f"An ingest batch already exists for this source and idempotency key ({duplicate}).",
				frappe.DuplicateEntryError,
			)
