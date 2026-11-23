"""Permission-filtered map payloads for the Camera Archive Desk map."""

from __future__ import annotations

import json

import frappe
from frappe.utils import getdate

from camera_archive_management.geo.coordinates import validate_pair
from camera_archive_management.utils.files import is_safe_frappe_file_url

MAX_CAMERAS = 500
MAX_EVENTS = 2000
CORE_COUNTRY_DATASET_ID = "natural-earth-admin0-110m"
MAX_CORE_COUNTRY_BOUNDARIES = 200


@frappe.whitelist(methods=["GET"])
def get_core_country_boundaries() -> dict:
	"""Return the bundled public-domain generalized country outlines for map context."""
	if frappe.session.user == "Guest" or not frappe.has_permission("Camera", "read"):
		frappe.throw("Sign in with Camera read permission to use the map.", frappe.PermissionError)
	dataset = frappe.db.get_value("Geo Dataset", {"dataset_id": CORE_COUNTRY_DATASET_ID}, "name")
	if not dataset:
		return {"type": "FeatureCollection", "features": []}
	# This fixed dataset is public-domain application reference data, not site-owned sensitive boundaries.
	rows = frappe.get_all(
		"Geo Boundary",
		filters={"dataset": dataset},
		fields=["name", "boundary_code", "label"],
		order_by="label asc, name asc",
		limit_page_length=MAX_CORE_COUNTRY_BOUNDARIES,
	)
	if len(rows) >= MAX_CORE_COUNTRY_BOUNDARIES:
		frappe.throw("Bundled country boundary count exceeded its safe map payload limit.", frappe.ValidationError)
	geometries = frappe.get_all(
		"Geo Boundary Geometry",
		filters={"parent": ["in", [row.name for row in rows]], "geometry_role": "Resolution"},
		fields=["parent", "geojson"],
		order_by="parent asc, idx asc",
		limit_page_length=MAX_CORE_COUNTRY_BOUNDARIES,
	) if rows else []
	geometry_by_boundary = {}
	for row in geometries:
		geometry_by_boundary.setdefault(row.parent, json.loads(row.geojson))
	return {
		"type": "FeatureCollection",
		"features": [
			{
				"type": "Feature",
				"properties": {"name": row.name, "code": row.boundary_code, "label": row.label},
				"geometry": geometry_by_boundary[row.name],
			}
			for row in rows
			if row.name in geometry_by_boundary
		],
	}


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


def _camera_photo_sort_key(photo: dict) -> tuple[bool, int]:
	order = photo.get("sort_order", 0)
	if isinstance(order, bool) or not isinstance(order, int):
		order = 0
	return not bool(photo.get("is_primary")), order


def _camera_gallery(row) -> list[dict]:
	try:
		photos = json.loads(row.camera_photos_json or "[]")
	except (TypeError, json.JSONDecodeError):
		photos = []
	if not isinstance(photos, list):
		photos = []

	valid = [
		photo
		for photo in photos
		if isinstance(photo, dict)
		and is_safe_frappe_file_url(photo.get("url"))
	]
	if row.primary_image and is_safe_frappe_file_url(row.primary_image) and not any(
		photo["url"] == row.primary_image for photo in valid
	):
		valid.append({"url": row.primary_image, "caption": "", "description": "", "is_primary": True, "sort_order": -1})
	return sorted(valid, key=_camera_photo_sort_key)


def _load_file_map(urls: set[str]) -> dict[str, list]:
	"""Load every referenced File in bounded query batches, without capping gallery size."""
	if not urls:
		return {}
	result = {}
	ordered_urls = sorted(urls)
	for offset in range(0, len(ordered_urls), 500):
		rows = frappe.get_all(
			"File",
			filters={"file_url": ["in", ordered_urls[offset : offset + 500]]},
			fields=["name", "file_url", "is_private"],
			order_by="file_url asc, name asc",
			limit_page_length=0,
		)
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
	include_demo=0,
	camera_status: str | None = None,
	area: str | None = None,
) -> dict:
	"""Return bounded, permission-filtered camera photos and vehicle movements."""
	if frappe.session.user == "Guest" or not frappe.has_permission("Camera", "read"):
		frappe.throw("Sign in with Camera read permission to use the map.", frappe.PermissionError)
	for value, label in ((camera, "camera"), (vehicle, "vehicle"), (event, "event"), (area, "area")):
		if value is not None and (not isinstance(value, str) or not value or len(value) > 140):
			frappe.throw(f"Invalid {label} name.", frappe.ValidationError)
	if camera_status not in (None, "", "all", "Active", "Inactive", "Maintenance"):
		frappe.throw("Invalid camera status filter.", frappe.ValidationError)
	if camera_status == "":
		camera_status = None
	if include_demo in (True, 1, "1"):
		include_demo = True
	elif include_demo in (False, 0, "0", None, ""):
		include_demo = False
	else:
		frappe.throw("include_demo must be 0 or 1.", frappe.ValidationError)

	camera_filters = {"name": camera} if camera else {}
	if camera_status and camera_status != "all":
		camera_filters["status"] = camera_status
	elif not camera and camera_status != "all":
		camera_filters["status"] = "Active"
	if area:
		camera_filters["area"] = area
	if not include_demo:
		camera_filters["is_demo_record"] = 0
	camera_rows = frappe.get_list(
		"Camera",
		filters=camera_filters,
		fields=[
			"name", "camera_name", "status", "camera_type", "area", "address", "latitude", "longitude",
			"geo_admin_area", "geo_boundary", "camera_photos_json", "primary_image", "is_demo_record",
		],
		order_by="camera_name asc, name asc",
		limit_page_length=MAX_CAMERAS,
	)
	gallery_by_camera = {row.name: _camera_gallery(row) for row in camera_rows}

	event_rows = []
	if frappe.has_permission("Motion Event", "read"):
		event_filters = _date_filter(start, end)
		if not include_demo:
			event_filters["is_demo_record"] = 0
		filter_events_by_camera_scope = bool(area or camera_status in {"Active", "Inactive", "Maintenance"})
		event_camera_names = [row.name for row in camera_rows] if filter_events_by_camera_scope else []
		empty_camera_scope = filter_events_by_camera_scope and not event_camera_names
		if filter_events_by_camera_scope and not empty_camera_scope:
			event_filters["camera"] = ["in", event_camera_names]
		elif camera:
			event_filters["camera"] = camera
		if vehicle:
			event_filters["vehicle"] = vehicle
		if event:
			event_filters["name"] = event
		if not empty_camera_scope:
			event_rows = frappe.get_list(
				"Motion Event",
				filters=event_filters,
				fields=[
					"name", "camera", "motion_type", "detected_at", "vehicle", "latitude_snapshot",
					"longitude_snapshot", "address_snapshot", "importance", "notes", "is_demo_record",
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

	all_urls = {
		photo["url"]
		for photos in gallery_by_camera.values()
		for photo in photos
	}
	all_urls.update(row.vehicle_image for row in vehicles if row.vehicle_image)
	all_urls.update(image for image in type_images.values() if image)
	file_map = _load_file_map(all_urls)
	photos_by_camera = {}
	for camera_name, items in gallery_by_camera.items():
		photos = []
		for item in items:
			photo_url = _clean_image_url(item["url"], file_map)
			if not photo_url:
				continue
			photos.append(
				{
					"url": photo_url,
					"caption": item.get("caption") or "",
					"description": item.get("description") or "",
					"primary": bool(item.get("is_primary")),
				}
			)
		photos_by_camera[camera_name] = photos

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
			"is_demo_record": bool(row.is_demo_record),
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
			"is_demo_record": bool(event.is_demo_record),
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
		"limits": {"cameras": MAX_CAMERAS, "movements": MAX_EVENTS},
		"tile_layers": [
			{"id": "standard/base", "label": "Standard", "attribution": "© OpenStreetMap contributors"},
			{"id": "aerial/base", "label": "Aerial", "attribution": "© Esri"},
			{"id": "hybrid/base", "label": "Hybrid", "attribution": "© Esri"},
		],
	}
