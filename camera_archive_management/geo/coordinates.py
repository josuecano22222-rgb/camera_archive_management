"""Strict WGS84 decimal-degree parsing shared by controllers and APIs."""

from __future__ import annotations

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


def point_from_geojson(value: Any) -> tuple[Decimal, Decimal] | None:
	"""Extract the anchor from a GeoJSON Point or Feature<Point>."""
	if not value:
		return None
	import json

	try:
		payload = json.loads(value, parse_float=Decimal) if isinstance(value, str) else value
	except (TypeError, json.JSONDecodeError) as exc:
		raise ValueError("Location must contain valid GeoJSON") from exc
	if not isinstance(payload, dict):
		raise ValueError("Location must be a GeoJSON object")
	if payload.get("type") == "Feature":
		payload = payload.get("geometry")
	if not isinstance(payload, dict) or payload.get("type") != "Point":
		raise ValueError("Camera location must be a GeoJSON Point")
	coordinates = payload.get("coordinates")
	if not isinstance(coordinates, list) or len(coordinates) < 2:
		raise ValueError("GeoJSON Point requires [longitude, latitude]")
	lon = parse_coordinate(coordinates[0], 180)
	lat = parse_coordinate(coordinates[1], 90)
	if lat is None or lon is None:
		raise ValueError("GeoJSON Point coordinates cannot be blank")
	return lat, lon
