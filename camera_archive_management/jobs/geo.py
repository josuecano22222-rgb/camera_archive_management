"""Background workers for GeoJSON import and camera-coordinate resolution."""

from __future__ import annotations

import json
from decimal import Decimal

import frappe

from camera_archive_management.geo.coordinates import validate_pair
from camera_archive_management.geo.geometry import dumps_geojson, geometry_bounds, load_geometry
from camera_archive_management.geo.resolver import resolve_point

MAX_GEOJSON_BYTES = 25 * 1024 * 1024
MAX_FEATURES = 5000


def _private_file_content(file_url: str) -> bytes:
	file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not file_name:
		frappe.throw("GeoJSON source is not registered as a Frappe File.", frappe.ValidationError)
	file_doc = frappe.get_doc("File", file_name)
	if not file_doc.is_private:
		frappe.throw("GeoJSON source must be a private Frappe File.", frappe.ValidationError)
	if int(file_doc.file_size or 0) > MAX_GEOJSON_BYTES:
		frappe.throw("GeoJSON file exceeds the 25 MiB import limit.", frappe.ValidationError)
	content = file_doc.get_content()
	return content.encode("utf-8") if isinstance(content, str) else content


def import_geo_dataset(dataset_name: str) -> None:
	if not isinstance(dataset_name, str) or len(dataset_name) > 140:
		frappe.throw("Invalid dataset name.", frappe.ValidationError)
	dataset = frappe.get_doc("Geo Dataset", dataset_name)
	if dataset.import_status == "Complete":
		return
	if dataset.import_status not in {"Queued", "Running"}:
		return
	dataset.import_status = "Running"
	dataset.import_error = None
	dataset.flags.job_update = True
	dataset.save(ignore_permissions=True)
	savepoint = "cam_geo_import"
	frappe.db.savepoint(savepoint)
	try:
		raw = _private_file_content(dataset.source_file)
		if len(raw) > MAX_GEOJSON_BYTES:
			frappe.throw("GeoJSON file exceeds the 25 MiB import limit.", frappe.ValidationError)
		try:
			payload = json.loads(raw.decode("utf-8"), parse_float=Decimal)
		except (UnicodeDecodeError, json.JSONDecodeError) as exc:
			frappe.throw(f"GeoJSON must be valid UTF-8 JSON: {exc}", frappe.ValidationError)
		if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
			frappe.throw("Only GeoJSON FeatureCollection inputs are supported.", frappe.ValidationError)
		features = payload.get("features")
		if not isinstance(features, list) or len(features) > MAX_FEATURES:
			frappe.throw(f"GeoJSON must contain at most {MAX_FEATURES} features.", frappe.ValidationError)

		existing_rows = frappe.get_all(
			"Geo Boundary",
			filters={"dataset": dataset.name},
			fields=["name", "boundary_code"],
			order_by="boundary_code asc",
			limit_page_length=MAX_FEATURES * 2,
		)
		boundary_names = {row.boundary_code: row.name for row in existing_rows}
		admin_area_rows = frappe.get_all(
			"Geo Admin Area",
			filters={"dataset": dataset.name},
			fields=["name", "code"],
			order_by="code asc",
			limit_page_length=MAX_FEATURES * 2,
		)
		admin_area_names = {row.code: row.name for row in admin_area_rows}
		parsed_features = []
		seen_codes = set()
		for index, feature in enumerate(features):
			if not isinstance(feature, dict) or feature.get("type") != "Feature":
				frappe.throw(f"Feature {index} is not a GeoJSON Feature.", frappe.ValidationError)
			properties = feature.get("properties") or {}
			if not isinstance(properties, dict):
				frappe.throw(f"Feature {index} properties must be an object.", frappe.ValidationError)
			code = str(
				properties.get("boundary_code") or properties.get("code") or feature.get("id") or ""
			).strip()
			label = str(properties.get("label") or properties.get("name") or code).strip()
			try:
				level = int(properties.get("level"))
			except (TypeError, ValueError):
				frappe.throw(f"Feature {index} requires an integer level property.", frappe.ValidationError)
			if not code or len(code) > 140 or not label or len(label) > 140 or level < 0:
				frappe.throw(f"Feature {index} has invalid code, label, or level.", frappe.ValidationError)
			if code in seen_codes:
				frappe.throw(f"Duplicate boundary code {code!r} in GeoJSON.", frappe.ValidationError)
			seen_codes.add(code)
			geometry = load_geometry(feature.get("geometry"))
			west, south, east, north = geometry_bounds(geometry)
			parent_code = properties.get("parent_code")
			admin_area_code = properties.get("admin_area_code")
			if admin_area_code and str(admin_area_code).strip() not in admin_area_names:
				frappe.throw(
					f"Unknown admin_area_code {admin_area_code!r} for boundary {code!r}.",
					frappe.ValidationError,
				)
			parsed_features.append(
				{
					"code": code,
					"label": label,
					"level": level,
					"parent_code": str(parent_code).strip() if parent_code else None,
					"admin_area_code": str(admin_area_code).strip() if admin_area_code else None,
					"source_id": str(feature.get("id") or "")[:140],
					"geometry": geometry,
					"bounds": (west, south, east, north),
				}
			)

		feature_by_code = {feature["code"]: feature for feature in parsed_features}
		for feature in parsed_features:
			parent_code = feature["parent_code"]
			if parent_code:
				parent_feature = feature_by_code.get(parent_code)
				if parent_code not in boundary_names and not parent_feature:
					frappe.throw(
						f"Unknown parent_code {parent_code!r} for boundary {feature['code']!r}.",
						frappe.ValidationError,
					)
				if parent_feature and parent_feature["level"] >= feature["level"]:
					frappe.throw(
						"Parent boundary level must be lower than its child level.", frappe.ValidationError
					)

		parsed_features.sort(key=lambda item: (item["level"], item["code"]))
		new_names = {}
		for feature in parsed_features:
			if feature["code"] in boundary_names:
				new_names[feature["code"]] = boundary_names[feature["code"]]
				continue
			west, south, east, north = feature["bounds"]
			parent_name = new_names.get(feature["parent_code"]) or boundary_names.get(feature["parent_code"])
			doc = frappe.get_doc(
				{
					"doctype": "Geo Boundary",
					"dataset": dataset.name,
					"boundary_code": feature["code"],
					"label": feature["label"],
					"level": feature["level"],
					"parent_boundary": parent_name,
					"admin_area": admin_area_names.get(feature["admin_area_code"]),
					"source_id": feature["source_id"],
					"source_kind": "Imported",
					"west": str(west),
					"south": str(south),
					"east": str(east),
					"north": str(north),
					"geometries": [
						{
							"geometry_role": "Resolution",
							"geojson": dumps_geojson(feature["geometry"]),
							"srid": 4326,
						}
					],
				}
			)
			doc.flags.prevalidated_dataset_links = True
			doc.flags.prevalidated_boundary_code = True
			doc.insert(ignore_permissions=True)
			new_names[feature["code"]] = doc.name

		dataset = frappe.get_doc("Geo Dataset", dataset_name)
		dataset.import_status = "Complete"
		dataset.import_progress = 100
		dataset.feature_count = len(parsed_features)
		dataset.index_version = int(dataset.index_version or 0) + 1
		dataset.last_imported_at = frappe.utils.now_datetime()
		dataset.import_error = None
		dataset.flags.job_update = True
		dataset.save(ignore_permissions=True)
	except Exception as exc:
		frappe.db.rollback(save_point=savepoint)
		failed = frappe.get_doc("Geo Dataset", dataset_name)
		failed.import_status = "Failed"
		failed.import_error = (
			"Dataset import failed; check server logs. Source data is intentionally omitted."
		)
		failed.flags.job_update = True
		failed.save(ignore_permissions=True)
		frappe.logger("camera_archive_management.geo").error(
			"Dataset import failed for %s (%s)", dataset_name, type(exc).__name__
		)


def resolve_camera_batch(
	camera_names: list[str], dataset: str | None, overwrite: bool, requested_by: str
) -> None:
	"""Resolve up to 250 cameras and only update geographic links by explicit policy."""
	if not isinstance(camera_names, list) or len(camera_names) > 250:
		frappe.throw("Invalid camera batch size.", frappe.ValidationError)
	if not isinstance(requested_by, str) or not requested_by:
		frappe.throw("Missing requesting user.", frappe.ValidationError)
	for name in camera_names:
		if not frappe.db.exists("Camera", name):
			continue
		camera = frappe.get_doc("Camera", name)
		try:
			lat, lon = validate_pair(camera.latitude, camera.longitude)
		except ValueError:
			continue
		if lat is None or lon is None:
			continue
		result = resolve_point(lat, lon, dataset=dataset)
		if not overwrite and (camera.geo_admin_area or camera.geo_boundary):
			continue
		if result.get("boundary") and not result.get("ambiguous"):
			camera.geo_boundary = result["boundary"]["name"]
			if result["boundary"].get("admin_area"):
				camera.geo_admin_area = result["boundary"]["admin_area"]
		camera.lookup_source = result.get("provenance")
		camera.lookup_confidence = result.get("confidence")
		camera.lookup_ambiguous = int(bool(result.get("ambiguous")))
		camera.lookup_resolved_at = frappe.utils.now_datetime()
		camera.save(ignore_permissions=True)
