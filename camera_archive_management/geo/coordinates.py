"""Strict WGS84 decimal-degree parsing shared by controllers and APIs."""

from __future__ import annotations

import json
import math
import re
from decimal import Decimal, InvalidOperation
from typing import Any

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫", "01234567890123456789.")  # noqa: RUF001
_DECIMAL = re.compile(r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$")


def parse_coordinate(value: Any, limit: Decimal | int) -> Decimal | None:
	"""Return a finite bounded Decimal, rejecting booleans and malformed text."""
	if value is None or (isinstance(value, str) and not value.strip()):
		return None
	if isinstance(value, str) and (len(value) > 140 or value != value.strip()):
		raise ValueError("Coordinate must be at most 140 characters with no surrounding whitespace")
	if isinstance(value, bool) or not isinstance(value, str | int | float | Decimal):
		raise ValueError("Coordinate must be a decimal number")
	if isinstance(value, float) and not math.isfinite(value):
		raise ValueError("Coordinate must be finite")
	text = str(value).strip().translate(_DIGITS)
	if isinstance(value, str) and not _DECIMAL.fullmatch(text):
		raise ValueError("Coordinate must use decimal-degree notation")
	try:
		number = Decimal(text)
	except (InvalidOperation, ValueError) as exc:
		raise ValueError("Coordinate is not a valid decimal number") from exc
	if not number.is_finite() or number.copy_abs() > Decimal(str(limit)):
		raise ValueError(f"Coordinate must be within {-limit} and {limit}")
	return number


def validate_pair(latitude: Any, longitude: Any) -> tuple[Decimal | None, Decimal | None]:
	lat = parse_coordinate(latitude, 90)
	lon = parse_coordinate(longitude, 180)
	if (lat is None) != (lon is None):
		raise ValueError("Latitude and longitude must both be supplied or both be blank")
	return lat, lon


def _encode_json_exact(value: Any) -> str:
	"""Serialize nested JSON values without converting Decimal coordinates to floats."""
	if isinstance(value, Decimal):
		return format(value, "f")
	if isinstance(value, bool) or value is None or isinstance(value, int):
		return json.dumps(value, ensure_ascii=False, allow_nan=False)
	if isinstance(value, float):
		if not math.isfinite(value):
			raise ValueError("GeoJSON numbers must be finite")
		return json.dumps(value, allow_nan=False)
	if isinstance(value, str):
		return json.dumps(value, ensure_ascii=False)
	if isinstance(value, list):
		return "[" + ",".join(_encode_json_exact(item) for item in value) + "]"
	if isinstance(value, dict):
		if not all(isinstance(key, str) for key in value):
			raise ValueError("GeoJSON object keys must be strings")
		return "{" + ",".join(
			json.dumps(key, ensure_ascii=False) + ":" + _encode_json_exact(item)
			for key, item in value.items()
		) + "}"
	raise ValueError("Unsupported GeoJSON value")


def point_feature_collection(latitude: Any, longitude: Any) -> str:
	"""Serialize a precise point in the FeatureCollection shape Frappe's Geolocation control expects."""
	lat, lon = validate_pair(latitude, longitude)
	if lat is None or lon is None:
		raise ValueError("A point FeatureCollection requires latitude and longitude")
	return _encode_json_exact({
		"type": "FeatureCollection",
		"features": [{
			"type": "Feature",
			"properties": {"point_type": "marker"},
			"geometry": {"type": "Point", "coordinates": [lon, lat]},
		}],
	})


def normalize_frappe_geolocation(value: Any) -> str:
	"""Return a GeoJSON FeatureCollection with safe feature properties for Frappe's map control."""
	if isinstance(value, str):
		try:
			payload = json.loads(value, parse_float=Decimal)
		except (TypeError, json.JSONDecodeError) as exc:
			raise ValueError("Location must contain valid GeoJSON") from exc
	else:
		payload = value
	if not isinstance(payload, dict):
		raise ValueError("Location must be a GeoJSON object")
	kind = payload.get("type")
	if kind == "Point":
		features = [{
			"type": "Feature",
			"properties": {"point_type": "marker"},
			"geometry": payload,
		}]
	elif kind == "Feature":
		features = [payload]
	elif kind == "FeatureCollection":
		features = payload.get("features")
		if not isinstance(features, list):
			raise ValueError("GeoJSON FeatureCollection requires a features array")
	else:
		raise ValueError("Location must be a GeoJSON Point or FeatureCollection")

	for feature in features:
		if not isinstance(feature, dict) or feature.get("type") != "Feature":
			raise ValueError("GeoJSON FeatureCollection entries must be Features")
		geometry = feature.get("geometry")
		if not isinstance(geometry, dict):
			raise ValueError("GeoJSON Features must contain a geometry")
		properties = feature.get("properties")
		if not isinstance(properties, dict):
			properties = {}
			feature["properties"] = properties
		if geometry.get("type") == "Point":
			properties.setdefault("point_type", "marker")

	return _encode_json_exact({"type": "FeatureCollection", "features": features})


def point_from_geojson(value: Any) -> tuple[Decimal, Decimal] | None:
	"""Extract the first Point anchor from a GeoJSON Point, Feature, or FeatureCollection."""
	if not value:
		return None
	try:
		payload = json.loads(value, parse_float=Decimal) if isinstance(value, str) else value
	except (TypeError, json.JSONDecodeError) as exc:
		raise ValueError("Location must contain valid GeoJSON") from exc
	if not isinstance(payload, dict):
		raise ValueError("Location must be a GeoJSON object")
	if payload.get("type") == "FeatureCollection":
		features = payload.get("features")
		if not isinstance(features, list):
			raise ValueError("GeoJSON FeatureCollection requires a features array")
		point_feature = next(
			(
				feature for feature in features
				if isinstance(feature, dict)
				and isinstance(feature.get("geometry"), dict)
				and feature["geometry"].get("type") == "Point"
			),
			None,
		)
		if point_feature is None:
			raise ValueError("GeoJSON FeatureCollection contains no Point location")
		payload = point_feature
	if payload.get("type") == "Feature":
		payload = payload.get("geometry")
	if not isinstance(payload, dict) or payload.get("type") != "Point":
		raise ValueError("Camera location must contain a GeoJSON Point")
	coordinates = payload.get("coordinates")
	if not isinstance(coordinates, list) or len(coordinates) < 2:
		raise ValueError("GeoJSON Point requires [longitude, latitude]")
	lon = parse_coordinate(coordinates[0], 180)
	lat = parse_coordinate(coordinates[1], 90)
	if lat is None or lon is None:
		raise ValueError("GeoJSON Point coordinates cannot be blank")
	return lat, lon
