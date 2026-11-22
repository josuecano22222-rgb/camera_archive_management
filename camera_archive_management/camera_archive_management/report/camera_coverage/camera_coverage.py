from __future__ import annotations

import json

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
			"lookup_resolved_at", "camera_photos_json", "is_demo_record",
		],
		order_by="camera_name asc, name asc",
		limit_page_length=5000,
	)
	photo_counts = {}
	for row in rows:
		try:
			gallery = json.loads(row.camera_photos_json or "[]")
		except (TypeError, json.JSONDecodeError):
			gallery = []
		photo_counts[row.name] = len(gallery) if isinstance(gallery, list) else 0
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
		{"fieldname": "is_demo_record", "label": "Synthetic Demo", "fieldtype": "Check", "width": 100},
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
			"is_demo_record": row.is_demo_record,
			"lookup_source": row.lookup_source,
			"lookup_confidence": row.lookup_confidence,
			"lookup_ambiguous": row.lookup_ambiguous,
			"lookup_resolved_at": row.lookup_resolved_at,
		})
	return columns, data
