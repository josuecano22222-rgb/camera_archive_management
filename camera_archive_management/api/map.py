"""Permission-filtered map payloads for the Camera Archive Desk map."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import frappe

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
		"Camera": ("latitude", "longitude"),
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
	fields = ["name", latitude_field, longitude_field]
	if doctype == "Camera":
		fields.extend([
			"camera_name", "status", "camera_type", "importance", "area", "serial_number", "camera_number",
			"installation_date", "address", "geo_admin_area", "geo_boundary", "field_of_view", "description",
			"lookup_source", "lookup_confidence", "lookup_ambiguous", "lookup_resolved_at",
			"camera_photos_json", "primary_image", "is_demo_record",
		])
	rows = frappe.get_list(
		doctype,
		filters=filters or [],
		fields=fields,
		order_by="name asc",
		limit_page_length=5000,
	)
	gallery_by_camera = {row.name: _camera_gallery(row) for row in rows} if doctype == "Camera" else {}
	all_urls = {
		photo["url"]
		for photos in gallery_by_camera.values()
		for photo in photos
	}
	file_map = _load_file_map(all_urls)
	features = []
	for row in rows:
		try:
			latitude, longitude = validate_pair(row.get(latitude_field), row.get(longitude_field))
		except ValueError:
			continue
		if latitude is None or longitude is None:
			continue
		properties = {"name": row.name}
		if doctype == "Camera":
			photos = []
			for photo in gallery_by_camera.get(row.name, []):
				url = _clean_image_url(photo["url"], file_map)
				photos.append({
					"url": url,
					"caption": photo.get("caption") or "",
					"description": photo.get("description") or "",
					"primary": bool(photo.get("is_primary")),
					"unavailable": not bool(url),
				})
			properties.update({
				"label": row.camera_name or row.name,
				"status": row.status or "",
				"is_demo_record": bool(row.is_demo_record),
				"camera_type": row.camera_type or "",
				"importance": row.importance or "",
				"area": row.area or "",
				"serial_number": row.serial_number or "",
				"camera_number": row.camera_number or "",
				"installation_date": str(row.installation_date) if row.installation_date else "",
				"address": row.address or "",
				"latitude": str(latitude),
				"longitude": str(longitude),
				"geo_admin_area": row.geo_admin_area or "",
				"geo_boundary": row.geo_boundary or "",
				"field_of_view": row.field_of_view or "",
				"description": row.description or "",
				"lookup_source": row.lookup_source or "",
				"lookup_confidence": row.lookup_confidence,
				"lookup_ambiguous": bool(row.lookup_ambiguous),
				"lookup_resolved_at": str(row.lookup_resolved_at) if row.lookup_resolved_at else "",
				"photos": photos,
			})
		features.append({
			"type": "Feature",
			"properties": properties,
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


def _parse_map_datetime(value: str, *, end_of_day: bool = False) -> datetime:
	if not isinstance(value, str) or not value or len(value) > 64:
		frappe.throw("Map dates must be ISO date or datetime values.", frappe.ValidationError)
	try:
		if len(value) == 10:
			parsed = datetime.strptime(value, "%Y-%m-%d")
			if end_of_day:
				parsed = parsed.replace(hour=23, minute=59, second=59)
		else:
			parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
		if parsed.tzinfo is not None:
			parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
		return parsed.replace(microsecond=0)
	except (TypeError, ValueError, OverflowError):
		frappe.throw("Map dates must be valid ISO dates or datetimes.", frappe.ValidationError)


def _date_filter(start: str | None, end: str | None) -> dict:
	start_datetime = _parse_map_datetime(start) if start else None
	end_datetime = _parse_map_datetime(end, end_of_day=True) if end else None
	if start_datetime and end_datetime and end_datetime < start_datetime:
		frappe.throw("end must be on or after start.", frappe.ValidationError)
	if start_datetime and end_datetime and end_datetime - start_datetime > timedelta(days=367):
		frappe.throw("Map date range is limited to 367 days.", frappe.ValidationError)
	if start_datetime and end_datetime:
		return {"detected_at": ["between", [start_datetime.strftime("%Y-%m-%d %H:%M:%S"), end_datetime.strftime("%Y-%m-%d %H:%M:%S")]]}
	if start_datetime:
		return {"detected_at": [">=", start_datetime.strftime("%Y-%m-%d %H:%M:%S")]}
	if end_datetime:
		return {"detected_at": ["<=", end_datetime.strftime("%Y-%m-%d %H:%M:%S")]}
	return {}


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
			"name", "camera_name", "status", "camera_type", "importance", "area", "serial_number",
			"camera_number", "installation_date", "address", "latitude", "longitude", "geo_admin_area",
			"geo_boundary", "field_of_view", "description", "lookup_source", "lookup_confidence",
			"lookup_ambiguous", "lookup_resolved_at", "camera_photos_json", "primary_image", "is_demo_record",
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
					"name", "camera", "camera_name_snapshot", "camera_type_snapshot", "camera_area_snapshot",
					"geo_admin_area_snapshot", "location_source_snapshot", "location_confidence_snapshot",
					"location_ambiguous_snapshot", "location_resolved_at_snapshot", "motion_type", "detected_at",
					"vehicle", "latitude_snapshot", "longitude_snapshot", "address_snapshot", "importance", "notes",
					"is_demo_record",
				],
				order_by="detected_at asc, name asc",
				limit_page_length=MAX_EVENTS,
			)

	nearby_by_event: dict[str, list[dict]] = {}
	if event_rows:
		nearby_rows = frappe.get_all(
			"Motion Event Nearby Camera",
			filters={"parent": ["in", [row.name for row in event_rows]]},
			fields=["parent", "camera", "distance_m", "bearing_compass", "area", "camera_status", "note"],
			order_by="parent asc, distance_m asc, idx asc",
			limit_page_length=MAX_EVENTS * 20,
		)
		for row in nearby_rows:
			nearby_by_event.setdefault(row.parent, []).append({
				"camera": row.camera or "",
				"distance_m": str(row.distance_m) if row.distance_m is not None else "",
				"bearing": row.bearing_compass or "",
				"area": row.area or "",
				"camera_status": row.camera_status or "",
				"note": row.note or "",
			})

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
			photos.append(
				{
					"url": photo_url,
					"caption": item.get("caption") or "",
					"description": item.get("description") or "",
					"primary": bool(item.get("is_primary")),
					"unavailable": not bool(photo_url),
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
			"importance": row.importance or "",
			"area": row.area,
			"serial_number": row.serial_number or "",
			"camera_number": row.camera_number or "",
			"installation_date": str(row.installation_date) if row.installation_date else "",
			"address": row.address or "",
			"latitude": str(lat),
			"longitude": str(lon),
			"geo_admin_area": row.geo_admin_area,
			"geo_boundary": row.geo_boundary,
			"field_of_view": row.field_of_view or "",
			"description": row.description or "",
			"lookup_source": row.lookup_source or "",
			"lookup_confidence": row.lookup_confidence,
			"lookup_ambiguous": bool(row.lookup_ambiguous),
			"lookup_resolved_at": str(row.lookup_resolved_at) if row.lookup_resolved_at else "",
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
			"camera_name": event.get("camera_name_snapshot") or event.camera,
			"camera_type": event.get("camera_type_snapshot") or "",
			"camera_area": event.get("camera_area_snapshot") or "",
			"geo_admin_area": event.get("geo_admin_area_snapshot") or "",
			"location_source": event.get("location_source_snapshot") or "",
			"location_confidence": event.get("location_confidence_snapshot"),
			"location_ambiguous": bool(event.get("location_ambiguous_snapshot")),
			"location_resolved_at": str(event.get("location_resolved_at_snapshot")) if event.get("location_resolved_at_snapshot") else "",
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
			"vehicle_status": vehicle.status if vehicle else "",
			"vehicle_image": vehicle_image or vehicle_type_image,
			"vehicle_image_source": "vehicle" if vehicle_image else ("type" if vehicle_type_image else "fallback"),
			"nearby_cameras": nearby_by_event.get(event.name, []),
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
