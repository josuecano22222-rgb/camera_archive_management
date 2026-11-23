from __future__ import annotations

import frappe


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {}
	for key in ("storage_backend", "index_status", "retention_state"):
		if filters.get(key):
			conditions[key] = filters[key]
	assets = frappe.get_list(
		"Archive Asset",
		filters=conditions,
		fields=[
			"name", "title", "camera", "motion_event", "storage_backend", "file_url", "external_reference",
			"checksum_sha256", "size_bytes", "index_status", "retention_state", "recorded_from", "recorded_to",
		],
		order_by="modified desc, name asc",
		limit_page_length=10000,
	)
	file_urls = sorted({row.file_url for row in assets if row.file_url})
	file_rows = frappe.get_all(
		"File",
		filters={"file_url": ["in", file_urls]},
		fields=["name", "file_url", "is_private"],
		order_by="file_url asc, name asc",
		limit_page_length=min(20000, len(file_urls) * 2),
	) if file_urls else []
	files_by_url = {}
	for file_doc in file_rows:
		files_by_url.setdefault(file_doc.file_url, []).append(file_doc)

	columns = [
		{"fieldname": "name", "label": "Archive Asset", "fieldtype": "Link", "options": "Archive Asset", "width": 170},
		{"fieldname": "title", "label": "Title", "fieldtype": "Data", "width": 220},
		{"fieldname": "camera", "label": "Camera", "fieldtype": "Link", "options": "Camera", "width": 140},
		{"fieldname": "motion_event", "label": "Motion Event", "fieldtype": "Link", "options": "Motion Event", "width": 150},
		{"fieldname": "storage_backend", "label": "Storage", "fieldtype": "Data", "width": 100},
		{"fieldname": "source_integrity", "label": "Source Integrity", "fieldtype": "Data", "width": 160},
		{"fieldname": "checksum_sha256", "label": "SHA-256", "fieldtype": "Data", "width": 240},
		{"fieldname": "size_bytes", "label": "Bytes", "fieldtype": "Int", "width": 100},
		{"fieldname": "index_status", "label": "Index Status", "fieldtype": "Data", "width": 100},
		{"fieldname": "retention_state", "label": "Retention", "fieldtype": "Data", "width": 100},
		{"fieldname": "recorded_from", "label": "Recorded From", "fieldtype": "Datetime", "width": 150},
		{"fieldname": "recorded_to", "label": "Recorded To", "fieldtype": "Datetime", "width": 150},
	]
	data = []
	for asset in assets:
		if asset.storage_backend == "External":
			integrity = "Reference set" if asset.external_reference else "Missing reference"
		else:
			matches = files_by_url.get(asset.file_url, [])
			integrity = "Private File OK" if len(matches) == 1 and matches[0].is_private else "Missing / duplicate / public File"
		data.append({
			"name": asset.name,
			"title": asset.title,
			"camera": asset.camera,
			"motion_event": asset.motion_event,
			"storage_backend": asset.storage_backend,
			"source_integrity": integrity,
			"checksum_sha256": asset.checksum_sha256,
			"size_bytes": asset.size_bytes,
			"index_status": asset.index_status,
			"retention_state": asset.retention_state,
			"recorded_from": asset.recorded_from,
			"recorded_to": asset.recorded_to,
		})
	return columns, data
