"""Bundled Natural Earth vector layers: catalog, loading, country intelligence, choropleth.

This module is framework-independent (no Frappe import) so it can be unit-tested
without a running site. It reads the committed data pack under
``data/natural_earth/`` and never touches the network. The Frappe API layer
(``api/natural_earth.py``) wraps these helpers with permission checks.

The pack covers cultural and physical geography at three cartographic scales
(1:110m, 1:50m, 1:10m) and all three vector geometry families (points, lines,
polygons). It is generalized reference data, not legal or cadastral boundaries.
"""

from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from camera_archive_management.geo.geometry import (
	geodesic_area_m2,
	geometry_bounds,
	load_geometry,
	point_in_geometry,
)

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "natural_earth"
CATALOG_PATH = DATA_DIR / "catalog.json"
COUNTRY_LAYER = "countries_110m"
COUNTRY_DETAIL_LAYER = "countries_50m"
PLACES_LAYER = "populated_places_110m"
MAX_LAYER_FEATURES = 5000
CHOROPLETH_METRICS = ("cameras", "movements")
CLASSIFICATION_METHODS = ("quantile", "equal_interval")


class NaturalEarthError(ValueError):
	"""Raised when the bundled pack is missing, corrupt, or fails its integrity pin."""


@lru_cache(maxsize=1)
def catalog() -> dict:
	"""Return the validated layer catalog (metadata only, no geometry)."""
	if not CATALOG_PATH.is_file():
		raise NaturalEarthError("The Natural Earth catalog is missing.")
	try:
		data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
	except (UnicodeDecodeError, json.JSONDecodeError) as exc:
		raise NaturalEarthError("The Natural Earth catalog is not valid JSON.") from exc
	if not isinstance(data, dict) or not isinstance(data.get("layers"), list) or not data["layers"]:
		raise NaturalEarthError("The Natural Earth catalog has no layers.")
	seen = set()
	for layer in data["layers"]:
		if not isinstance(layer, dict) or not layer.get("id") or layer["id"] in seen:
			raise NaturalEarthError("The Natural Earth catalog has an invalid or duplicate layer id.")
		seen.add(layer["id"])
		for key in ("label", "category", "geometry", "scale", "file", "sha256", "feature_count"):
			if key not in layer:
				raise NaturalEarthError(f"Natural Earth layer {layer['id']} is missing {key}.")
		if layer["category"] not in ("cultural", "physical"):
			raise NaturalEarthError(f"Natural Earth layer {layer['id']} has an invalid category.")
		if layer["geometry"] not in ("point", "line", "polygon"):
			raise NaturalEarthError(f"Natural Earth layer {layer['id']} has an invalid geometry family.")
	return data


def layer_spec(layer_id: str) -> dict | None:
	for layer in catalog()["layers"]:
		if layer["id"] == layer_id:
			return layer
	return None


def layer_ids() -> list[str]:
	return [layer["id"] for layer in catalog()["layers"]]


@lru_cache(maxsize=32)
def load_layer(layer_id: str) -> dict:
	"""Load and integrity-check one bundled layer, returning a FeatureCollection."""
	spec = layer_spec(layer_id)
	if not spec:
		raise NaturalEarthError(f"Unknown Natural Earth layer {layer_id!r}.")
	path = DATA_DIR / spec["file"]
	if not path.is_file():
		raise NaturalEarthError(f"The Natural Earth layer file {spec['file']} is missing.")
	raw = path.read_bytes()
	if hashlib.sha256(raw).hexdigest() != spec["sha256"]:
		raise NaturalEarthError(f"The Natural Earth layer {layer_id} failed its integrity check.")
	try:
		payload = json.loads(raw.decode("utf-8"))
	except (UnicodeDecodeError, json.JSONDecodeError) as exc:
		raise NaturalEarthError(f"The Natural Earth layer {layer_id} is not valid JSON.") from exc
	if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
		raise NaturalEarthError(f"The Natural Earth layer {layer_id} is not a FeatureCollection.")
	features = payload.get("features")
	if not isinstance(features, list) or len(features) > MAX_LAYER_FEATURES:
		raise NaturalEarthError(f"The Natural Earth layer {layer_id} has an invalid feature list.")
	if len(features) != spec["feature_count"]:
		raise NaturalEarthError(
			f"The Natural Earth layer {layer_id} feature count does not match its catalog."
		)
	return payload


def summary() -> dict:
	"""Aggregate counts by category, geometry family, and scale."""
	data = catalog()
	layers = data["layers"]
	return {
		"layers": len(layers),
		"cultural": sum(1 for layer in layers if layer["category"] == "cultural"),
		"physical": sum(1 for layer in layers if layer["category"] == "physical"),
		"point": sum(1 for layer in layers if layer["geometry"] == "point"),
		"line": sum(1 for layer in layers if layer["geometry"] == "line"),
		"polygon": sum(1 for layer in layers if layer["geometry"] == "polygon"),
		"scales": sorted({layer["scale"] for layer in layers}),
		"features": sum(layer["feature_count"] for layer in layers),
		"license": data.get("license"),
		"revision": data.get("revision"),
	}


# ---------------------------------------------------------------------------
# Country intelligence
# ---------------------------------------------------------------------------


def iso_code(properties: dict) -> str:
	"""Natural Earth uses '-99' for some ISO_A3 values (e.g. France, Norway).

	Prefer a valid alphabetic ISO_A3, then fall back to ADM0_A3 which carries the
	real three-letter code in those cases.
	"""
	iso = properties.get("ISO_A3")
	if isinstance(iso, str) and len(iso) == 3 and iso.isalpha():
		return iso.upper()
	adm = properties.get("ADM0_A3")
	if isinstance(adm, str) and len(adm) == 3 and adm.isalpha():
		return adm.upper()
	return ""


def _clean_label(value: Any) -> str:
	"""Return a trimmed label, treating Natural Earth placeholders as empty."""
	if value is None:
		return ""
	text = str(value).strip()
	return "" if text in ("", "-99", "null", "None") else text


def _clean_number(value: Any) -> float | int | None:
	if value is None or isinstance(value, bool):
		return None
	if isinstance(value, int | float):
		return value if math.isfinite(float(value)) else None
	return None


@lru_cache(maxsize=1)
def _country_index() -> tuple:
	"""Precompute (properties, bbox, geometry) for every country for fast hit-testing."""
	index = []
	for feature in load_layer(COUNTRY_LAYER)["features"]:
		geometry = feature.get("geometry")
		properties = feature.get("properties") or {}
		if not geometry:
			continue
		try:
			bounds = geometry_bounds(geometry)
			load_geometry(geometry)
		except ValueError:
			continue
		index.append((properties, bounds, geometry))
	return tuple(index)


def find_country(longitude: float, latitude: float) -> dict | None:
	"""Return the country properties containing a WGS84 point (bbox pre-filtered)."""
	if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
		return None
	for properties, (west, south, east, north), geometry in _country_index():
		if not (south <= latitude <= north):
			continue
		in_lon = (west <= longitude <= east) if west <= east else (longitude >= west or longitude <= east)
		if not in_lon:
			continue
		try:
			if point_in_geometry(longitude, latitude, geometry):
				return properties
		except ValueError:
			continue
	return None


@lru_cache(maxsize=1)
def _capital_index() -> dict:
	"""Map ISO_A3 -> capital city properties from the populated-places layer."""
	capitals = {}
	try:
		features = load_layer(PLACES_LAYER)["features"]
	except NaturalEarthError:
		return capitals
	for feature in features:
		properties = feature.get("properties") or {}
		if properties.get("FEATURECLA") != "Admin-0 capital":
			continue
		code = properties.get("ADM0_A3")
		if code and code not in capitals:
			capitals[code] = properties
	return capitals


def country_profile(
	code: str | None = None, longitude: float | None = None, latitude: float | None = None
) -> dict | None:
	"""Build a normalized country profile from the bundled attributes.

	Accepts either an ISO_A3 / boundary code or a coordinate pair. The capital is
	derived from the populated-places layer; the area is a spherical estimate.
	"""
	properties = None
	if code:
		code = str(code).strip().upper()
		for candidate, _bounds, _geometry in _country_index():
			if iso_code(candidate) == code:
				properties = candidate
				break
	elif longitude is not None and latitude is not None:
		properties = find_country(float(longitude), float(latitude))
	if not properties:
		return None

	iso_a3 = iso_code(properties)
	capital = _capital_index().get(iso_a3)
	geometry = None
	for candidate, _bounds, geom in _country_index():
		if candidate is properties:
			geometry = geom
			break
	area_km2 = None
	if geometry is not None:
		try:
			area_km2 = round(geodesic_area_m2(geometry) / 1_000_000, 1)
		except ValueError:
			area_km2 = None

	return {
		"code": iso_a3,
		"iso_a2": properties.get("ISO_A2") or "",
		"name": properties.get("NAME") or properties.get("ADMIN") or "",
		"name_ar": _clean_label(properties.get("NAME_AR")),
		"name_long": properties.get("NAME_LONG") or properties.get("FORMAL_EN") or "",
		"sovereign": properties.get("SOVEREIGNT") or "",
		"type": properties.get("TYPE") or "",
		"continent": properties.get("CONTINENT") or "",
		"region": properties.get("REGION_UN") or "",
		"subregion": properties.get("SUBREGION") or "",
		"economy": properties.get("ECONOMY") or "",
		"income_group": properties.get("INCOME_GRP") or "",
		"population_estimate": _clean_number(properties.get("POP_EST")),
		"population_year": _clean_number(properties.get("POP_YEAR")),
		"gdp_million_usd": _clean_number(properties.get("GDP_MD") or properties.get("GDP_MD_EST")),
		"gdp_year": _clean_number(properties.get("GDP_YEAR")),
		"area_km2": area_km2,
		"label_longitude": _clean_number(properties.get("LABEL_X")),
		"label_latitude": _clean_number(properties.get("LABEL_Y")),
		"capital": (
			{
				"name": capital.get("NAME"),
				"name_ar": _clean_label(capital.get("NAME_AR")),
				"admin1": capital.get("ADM1NAME") or "",
				"latitude": _clean_number(capital.get("LATITUDE")),
				"longitude": _clean_number(capital.get("LONGITUDE")),
				"population_max": _clean_number(capital.get("POP_MAX")),
			}
			if capital
			else None
		),
		"provenance": "natural_earth_bundle",
	}


# ---------------------------------------------------------------------------
# Choropleth classification (pure, testable)
# ---------------------------------------------------------------------------


def classify(values: list, method: str = "quantile", classes: int = 5) -> dict:
	"""Compute choropleth class breaks for a list of numeric values.

	Returns breakpoints (upper bound of each class), the observed min/max, and the
	empty-data flag. ``quantile`` distributes features evenly across classes;
	``equal_interval`` splits the value range into equal-width bands.
	"""
	if method not in CLASSIFICATION_METHODS:
		raise NaturalEarthError(f"Unknown classification method {method!r}.")
	if isinstance(classes, bool) or not isinstance(classes, int) or not 2 <= classes <= 9:
		raise NaturalEarthError("Choropleth classes must be an integer between 2 and 9.")
	numbers = sorted(
		float(value)
		for value in values
		if isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(float(value))
	)
	if not numbers:
		return {"method": method, "classes": classes, "breaks": [], "min": None, "max": None, "empty": True}
	low, high = numbers[0], numbers[-1]
	if method == "equal_interval" or high == low:
		if high == low:
			breaks = [high]
		else:
			width = (high - low) / classes
			breaks = [low + width * (index + 1) for index in range(classes)]
	else:  # quantile
		breaks = []
		for index in range(1, classes + 1):
			position = (len(numbers) - 1) * index / classes
			lower = int(math.floor(position))
			upper = min(lower + 1, len(numbers) - 1)
			fraction = position - lower
			breaks.append(numbers[lower] + (numbers[upper] - numbers[lower]) * fraction)
	# Ensure strictly increasing, finite breaks ending at the observed maximum.
	cleaned = []
	for value in breaks:
		if not cleaned or value > cleaned[-1]:
			cleaned.append(value)
	if cleaned:
		cleaned[-1] = high
	return {
		"method": method,
		"classes": len(cleaned) or classes,
		"breaks": cleaned,
		"min": low,
		"max": high,
		"empty": False,
	}


def class_index(value: float, breaks: list) -> int:
	"""Return the zero-based choropleth class for a value given upper-bound breaks."""
	if not breaks:
		return 0
	for index, bound in enumerate(breaks):
		if value <= bound:
			return index
	return len(breaks) - 1
