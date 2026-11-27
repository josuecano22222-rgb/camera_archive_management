"""Bounded recovery for queued background work."""

from __future__ import annotations

import frappe


def requeue_pending_work() -> None:
	"""Re-enqueue a bounded page of queued records after worker restarts."""
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
