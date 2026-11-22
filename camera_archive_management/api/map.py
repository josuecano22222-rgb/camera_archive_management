"""Permission-filtered map payloads for the Camera Archive Desk map."""

from __future__ import annotations

import frappe
from frappe.utils import getdate

from camera_archive_management.geo.coordinates import validate_pair
from camera_archive_management.utils.files import is_safe_frappe_file_url

MAX_CAMERAS = 500
MAX_EVENTS = 2000
MAX_PHOTOS_PER_CAMERA = 12


@frappe.whitelist()
def get_custom_map_coords(doctype: str, filters=None, type=None) -> dict:
	"""Return permission-filtered point markers for DocTypes with nonstandard coordinate fields."""
	coordinate_fields = {
		"Geo Boundary": ("centroid_lat", "centroid_lon"),
		"Motion Event": ("latitude_snapshot", "longitude_snapshot"),
	}
	if not isinstance(doctype, str) or doctype not in coordinate_fields:
		frappe.throw("Map coordinates are not available for this DocType.", frappe.ValidationError)
	if not frappe.has_permission(doctype, "read"):
		frappe.throw("You do not have permission to read this DocType.", frappe.PermissionError)

	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	if filters is not None and not isinstance(filters, (list, dict)):
		frappe.throw("Map filters must be a list or object.", frappe.ValidationError)

	latitude_field, longitude_field = coordinate_fields[doctype]
	rows = frappe.get_list(
		doctype,
		filters=filters or [],
		fields=["name", latitude_field, longitude_field],
		order_by="name asc",
		limit_page_length=5000,
	)
	features = []
	for row in rows:
		try:
			latitude, longitude = validate_pair(row.get(latitude_field), row.get(longitude_field))
		except ValueError:
			continue
		if latitude is None or longitude is None:
			continue
		features.append({
			"type": "Feature",
			"properties": {"name": row.name},
			"geometry": {
				"type": "Point",
				"coordinates": [float(longitude), float(latitude)],
			},
		})
	return {"type": "FeatureCollection", "features": features}


def _clean_image_url(value: str | None, file_map: dict[str, object]) -> str | None:
	if not is_safe_frappe_file_url(value):
		return None
	matches = file_map.get(value, [])
	if len(matches) != 1:
		return None
	file_doc = matches[0]
	if file_doc.is_private and not frappe.has_permission("File", "read", file_doc.name, raise_exception=False):
		return None
	return value


def _load_file_map(urls: set[str]) -> dict[str, list]:
	if not urls:
		return {}
	rows = frappe.get_all(
		"File",
		filters={"file_url": ["in", sorted(urls)]},
		fields=["name", "file_url", "is_private"],
		order_by="file_url asc, name asc",
		limit_page_length=min(5000, len(urls) * 2),
	)
	result = {}
	for row in rows:
		result.setdefault(row.file_url, []).append(row)
	return result


def _date_filter(start: str | None, end: str | None) -> dict:
	filters = {}
	if start:
		try:
			start_date = getdate(start)
		except Exception:
			frappe.throw("start must be a valid ISO date.", frappe.ValidationError)
	else:
		start_date = None
	if end:
		try:
			end_date = getdate(end)
		except Exception:
			frappe.throw("end must be a valid ISO date.", frappe.ValidationError)
	else:
		end_date = None
	if start_date and end_date and end_date < start_date:
		frappe.throw("end must be on or after start.", frappe.ValidationError)
	if start_date and end_date and (end_date - start_date).days > 366:
		frappe.throw("Map date range is limited to 367 days.", frappe.ValidationError)
	if start_date and end_date:
		filters["detected_at"] = ["between", [f"{start_date} 00:00:00", f"{end_date} 23:59:59"]]
	elif start_date:
		filters["detected_at"] = [">=", f"{start_date} 00:00:00"]
	elif end_date:
		filters["detected_at"] = ["<=", f"{end_date} 23:59:59"]
	return filters


@frappe.whitelist(methods=["GET"])
def map_payload(
	camera: str | None = None,
	vehicle: str | None = None,
	event: str | None = None,
	start: str | None = None,
	end: str | None = None,
) -> dict:
	"""Return bounded, permission-filtered camera photos and vehicle movements."""
	if frappe.session.user == "Guest" or not frappe.has_permission("Camera", "read"):
		frappe.throw("Sign in with Camera read permission to use the map.", frappe.PermissionError)
	for value, label in ((camera, "camera"), (vehicle, "vehicle"), (event, "event")):
		if value is not None and (not isinstance(value, str) or not value or len(value) > 140):
			frappe.throw(f"Invalid {label} name.", frappe.ValidationError)

	camera_filters = {"status": "Active"}
	if camera:
		camera_filters = {"name": camera}
	camera_rows = frappe.get_list(
		"Camera",
		filters=camera_filters,
		fields=[
			"name", "camera_name", "status", "camera_type", "area", "address", "latitude", "longitude",
			"geo_admin_area", "geo_boundary",
		],
		order_by="camera_name asc, name asc",
		limit_page_length=MAX_CAMERAS,
	)
	camera_names = [row.name for row in camera_rows]
	photo_rows = (
		frappe.get_all(
			"Camera Photo",
			filters={"parent": ["in", camera_names], "parenttype": "Camera", "parentfield": "camera_photos"},
			fields=["name", "parent", "image", "caption", "description", "is_primary", "sort_order", "idx"],
			order_by="parent asc, is_primary desc, sort_order asc, idx asc, name asc",
			limit_page_length=MAX_CAMERAS * MAX_PHOTOS_PER_CAMERA,
		)
		if camera_names
		else []
	)

	event_rows = []
	if frappe.has_permission("Motion Event", "read"):
		event_filters = _date_filter(start, end)
		if camera:
			event_filters["camera"] = camera
		if vehicle:
			event_filters["vehicle"] = vehicle
		if event:
			event_filters["name"] = event
		event_rows = frappe.get_list(
			"Motion Event",
			filters=event_filters,
			fields=[
				"name", "camera", "motion_type", "detected_at", "vehicle", "latitude_snapshot",
				"longitude_snapshot", "address_snapshot", "importance", "notes",
			],
			order_by="detected_at asc, name asc",
			limit_page_length=MAX_EVENTS,
		)

	vehicle_names = sorted({row.vehicle for row in event_rows if row.vehicle})
	vehicles = (
		frappe.get_list(
			"CAM Vehicle",
			filters={"name": ["in", vehicle_names]},
			fields=["name", "vehicle_name", "vehicle_type", "vehicle_number", "vehicle_image", "status"],
			order_by="vehicle_name asc, name asc",
			limit_page_length=MAX_EVENTS,
		)
		if vehicle_names and frappe.has_permission("CAM Vehicle", "read")
		else []
	)
	vehicle_by_name = {row.name: row for row in vehicles}
	type_names = sorted({row.vehicle_type for row in vehicles if row.vehicle_type})
	vehicle_types = (
		frappe.get_list(
			"Vehicle Type",
			filters={"name": ["in", type_names]},
			fields=["name", "vehicle_type_image"],
			order_by="name asc",
			limit_page_length=500,
		)
		if type_names and frappe.has_permission("Vehicle Type", "read")
		else []
	)
	type_images = {row.name: row.vehicle_type_image for row in vehicle_types}

	all_urls = {row.image for row in photo_rows if row.image}
	all_urls.update(row.vehicle_image for row in vehicles if row.vehicle_image)
	all_urls.update(
		image for image in type_images.values() if image
	)
	file_map = _load_file_map(all_urls)
	photos_by_camera = {}
	for photo in photo_rows:
		photo_url = _clean_image_url(photo.image, file_map)
		if not photo_url:
			continue
		gallery = photos_by_camera.setdefault(photo.parent, [])
		if len(gallery) < MAX_PHOTOS_PER_CAMERA:
			gallery.append({
				"url": photo_url,
				"caption": photo.caption or "",
				"description": photo.description or "",
				"primary": bool(photo.is_primary),
			})

	cameras = []
	for row in camera_rows:
		try:
			lat, lon = validate_pair(row.latitude, row.longitude)
		except ValueError:
			continue
		if lat is None or lon is None:
			continue
		cameras.append({
			"name": row.name,
			"label": row.camera_name or row.name,
			"status": row.status,
			"camera_type": row.camera_type,
			"area": row.area,
			"address": row.address or "",
			"latitude": str(lat),
			"longitude": str(lon),
			"geo_admin_area": row.geo_admin_area,
			"geo_boundary": row.geo_boundary,
			"photos": photos_by_camera.get(row.name, []),
		})

	movements = []
	for event in event_rows:
		try:
			lat, lon = validate_pair(event.latitude_snapshot, event.longitude_snapshot)
		except ValueError:
			continue
		if lat is None or lon is None:
			continue
		vehicle = vehicle_by_name.get(event.vehicle)
		vehicle_image = None
		vehicle_type_image = None
		if vehicle:
			vehicle_image = _clean_image_url(vehicle.vehicle_image, file_map)
			vehicle_type_image = _clean_image_url(type_images.get(vehicle.vehicle_type), file_map)
		movements.append({
			"name": event.name,
			"camera": event.camera,
			"motion_type": event.motion_type,
			"detected_at": str(event.detected_at),
			"latitude": str(lat),
			"longitude": str(lon),
			"address": event.address_snapshot or "",
			"importance": event.importance or "",
			"notes": event.notes or "",
			"vehicle": event.vehicle,
			"vehicle_name": vehicle.vehicle_name if vehicle else event.vehicle,
			"vehicle_number": vehicle.vehicle_number if vehicle else "",
			"vehicle_type": vehicle.vehicle_type if vehicle else "",
			"vehicle_image": vehicle_image or vehicle_type_image,
			"vehicle_image_source": "vehicle" if vehicle_image else ("type" if vehicle_type_image else "fallback"),
		})

	return {
		"cameras": cameras,
		"movements": movements,
		"limits": {"cameras": MAX_CAMERAS, "movements": MAX_EVENTS, "photos_per_camera": MAX_PHOTOS_PER_CAMERA},
		"tile_layers": [
			{"id": "standard/base", "label": "Standard", "attribution": "© OpenStreetMap contributors"},
			{"id": "aerial/base", "label": "Aerial", "attribution": "© Esri"},
			{"id": "hybrid/base", "label": "Hybrid", "attribution": "© Esri"},
		],
	}
