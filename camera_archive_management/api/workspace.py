"""Permission-aware summary metrics for the Camera Archive workspace."""

from __future__ import annotations

import frappe
from frappe.utils import add_days, nowdate


@frappe.whitelist(methods=["GET"])
def get_workspace_summary() -> dict:
	"""Return workspace totals and compact chart series using permission-aware list queries."""
	if frappe.session.user == "Guest":
		frappe.throw("Sign in to view Camera Archive workspace statistics.", frappe.PermissionError)

	counts = {}
	for doctype, key in (
		("Camera", "cameras"), ("Motion Event", "movements"), ("CAM Vehicle", "vehicles"),
		("Archive Asset", "archive_assets"), ("Archive Ingest Batch", "ingest_batches"),
	):
		if not frappe.has_permission(doctype, "read"):
			continue
		rows = frappe.get_list(doctype, fields=["count(name) as total"], limit_page_length=1)
		counts[key] = _count(rows[0].get("total")) if rows else 0

	camera_status = _grouped_counts("Camera", "status")
	movement_types = _grouped_counts("Motion Event", "motion_type")
	daily_movements = []
	if frappe.has_permission("Motion Event", "read"):
		start_day = add_days(nowdate(), -13)
		rows = frappe.get_list(
			"Motion Event",
			filters={"detected_at": [">=", f"{start_day} 00:00:00"]},
			fields=["DATE(detected_at) as day", "count(name) as total"],
			group_by="DATE(detected_at)",
			order_by="day asc",
			limit_page_length=14,
		)
		daily_movements = [
			{"label": str(row.get("day") or ""), "value": _count(row.get("total"))}
			for row in rows if row.get("day")
		]

	top_vehicles = []
	if frappe.has_permission("Motion Event", "read"):
		rows = frappe.get_list(
			"Motion Event",
			filters={"vehicle": ["is", "set"]},
			fields=["vehicle", "count(name) as total"],
			group_by="vehicle",
			order_by="total desc, vehicle asc",
			limit_page_length=8,
		)
		vehicle_ids = [row.get("vehicle") for row in rows if row.get("vehicle")]
		labels = {}
		if vehicle_ids and frappe.has_permission("CAM Vehicle", "read"):
			vehicles = frappe.get_list(
				"CAM Vehicle", filters={"name": ["in", vehicle_ids]},
				fields=["name", "vehicle_name"], limit_page_length=8,
			)
			labels = {row.name: row.vehicle_name or row.name for row in vehicles}
		top_vehicles = [
			{"label": labels.get(row.get("vehicle"), row.get("vehicle")), "value": _count(row.get("total"))}
			for row in rows if row.get("vehicle")
		]

	return {
		"counts": counts,
		"camera_status": camera_status,
		"movement_types": movement_types,
		"daily_movements": daily_movements,
		"top_vehicles": top_vehicles,
		"generated_on": nowdate(),
	}


def _grouped_counts(doctype: str, field: str) -> list[dict]:
	if not frappe.has_permission(doctype, "read"):
		return []
	rows = frappe.get_list(
		doctype,
		fields=[field, "count(name) as total"],
		group_by=field,
		order_by=f"{field} asc",
		limit_page_length=100,
	)
	return [
		{"label": str(row.get(field) or "Not set"), "value": _count(row.get("total"))}
		for row in rows
	]


def _count(value) -> int:
	try:
		return max(0, int(value or 0))
	except (TypeError, ValueError, OverflowError):
		return 0
