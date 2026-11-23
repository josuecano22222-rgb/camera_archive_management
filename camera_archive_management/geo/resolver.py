"""Dataset-agnostic local boundary and gazetteer reverse lookup."""

from __future__ import annotations

import math
from decimal import Decimal

import frappe
from frappe.query_builder.functions import Cast

from camera_archive_management.geo.coordinates import validate_pair
from camera_archive_management.geo.geometry import haversine_m, point_in_geometry

MAX_BOUNDARIES = 5000
MAX_GAZETTEER_CANDIDATES = 5000
MAX_HIERARCHY_DEPTH = 32


def _settings() -> dict:
	settings = frappe.get_single("CAM Geo Settings")
	return {
		"dataset": settings.active_dataset,
		"radius_m": int(settings.default_search_radius_m or 5000),
		"ambiguity_m": int(settings.ambiguity_threshold_m or 250),
	}


def _get_dataset(dataset: str | None) -> str:
	if dataset is not None and (not isinstance(dataset, str) or len(dataset) > 140):
		frappe.throw("Invalid Geo Dataset name.", frappe.ValidationError)
	name = dataset or _settings()["dataset"]
	if not name:
		frappe.throw("No active Geo Dataset is configured.", frappe.ValidationError)
	if not frappe.db.exists("Geo Dataset", name):
		frappe.throw("The requested Geo Dataset does not exist.", frappe.ValidationError)
	return name


def _candidate_boundaries(dataset: str, lat: Decimal, lon: Decimal) -> list:
	Boundary = frappe.qb.DocType("Geo Boundary")
	west = Cast(Boundary.west, "DECIMAL(65,30)")
	east = Cast(Boundary.east, "DECIMAL(65,30)")
	south = Cast(Boundary.south, "DECIMAL(65,30)")
	north = Cast(Boundary.north, "DECIMAL(65,30)")
	bbox_matches = ((west <= lon) & (east >= lon)) | ((west > east) & ((west <= lon) | (east >= lon)))
	return (
		frappe.qb.from_(Boundary)
		.select(
			Boundary.name,
			Boundary.dataset,
			Boundary.boundary_code,
			Boundary.label,
			Boundary.level,
			Boundary.parent_boundary,
			Boundary.admin_area,
			Boundary.west,
			Boundary.south,
			Boundary.east,
			Boundary.north,
			Boundary.area_m2,
		)
		.where((Boundary.dataset == dataset) & bbox_matches & (south <= lat) & (north >= lat))
		.orderby(Boundary.level, order=frappe.qb.desc)
		.orderby(Boundary.name)
		.limit(MAX_BOUNDARIES)
		.run(as_dict=True)
	)


def _matched_boundaries(dataset: str, lat: Decimal, lon: Decimal) -> list[dict]:
	rows = _candidate_boundaries(dataset, lat, lon)
	if not rows:
		return []
	names = [row.name for row in rows]
	geometries = frappe.get_all(
		"Geo Boundary Geometry",
		filters={"parent": ["in", names], "geometry_role": "Resolution"},
		fields=["parent", "geojson"],
		order_by="parent asc, idx asc",
		limit_page_length=MAX_BOUNDARIES,
	)
	geometry_by_boundary = {}
	for row in geometries:
		geometry_by_boundary.setdefault(row.parent, []).append(row.geojson)
	matches = []
	for row in rows:
		for geometry in geometry_by_boundary.get(row.name, []):
			try:
				if point_in_geometry(float(lon), float(lat), geometry):
					matches.append(row)
					break
			except ValueError:
				frappe.logger("camera_archive_management.geo").warning(
					"Invalid geometry skipped during point resolution: %s", row.name
				)
	matches.sort(key=lambda row: (-(row.level or 0), row.area_m2 or float("inf"), row.name))
	return matches


def _boundary_ancestors(start_name: str | None) -> list[dict]:
	chain = []
	frontier = {start_name} if start_name else set()
	seen = set()
	for _ in range(MAX_HIERARCHY_DEPTH):
		frontier -= seen
		if not frontier:
			break
		rows = frappe.get_all(
			"Geo Boundary",
			filters={"name": ["in", sorted(frontier)]},
			fields=["name", "boundary_code", "label", "level", "parent_boundary", "admin_area"],
			order_by="level desc, name asc",
			limit_page_length=len(frontier),
		)
		if not rows:
			break
		chain.extend(rows)
		seen.update(row.name for row in rows)
		frontier = {
			row.parent_boundary for row in rows if row.parent_boundary and row.parent_boundary not in seen
		}
	return chain


def _admin_area_ancestors(start_name: str | None) -> list[dict]:
	"""Walk a parent chain with one batched query per hierarchy level."""
	chain = []
	frontier = {start_name} if start_name else set()
	seen = set()
	for _ in range(MAX_HIERARCHY_DEPTH):
		frontier -= seen
		if not frontier:
			break
		rows = frappe.get_all(
			"Geo Admin Area",
			filters={"name": ["in", sorted(frontier)]},
			fields=["name", "code", "label", "level", "parent_area", "dataset"],
			order_by="level desc, name asc",
			limit_page_length=len(frontier),
		)
		if not rows:
			break
		chain.extend(rows)
		seen.update(row.name for row in rows)
		frontier = {row.parent_area for row in rows if row.parent_area and row.parent_area not in seen}
	return chain


def _nearest_gazetteer(dataset: str, lat: Decimal, lon: Decimal, radius_m: int) -> dict | None:
	lat_float, lon_float = float(lat), float(lon)
	delta_lat = Decimal(str(radius_m / 110_574.0))
	delta_lon = Decimal(str(min(180.0, radius_m / (111_320.0 * max(0.01, math.cos(math.radians(lat_float)))))))
	Place = frappe.qb.DocType("Geo Gazetteer Place")
	place_lat = Cast(Place.latitude, "DECIMAL(65,30)")
	place_lon = Cast(Place.longitude, "DECIMAL(65,30)")
	west, east = lon - delta_lon, lon + delta_lon
	if west < -180:
		longitude_matches = (place_lon >= west + 360) | (place_lon <= east)
	elif east > 180:
		longitude_matches = (place_lon >= west) | (place_lon <= east - 360)
	else:
		longitude_matches = (place_lon >= west) & (place_lon <= east)
	rows = (
		frappe.qb.from_(Place)
		.select(
			Place.name,
			Place.place_code,
			Place.place_name,
			Place.latitude,
			Place.longitude,
			Place.feature_type,
			Place.admin_area,
		)
		.where(
			(Place.dataset == dataset)
			& (place_lat >= max(Decimal(-90), lat - delta_lat))
			& (place_lat <= min(Decimal(90), lat + delta_lat))
			& longitude_matches
		)
		.orderby(Place.name)
		.limit(MAX_GAZETTEER_CANDIDATES)
		.run(as_dict=True)
	)
	if not rows:
		return None
	for row in rows:
		row.distance_m = haversine_m(lat_float, lon_float, float(row.latitude), float(row.longitude))
	valid = [row for row in rows if row.distance_m <= radius_m]
	if not valid:
		return None
	nearest = min(valid, key=lambda row: (row.distance_m, row.name))
	return {
		"name": nearest.name,
		"place_code": nearest.place_code,
		"place_name": nearest.place_name,
		"latitude": str(nearest.latitude),
		"longitude": str(nearest.longitude),
		"feature_type": nearest.feature_type,
		"admin_area": nearest.admin_area,
		"distance_m": round(nearest.distance_m, 1),
		"provenance": "local_gazetteer",
	}


def resolve_point(latitude, longitude, dataset: str | None = None, radius_m: int | None = None) -> dict:
	"""Resolve a WGS84 point against local boundaries and gazetteer records."""
	try:
		lat_d, lon_d = validate_pair(latitude, longitude)
	except ValueError as exc:
		frappe.throw(str(exc), frappe.ValidationError)
	if lat_d is None or lon_d is None:
		frappe.throw("Latitude and longitude are required.", frappe.ValidationError)
	config = _settings()
	dataset_name = _get_dataset(dataset)
	if radius_m in (None, ""):
		radius = config["radius_m"]
	elif isinstance(radius_m, bool) or not str(radius_m).isdigit():
		frappe.throw("Lookup radius must be a whole number of meters.", frappe.ValidationError)
	else:
		radius = int(radius_m)
	if not 1 <= radius <= 100_000:
		frappe.throw("Lookup radius must be between 1 and 100000 meters.", frappe.ValidationError)

	matches = _matched_boundaries(dataset_name, lat_d, lon_d)
	primary = matches[0] if matches else None
	chain = _boundary_ancestors(primary.parent_boundary) if primary else []
	if primary:
		chain.insert(
			0,
			{
				"name": primary.name,
				"boundary_code": primary.boundary_code,
				"label": primary.label,
				"level": primary.level,
				"parent_boundary": primary.parent_boundary,
				"admin_area": primary.admin_area,
			},
		)
	gazetteer = _nearest_gazetteer(dataset_name, lat_d, lon_d, radius)
	admin_area_start = primary.admin_area if primary else (gazetteer.get("admin_area") if gazetteer else None)
	admin_hierarchy = _admin_area_ancestors(admin_area_start)
	ambiguous = False
	candidates = []
	if primary:
		same_level = [row for row in matches if row.level == primary.level]
		ambiguous = len(same_level) > 1
		candidates = [
			{"name": row.name, "code": row.boundary_code, "label": row.label} for row in same_level[:20]
		]

	return {
		"dataset": dataset_name,
		"coordinates": {"latitude": str(lat_d), "longitude": str(lon_d)},
		"boundary": (
			{
				"name": primary.name,
				"code": primary.boundary_code,
				"label": primary.label,
				"level": primary.level,
				"admin_area": primary.admin_area,
			}
			if primary
			else None
		),
		"hierarchy": [dict(row) for row in chain],
		"admin_hierarchy": [dict(row) for row in admin_hierarchy],
		"nearest_place": gazetteer,
		"provenance": "local_boundary" if primary else ("local_gazetteer" if gazetteer else "no_local_match"),
		"confidence": 0.95
		if primary and not ambiguous
		else (0.6 if primary else (0.55 if gazetteer else 0.0)),
		"ambiguous": ambiguous,
		"candidates": candidates,
		"on_land": bool(primary),
	}
