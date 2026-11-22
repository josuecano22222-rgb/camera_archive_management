"""Bounded recovery for queued background work."""

from __future__ import annotations

import frappe


def requeue_pending_work() -> None:
	"""Re-enqueue a bounded page of queued records after worker restarts."""
	batches = frappe.get_all(
		"Archive Ingest Batch",
		filters={"status": "Queued"},
		fields=["name"],
		order_by="modified asc, name asc",
		limit_page_length=100,
	)
	for row in batches:
		frappe.enqueue(
			"camera_archive_management.jobs.archive.process_ingest_batch",
			queue="long",
			batch_name=row.name,
			job_id=f"cam-ingest-{row.name}",
			deduplicate=True,
			enqueue_after_commit=True,
		)

	assets = frappe.get_all(
		"Archive Asset",
		filters={"index_status": "Queued"},
		fields=["name"],
		order_by="modified asc, name asc",
		limit_page_length=100,
	)
	for row in assets:
		frappe.enqueue(
			"camera_archive_management.jobs.archive.index_archive_asset",
			queue="long",
			asset_name=row.name,
			job_id=f"cam-archive-index-{row.name}",
			deduplicate=True,
			enqueue_after_commit=True,
		)

	datasets = frappe.get_all(
		"Geo Dataset",
		filters={"import_status": "Queued"},
		fields=["name"],
		order_by="modified asc, name asc",
		limit_page_length=100,
	)
	for row in datasets:
		frappe.enqueue(
			"camera_archive_management.jobs.geo.import_geo_dataset",
			queue="long",
			dataset_name=row.name,
			job_id=f"cam-geo-import-{row.name}",
			deduplicate=True,
			enqueue_after_commit=True,
		)
