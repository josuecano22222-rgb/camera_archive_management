"""Permission-checked endpoints for the bundled Natural Earth vector pack.

All endpoints are read-only, require an authenticated non-Guest session with
Camera read permission (the same gate as the map payload), and serve only the
committed public-domain reference pack — never the network. Site-owned data
(cameras, motion events) is joined through ``frappe.get_list`` so per-user
permissions always apply.
"""

from __future__ import annotations

import json
import math

import frappe

from camera_archive_management.geo import natural_earth as ne
from camera_archive_management.geo.coordinates import validate_pair

MAX_CHOROPLETH_CAMERAS = 5000
MAX_CUSTOM_VALUES = 300
MAX_IDENTIFIER_LENGTH = 64


def _require_map_reader() -> None:
	if frappe.session.user == "Guest" or not frappe.has_permission("Camera", "read"):
		frappe.throw("Sign in with Camera read permission to use the map.", frappe.PermissionError)


def _validate_layer_id(layer_id) -> str:
	if not isinstance(layer_id, str) or not layer_id or len(layer_id) > MAX_IDENTIFIER_LENGTH:
		frappe.throw("A valid layer id is required.", frappe.ValidationError)
	if not ne.layer_spec(layer_id):
		frappe.throw("Unknown Natural Earth layer.", frappe.ValidationError)
	return layer_id


def _validate_pair_or_none(latitude, longitude) -> tuple[float, float] | None:
	try:
		lat, lon = validate_pair(latitude, longitude)
	except ValueError as exc:
		frappe.throw(str(exc), frappe.ValidationError)
	if lat is None:
		return None
	return float(lat), float(lon)


@frappe.whitelist(methods=["GET"])
def get_catalog() -> dict:
	"""Return layer metadata, provenance, licensing, and limitations (no geometry)."""
	_require_map_reader()
	try:
		catalog = ne.catalog()
		return {**catalog, "summary": ne.summary()}
	except ne.NaturalEarthError as exc:
		frappe.throw(str(exc), frappe.ValidationError)


@frappe.whitelist(methods=["GET"])
def get_layer(layer_id: str) -> dict:
	"""Return one integrity-checked bundled layer as a FeatureCollection."""
	_require_map_reader()
	layer_id = _validate_layer_id(layer_id)
	try:
		spec = ne.layer_spec(layer_id)
		payload = ne.load_layer(layer_id)
	except ne.NaturalEarthError as exc:
		frappe.throw(str(exc), frappe.ValidationError)
	return {
		"layer": {
			key: spec[key]
			for key in (
				"id",
				"label",
				"category",
				"theme",
				"geometry",
				"scale",
				"name_field",
				"description",
				"style",
				"feature_count",
				"bounds",
				"source",
				"sha256",
			)
		},
		"geojson": payload,
		"attribution": ne.catalog()["attribution"],
	}


@frappe.whitelist(methods=["GET"])
def get_country_profile(code: str | None = None, latitude=None, longitude=None) -> dict:
	"""Return the bundled profile for a country by ISO code or by coordinate."""
	_require_map_reader()
	if code is not None and (not isinstance(code, str) or not code.strip() or len(code) > 8):
		frappe.throw("Country code must be a short ISO identifier.", frappe.ValidationError)
	pair = _validate_pair_or_none(latitude, longitude)
	if code is None and pair is None:
		frappe.throw("Provide a country code or a latitude/longitude pair.", frappe.ValidationError)
	try:
		if pair is not None:
			profile = ne.country_profile(longitude=pair[1], latitude=pair[0])
		else:
			profile = ne.country_profile(code)
	except ne.NaturalEarthError as exc:
		frappe.throw(str(exc), frappe.ValidationError)
	return {"profile": profile, "attribution": ne.catalog()["attribution"]}


def _camera_country_counts() -> dict:
	"""Count readable cameras per country using bundle point-in-polygon joins."""
	rows = frappe.get_list(
		"Camera",
		fields=["name", "latitude", "longitude"],
		limit_page_length=MAX_CHOROPLETH_CAMERAS + 1,
	)
	truncated = len(rows) > MAX_CHOROPLETH_CAMERAS
	counts: dict[str, int] = {}
	camera_country: dict[str, str] = {}
	located = 0
	cache: dict[tuple, str] = {}
	for row in rows[:MAX_CHOROPLETH_CAMERAS]:
		try:
			lat, lon = validate_pair(row.latitude, row.longitude)
		except ValueError:
			continue
		if lat is None:
			continue
		located += 1
		key = (round(float(lat), 4), round(float(lon), 4))
		if key not in cache:
			properties = ne.find_country(key[1], key[0])
			cache[key] = ne.iso_code(properties) if properties else ""
		code = cache[key]
		if code:
			counts[code] = counts.get(code, 0) + 1
			camera_country[row.name] = code
	return {"counts": counts, "camera_country": camera_country, "located": located, "truncated": truncated}


def _movement_country_counts(camera_country: dict) -> dict:
	"""Sum readable motion events per country through their cameras."""
	if not frappe.has_permission("Motion Event", "read"):
		frappe.throw("You do not have permission to read Motion Event.", frappe.PermissionError)
	rows = frappe.get_list(
		"Motion Event",
		fields=["camera", "count(name) as total"],
		group_by="camera",
		limit_page_length=MAX_CHOROPLETH_CAMERAS,
	)
	counts: dict[str, int] = {}
	for row in rows:
		code = camera_country.get(row.camera)
		if code:
			try:
				total = int(row.total)
			except (TypeError, ValueError):
				continue
			counts[code] = counts.get(code, 0) + total
	return counts


def _custom_values(raw) -> dict:
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except json.JSONDecodeError:
			frappe.throw("Custom values must be a JSON object of ISO code to number.", frappe.ValidationError)
	if not isinstance(raw, dict) or len(raw) > MAX_CUSTOM_VALUES:
		frappe.throw("Custom values must be an object with at most 300 entries.", frappe.ValidationError)
	values = {}
	for code, value in raw.items():
		if not isinstance(code, str) or len(code) > 8 or not code.strip():
			frappe.throw("Custom value keys must be short ISO country codes.", frappe.ValidationError)
		if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(float(value)):
			frappe.throw("Custom values must be finite numbers.", frappe.ValidationError)
		values[code.strip().upper()] = float(value)
	return values


@frappe.whitelist(methods=["GET"])
def get_country_choropleth(metric: str = "cameras", method: str = "quantile", classes=5, values=None) -> dict:
	"""Aggregate a metric per country and classify it for choropleth rendering.

	Metrics: ``cameras`` and ``movements`` join permission-filtered site data to
	countries through the bundle; ``population`` and ``gdp`` use Natural Earth's
	own estimates; ``custom`` accepts an external ISO-code→number mapping (e.g.
	climate or business data) supplied as JSON.
	"""
	_require_map_reader()
	if metric not in ("cameras", "movements", "population", "gdp", "custom"):
		frappe.throw("Unknown choropleth metric.", frappe.ValidationError)
	try:
		classes = int(classes)
	except (TypeError, ValueError):
		frappe.throw("Classes must be an integer.", frappe.ValidationError)
	meta: dict = {"metric": metric, "method": method, "provenance": "natural_earth_bundle"}
	try:
		if metric in ("cameras", "movements"):
			camera_stats = _camera_country_counts()
			if metric == "cameras":
				per_country = camera_stats["counts"]
			else:
				per_country = _movement_country_counts(camera_stats["camera_country"])
			meta["located_cameras"] = camera_stats["located"]
			meta["truncated"] = camera_stats["truncated"]
			meta["provenance"] = "site_data"
		elif metric in ("population", "gdp"):
			field = "POP_EST" if metric == "population" else "GDP_MD"
			per_country = {}
			for feature in ne.load_layer(ne.COUNTRY_LAYER)["features"]:
				properties = feature.get("properties") or {}
				code = ne.iso_code(properties)
				value = properties.get(field)
				if code and isinstance(value, int | float) and not isinstance(value, bool) and value > 0:
					per_country[code] = float(value)
			meta["note"] = "Natural Earth estimates, not a live statistical database."
		else:
			per_country = _custom_values(values)
			meta["provenance"] = "external_join"
		classification = ne.classify(list(per_country.values()), method=method, classes=classes)
	except ne.NaturalEarthError as exc:
		frappe.throw(str(exc), frappe.ValidationError)
	return {"values": per_country, "classification": classification, "meta": meta}
