from __future__ import annotations

import frappe
from frappe.utils import getdate

from camera_archive_management.utils.files import is_safe_frappe_file_url


def _visible_image(value: str | None) -> str | None:
	if not is_safe_frappe_file_url(value):
		return None
	files = frappe.get_all(
		"File", filters={"file_url": value}, fields=["name", "is_private"], order_by="name asc", limit_page_length=2
	)
	if len(files) != 1:
		return None
	if files[0].is_private and not frappe.has_permission("File", "read", files[0].name, throw=False):
		return None
	return value


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {}
	start = getdate(filters.start_date) if filters.start_date else None
	end = getdate(filters.end_date) if filters.end_date else None
	if start and end and end < start:
		frappe.throw("End date must not be earlier than start date.", frappe.ValidationError)
	if start and end and (end - start).days > 366:
		frappe.throw("Movement report range cannot exceed 367 days.", frappe.ValidationError)
	if start and end:
		conditions["detected_at"] = ["between", [f"{start} 00:00:00", f"{end} 23:59:59"]]
	elif start:
		conditions["detected_at"] = [">=", f"{start} 00:00:00"]
	elif end:
		conditions["detected_at"] = ["<=", f"{end} 23:59:59"]
	if filters.get("vehicle"):
		conditions["vehicle"] = filters.vehicle

	events = frappe.get_list(
		"Motion Event",
		filters=conditions,
		fields=[
			"name", "detected_at", "motion_type", "camera", "vehicle", "latitude_snapshot",
			"longitude_snapshot", "address_snapshot", "importance",
		],
		order_by="detected_at desc, name asc",
		limit_page_length=5000,
	)
	vehicle_names = sorted({row.vehicle for row in events if row.vehicle})
	vehicles = (
		frappe.get_list(
			"CAM Vehicle",
			filters={"name": ["in", vehicle_names]},
			fields=["name", "vehicle_name", "vehicle_number", "vehicle_type", "vehicle_image"],
			order_by="vehicle_name asc, name asc",
			limit_page_length=5000,
		)
		if vehicle_names and frappe.has_permission("CAM Vehicle", "read")
		else []
	)
	by_name = {row.name: row for row in vehicles}
	type_names = sorted({row.vehicle_type for row in vehicles if row.vehicle_type})
	types = (
		frappe.get_list(
			"Vehicle Type", filters={"name": ["in", type_names]}, fields=["name", "vehicle_type_image"],
			order_by="name asc", limit_page_length=500,
		)
		if type_names and frappe.has_permission("Vehicle Type", "read")
		else []
	)
	type_image = {row.name: row.vehicle_type_image for row in types}

	columns = [
		{"fieldname": "name", "label": "Motion Event", "fieldtype": "Link", "options": "Motion Event", "width": 150},
		{"fieldname": "detected_at", "label": "Detected At", "fieldtype": "Datetime", "width": 150},
		{"fieldname": "vehicle_name", "label": "Vehicle", "fieldtype": "Data", "width": 190},
		{"fieldname": "vehicle_number", "label": "Vehicle Number", "fieldtype": "Data", "width": 130},
		{"fieldname": "vehicle_image", "label": "Vehicle", "fieldtype": "Data", "width": 74},
		{"fieldname": "vehicle", "label": "CAM Vehicle", "fieldtype": "Link", "options": "CAM Vehicle", "width": 150},
		{"fieldname": "motion_type", "label": "Movement", "fieldtype": "Data", "width": 90},
		{"fieldname": "camera", "label": "Camera", "fieldtype": "Link", "options": "Camera", "width": 140},
		{"fieldname": "latitude_snapshot", "label": "Latitude (exact)", "fieldtype": "Data", "width": 140},
		{"fieldname": "longitude_snapshot", "label": "Longitude (exact)", "fieldtype": "Data", "width": 140},
		{"fieldname": "address_snapshot", "label": "Address Snapshot", "fieldtype": "Data", "width": 240},
		{"fieldname": "importance", "label": "Importance", "fieldtype": "Data", "width": 90},
	]
	data = []
	for event in events:
		vehicle = by_name.get(event.vehicle)
		image = None
		if vehicle:
			image = _visible_image(vehicle.vehicle_image)
			if not image and vehicle.vehicle_type:
				image = _visible_image(type_image.get(vehicle.vehicle_type))
		data.append({
			"name": event.name,
			"detected_at": event.detected_at,
			"vehicle_name": vehicle.vehicle_name if vehicle else (event.vehicle or "Unidentified vehicle"),
			"vehicle_number": vehicle.vehicle_number if vehicle else "",
			"vehicle_image": image or "🚘",
			"vehicle": event.vehicle,
			"motion_type": event.motion_type,
			"camera": event.camera,
			"latitude_snapshot": event.latitude_snapshot,
			"longitude_snapshot": event.longitude_snapshot,
			"address_snapshot": event.address_snapshot,
			"importance": event.importance,
		})
	return columns, data
