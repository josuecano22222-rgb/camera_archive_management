from __future__ import annotations

import frappe


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {}
	if filters.get("camera_area"):
		conditions["area"] = filters.camera_area
	if filters.get("status"):
		conditions["status"] = filters.status
	rows = frappe.get_list(
		"Camera",
		filters=conditions,
		fields=[
			"name", "camera_name", "status", "camera_type", "area", "address", "latitude", "longitude",
			"geo_admin_area", "geo_boundary", "lookup_source", "lookup_confidence", "lookup_ambiguous",
			"lookup_resolved_at",
		],
		order_by="camera_name asc, name asc",
		limit_page_length=5000,
	)
	names = [row.name for row in rows]
	photo_counts = {}
	if names:
		photo_rows = frappe.get_all(
			"Camera Photo",
			filters={"parent": ["in", names], "parenttype": "Camera", "parentfield": "camera_photos"},
			fields=["parent"],
			order_by="parent asc, idx asc",
			limit_page_length=50000,
		)
		for row in photo_rows:
			photo_counts[row.parent] = photo_counts.get(row.parent, 0) + 1
	columns = [
		{"fieldname": "name", "label": "Camera", "fieldtype": "Link", "options": "Camera", "width": 150},
		{"fieldname": "camera_name", "label": "Camera Name", "fieldtype": "Data", "width": 200},
		{"fieldname": "status", "label": "Status", "fieldtype": "Data", "width": 100},
		{"fieldname": "camera_type", "label": "Type", "fieldtype": "Link", "options": "Camera Type", "width": 130},
		{"fieldname": "area", "label": "Area", "fieldtype": "Link", "options": "Camera Area", "width": 130},
		{"fieldname": "latitude", "label": "Latitude (exact)", "fieldtype": "Data", "width": 150},
		{"fieldname": "longitude", "label": "Longitude (exact)", "fieldtype": "Data", "width": 150},
		{"fieldname": "address", "label": "Address", "fieldtype": "Data", "width": 220},
		{"fieldname": "geo_admin_area", "label": "Administrative Area", "fieldtype": "Link", "options": "Geo Admin Area", "width": 170},
		{"fieldname": "geo_boundary", "label": "Boundary", "fieldtype": "Link", "options": "Geo Boundary", "width": 150},
		{"fieldname": "photo_count", "label": "Photos", "fieldtype": "Int", "width": 70},
		{"fieldname": "lookup_source", "label": "Location Source", "fieldtype": "Data", "width": 130},
		{"fieldname": "lookup_confidence", "label": "Confidence (0-1)", "fieldtype": "Float", "width": 110},
		{"fieldname": "lookup_ambiguous", "label": "Ambiguous", "fieldtype": "Check", "width": 90},
		{"fieldname": "lookup_resolved_at", "label": "Resolved At", "fieldtype": "Datetime", "width": 150},
	]
	data = []
	for row in rows:
		data.append({
			"name": row.name,
			"camera_name": row.camera_name,
			"status": row.status,
			"camera_type": row.camera_type,
			"area": row.area,
			"latitude": row.latitude,
			"longitude": row.longitude,
			"address": row.address,
			"geo_admin_area": row.geo_admin_area,
			"geo_boundary": row.geo_boundary,
			"photo_count": photo_counts.get(row.name, 0),
			"lookup_source": row.lookup_source,
			"lookup_confidence": row.lookup_confidence,
			"lookup_ambiguous": row.lookup_ambiguous,
			"lookup_resolved_at": row.lookup_resolved_at,
		})
	return columns, data
