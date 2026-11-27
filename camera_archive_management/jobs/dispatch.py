"""Post-transaction dispatch hooks for queued app work."""

from __future__ import annotations

import frappe


def queue_geo_dataset_import(doc, method=None) -> None:
	if doc.doctype != "Geo Dataset" or doc.import_status != "Queued":
		return
	frappe.enqueue(
		"camera_archive_management.jobs.geo.import_geo_dataset",
		queue="long",
		dataset_name=doc.name,
		job_id=f"cam-geo-import-{doc.name}",
		deduplicate=True,
		enqueue_after_commit=True,
	)
