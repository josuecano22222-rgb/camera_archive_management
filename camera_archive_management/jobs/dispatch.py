"""Post-transaction dispatch hooks for queued app work."""

from __future__ import annotations

import frappe


def queue_ingest_batch(doc, method=None) -> None:
	if doc.doctype != "Archive Ingest Batch" or doc.status != "Queued":
		return
	frappe.enqueue(
		"camera_archive_management.jobs.archive.process_ingest_batch",
		queue="long",
		batch_name=doc.name,
		job_id=f"cam-ingest-{doc.name}",
		deduplicate=True,
		enqueue_after_commit=True,
	)


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


def queue_archive_asset_index(doc, method=None) -> None:
	if doc.doctype != "Archive Asset" or doc.index_status != "Queued":
		return
	frappe.enqueue(
		"camera_archive_management.jobs.archive.index_archive_asset",
		queue="long",
		asset_name=doc.name,
		job_id=f"cam-archive-index-{doc.name}",
		deduplicate=True,
		enqueue_after_commit=True,
	)
