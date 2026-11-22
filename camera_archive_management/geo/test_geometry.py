from __future__ import annotations

import unittest
from decimal import Decimal

from camera_archive_management.geo.coordinates import parse_coordinate, point_from_geojson, validate_pair
from camera_archive_management.geo.geometry import (
	bearing_degrees,
	compass_8,
	dumps_geojson,
	geometry_bounds,
	haversine_m,
	point_in_geometry,
)


class TestCoordinates(unittest.TestCase):
	def test_wgs84_limits_and_blank_pair(self):
		self.assertEqual(validate_pair("90", "180"), (90, 180))
		self.assertEqual(validate_pair("", None), (None, None))
		for latitude, longitude in ((90.01, 0), (0, -180.01), (True, 0), ("1e2", 0), (10, None)):
			with self.subTest(latitude=latitude, longitude=longitude), self.assertRaises(ValueError):
				validate_pair(latitude, longitude)

	def test_decimal_separator_and_geojson_point(self):
		self.assertEqual(parse_coordinate("٥٢٫٣٧", 90), Decimal("52.37"))  # noqa: RUF001
		self.assertEqual(
			point_from_geojson('{"type":"Point","coordinates":[4.9,52.3]}'),
			(Decimal("52.3"), Decimal("4.9")),
		)


class TestGeometry(unittest.TestCase):
	def setUp(self):
		self.polygon = {
			"type": "Polygon",
			"coordinates": [
				[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
				[[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]],
			],
		}

	def test_bounds_and_polygon_hole(self):
		self.assertEqual(geometry_bounds(self.polygon), (0, 0, 10, 10))
		self.assertTrue(point_in_geometry(2, 2, self.polygon))
		self.assertFalse(point_in_geometry(5, 5, self.polygon))
		self.assertTrue(point_in_geometry(0, 3, self.polygon))

	def test_multipolygon_distance_and_bearing(self):
		geometry = {
			"type": "MultiPolygon",
			"coordinates": [
				self.polygon["coordinates"][:1],
				[[[20, 20], [21, 20], [21, 21], [20, 21], [20, 20]]],
			],
		}
		self.assertTrue(point_in_geometry(20.5, 20.5, geometry))
		self.assertGreater(haversine_m(52.0, 4.0, 52.0, 4.01), 600)
		self.assertEqual(compass_8(bearing_degrees(0, 0, 1, 0)), "N")

	def test_rejects_out_of_range_geometry(self):
		with self.assertRaises(ValueError):
			geometry_bounds({"type": "Polygon", "coordinates": [[[181, 0], [181, 1], [180, 1], [181, 0]]]})

	def test_geojson_decimal_precision_is_not_rounded(self):
		raw = (
			'{"type":"Polygon","coordinates":[[['
			'4.90000000000000000000000000000000000001,52.30000000000000000000000000000000000002],'
			'[4.91,52.30],[4.92,52.31],'
			'[4.90000000000000000000000000000000000001,52.30000000000000000000000000000000000002]]]}'
		)
		saved = dumps_geojson(raw)
		self.assertIn("4.90000000000000000000000000000000000001", saved)
		self.assertIn("52.30000000000000000000000000000000000002", saved)


if __name__ == "__main__":
	unittest.main()
