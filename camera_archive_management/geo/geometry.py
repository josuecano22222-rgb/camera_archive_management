"""GeoJSON geometry bounds, point-in-polygon, and geodesic distance helpers."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

EARTH_RADIUS_M = 6_371_008.8


def _positions(value: Any) -> Iterable[tuple[int | float | Decimal, int | float | Decimal]]:
	if (
		isinstance(value, list)
		and len(value) >= 2
		and all(isinstance(v, int | float | Decimal) and not isinstance(v, bool) for v in value[:2])
	):
		yield value[0], value[1]
	elif isinstance(value, list):
		for child in value:
			yield from _positions(child)


def load_geometry(value: Any) -> dict:
	try:
		geometry = json.loads(value, parse_float=Decimal) if isinstance(value, str) else value
	except (TypeError, json.JSONDecodeError) as exc:
		raise ValueError("Geometry is not valid GeoJSON") from exc
	if not isinstance(geometry, dict) or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
		raise ValueError("Only GeoJSON Polygon and MultiPolygon boundaries are supported")
	coordinates = geometry.get("coordinates")
	polygons = [coordinates] if geometry["type"] == "Polygon" else coordinates
	if not isinstance(polygons, list) or not polygons:
		raise ValueError("Polygon geometry contains no coordinate rings")
	for polygon in polygons:
		if not isinstance(polygon, list) or not polygon:
			raise ValueError("Each polygon must contain at least one ring")
		for ring in polygon:
			if not isinstance(ring, list) or len(ring) < 4:
				raise ValueError("Each polygon ring must contain at least four positions")
			if any(
				not isinstance(position, list)
				or len(position) < 2
				or any(
					not isinstance(value, int | float | Decimal) or isinstance(value, bool) for value in position[:2]
				)
				for position in ring
			):
				raise ValueError("Polygon ring positions must contain numeric longitude and latitude")
			if ring[0][:2] != ring[-1][:2]:
				raise ValueError("Polygon rings must be closed")
	positions = list(_positions(coordinates))
	if not positions:
		raise ValueError("Polygon geometry contains no coordinate positions")
	if any(
		not math.isfinite(float(lon))
		or not math.isfinite(float(lat))
		or not (-180 <= lon <= 180 and -90 <= lat <= 90)
		for lon, lat in positions
	):
		raise ValueError("Boundary coordinates are outside WGS84 ranges")
	return geometry


def geometry_bounds(value: Any) -> tuple[int | float | Decimal, int | float | Decimal, int | float | Decimal, int | float | Decimal]:
	geometry = load_geometry(value)
	positions = list(_positions(geometry["coordinates"]))
	longitudes = [p[0] for p in positions]
	latitudes = [p[1] for p in positions]
	if any(not (-180 <= lon <= 180 and -90 <= lat <= 90) for lon, lat in positions):
		raise ValueError("Boundary coordinates are outside WGS84 ranges")
	return min(longitudes), min(latitudes), max(longitudes), max(latitudes)


def dumps_geojson(value: Any) -> str:
	"""Serialize validated geometry without converting Decimal coordinates to floats."""
	geometry = load_geometry(value)

	def encode(item: Any) -> str:
		if isinstance(item, Decimal):
			return format(item, "f")
		if isinstance(item, bool) or item is None or isinstance(item, int):
			return json.dumps(item, ensure_ascii=False, allow_nan=False)
		if isinstance(item, float):
			if not math.isfinite(item):
				raise ValueError("GeoJSON numbers must be finite")
			return json.dumps(item, allow_nan=False)
		if isinstance(item, str):
			return json.dumps(item, ensure_ascii=False)
		if isinstance(item, list):
			return "[" + ",".join(encode(child) for child in item) + "]"
		if isinstance(item, dict):
			if not all(isinstance(key, str) for key in item):
				raise ValueError("GeoJSON object keys must be strings")
			pairs = (json.dumps(key, ensure_ascii=False) + ":" + encode(item[key]) for key in sorted(item))
			return "{" + ",".join(pairs) + "}"
		raise ValueError("Unsupported GeoJSON value")

	return encode(geometry)


def _on_segment(x: float, y: float, a: list, b: list, epsilon: float = 1e-10) -> bool:
	ax, ay = float(a[0]), float(a[1])
	bx, by = float(b[0]), float(b[1])
	cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax)
	if abs(cross) > epsilon:
		return False
	return (
		min(ax, bx) - epsilon <= x <= max(ax, bx) + epsilon
		and min(ay, by) - epsilon <= y <= max(ay, by) + epsilon
	)


def _ring_contains(lon: float, lat: float, ring: list) -> bool:
	inside = False
	if len(ring) < 4:
		return False
	previous = ring[-1]
	for current in ring:
		if _on_segment(lon, lat, previous, current):
			return True
		x1, y1 = float(previous[0]), float(previous[1])
		x2, y2 = float(current[0]), float(current[1])
		if (y1 > lat) != (y2 > lat):
			crossing_lon = (x2 - x1) * (lat - y1) / (y2 - y1) + x1
			if lon < crossing_lon:
				inside = not inside
		previous = current
	return inside


def _polygon_contains(lon: float, lat: float, rings: list) -> bool:
	if not rings or not _ring_contains(lon, lat, rings[0]):
		return False
	return not any(_ring_contains(lon, lat, hole) for hole in rings[1:])


def point_in_geometry(lon: float, lat: float, value: Any) -> bool:
	"""Containment with boundary points considered inside; Shapely is optional."""
	geometry = load_geometry(value)
	try:
		from shapely.geometry import Point, shape

		def floats(value):
			if isinstance(value, dict):
				return {key: floats(child) for key, child in value.items()}
			if isinstance(value, list):
				return [floats(child) for child in value]
			if isinstance(value, int | float | Decimal) and not isinstance(value, bool):
				return float(value)
			return value

		return shape(floats(geometry)).covers(Point(lon, lat))
	except ImportError:
		pass
	if geometry["type"] == "Polygon":
		return _polygon_contains(lon, lat, geometry["coordinates"])
	return any(_polygon_contains(lon, lat, polygon) for polygon in geometry["coordinates"])


def _ring_area_m2(ring: list) -> float:
	"""Approximate spherical area of one closed ring (square meters).

	Uses the standard spherical-excess summation; accurate enough for
	country-scale display, not for cadastral or engineering measurement.
	"""
	if not isinstance(ring, list) or len(ring) < 4:
		return 0.0
	total = 0.0
	for index in range(len(ring) - 1):
		lon1, lat1 = math.radians(float(ring[index][0])), math.radians(float(ring[index][1]))
		lon2, lat2 = math.radians(float(ring[index + 1][0])), math.radians(float(ring[index + 1][1]))
		total += (lon2 - lon1) * (2 + math.sin(lat1) + math.sin(lat2))
	return abs(total) * EARTH_RADIUS_M * EARTH_RADIUS_M / 2.0


def geodesic_area_m2(value: Any) -> float:
	"""Approximate geodesic area of a Polygon/MultiPolygon in square meters.

	Outer rings add area and holes subtract it. This is a cartographic estimate
	on a sphere, suitable for comparing country sizes, not a legal survey area.
	"""
	geometry = load_geometry(value)
	polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
	total = 0.0
	for polygon in polygons:
		if not isinstance(polygon, list) or not polygon:
			continue
		total += _ring_area_m2(polygon[0])
		for hole in polygon[1:]:
			total -= _ring_area_m2(hole)
	return max(0.0, total)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
	p1, p2 = math.radians(lat1), math.radians(lat2)
	dp = math.radians(lat2 - lat1)
	dl = math.radians(lon2 - lon1)
	a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
	return 2 * EARTH_RADIUS_M * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))


def bearing_degrees(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
	p1, p2 = math.radians(lat1), math.radians(lat2)
	delta_lon = math.radians(lon2 - lon1)
	y = math.sin(delta_lon) * math.cos(p2)
	x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(delta_lon)
	return (math.degrees(math.atan2(y, x)) + 360) % 360


def compass_8(degrees: float) -> str:
	return ("N", "NE", "E", "SE", "S", "SW", "W", "NW")[int((degrees + 22.5) // 45) % 8]
