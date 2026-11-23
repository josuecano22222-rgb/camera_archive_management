from __future__ import annotations

import frappe


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {}
	if filters.get("lookup_source"):
		conditions["lookup_source"] = filters.lookup_source
	if filters.get("only_ambiguous"):
		conditions["lookup_ambiguous"] = 1
	rows = frappe.get_list(
		"Camera",
		filters=conditions,
		fields=[
			"name", "camera_name", "status", "latitude", "longitude", "address", "geo_admin_area",
			"geo_boundary", "lookup_source", "lookup_confidence", "lookup_ambiguous", "lookup_resolved_at",
		],
		order_by="lookup_ambiguous desc, lookup_resolved_at desc, camera_name asc, name asc",
		limit_page_length=10000,
	)
	columns = [
		{"fieldname": "name", "label": "Camera", "fieldtype": "Link", "options": "Camera", "width": 150},
		{"fieldname": "camera_name", "label": "Camera Name", "fieldtype": "Data", "width": 200},
		{"fieldname": "status", "label": "Status", "fieldtype": "Data", "width": 90},
		{"fieldname": "latitude", "label": "Latitude (exact string)", "fieldtype": "Data", "width": 170},
		{"fieldname": "longitude", "label": "Longitude (exact string)", "fieldtype": "Data", "width": 170},
		{"fieldname": "address", "label": "Address", "fieldtype": "Data", "width": 220},
		{"fieldname": "geo_admin_area", "label": "Admin Area", "fieldtype": "Link", "options": "Geo Admin Area", "width": 160},
		{"fieldname": "geo_boundary", "label": "Boundary", "fieldtype": "Link", "options": "Geo Boundary", "width": 140},
		{"fieldname": "lookup_source", "label": "Provenance", "fieldtype": "Data", "width": 140},
		{"fieldname": "lookup_confidence", "label": "Confidence (0-1)", "fieldtype": "Float", "width": 120},
		{"fieldname": "lookup_ambiguous", "label": "Ambiguous", "fieldtype": "Check", "width": 90},
		{"fieldname": "lookup_resolved_at", "label": "Resolved At", "fieldtype": "Datetime", "width": 160},
	]
	return columns, [dict(row) for row in rows]
