"""Framework-independent tests for the bundled Natural Earth vector pack."""

from __future__ import annotations

import hashlib
import json
import unittest

from camera_archive_management.geo import natural_earth as ne
from camera_archive_management.geo.geometry import geodesic_area_m2


class TestNaturalEarthCatalog(unittest.TestCase):
	def test_catalog_is_valid_and_comprehensive(self):
		catalog = ne.catalog()
		layers = catalog["layers"]
		self.assertEqual(len(layers), 18)
		self.assertEqual(catalog["license"], "Public Domain")
		self.assertTrue(catalog["revision"])
		categories = {layer["category"] for layer in layers}
		geometries = {layer["geometry"] for layer in layers}
		scales = {layer["scale"] for layer in layers}
		self.assertEqual(categories, {"cultural", "physical"})
		self.assertEqual(geometries, {"point", "line", "polygon"})
		self.assertEqual(scales, {"10m", "50m", "110m"})

	def test_summary_counts_match_layers(self):
		summary = ne.summary()
		self.assertEqual(summary["layers"], 18)
		self.assertEqual(summary["cultural"] + summary["physical"], 18)
		self.assertEqual(summary["point"] + summary["line"] + summary["polygon"], 18)
		self.assertGreater(summary["features"], 3000)

	def test_every_layer_file_matches_its_integrity_pin(self):
		for layer in ne.catalog()["layers"]:
			with self.subTest(layer=layer["id"]):
				path = ne.DATA_DIR / layer["file"]
				self.assertTrue(path.is_file())
				raw = path.read_bytes()
				self.assertEqual(hashlib.sha256(raw).hexdigest(), layer["sha256"])
				payload = json.loads(raw.decode("utf-8"))
				self.assertEqual(payload["type"], "FeatureCollection")
				self.assertEqual(len(payload["features"]), layer["feature_count"])

	def test_load_layer_returns_feature_collection_and_rejects_unknown(self):
		payload = ne.load_layer("countries_110m")
		self.assertEqual(payload["type"], "FeatureCollection")
		self.assertEqual(len(payload["features"]), 177)
		with self.assertRaises(ne.NaturalEarthError):
			ne.load_layer("does_not_exist")

	def test_layer_geometry_families_match_their_spec(self):
		expected = {
			"point": {"Point", "MultiPoint"},
			"line": {"LineString", "MultiLineString"},
			"polygon": {"Polygon", "MultiPolygon"},
		}
		for layer in ne.catalog()["layers"]:
			with self.subTest(layer=layer["id"]):
				payload = ne.load_layer(layer["id"])
				types = {
					feature["geometry"]["type"] for feature in payload["features"] if feature.get("geometry")
				}
				self.assertTrue(types <= expected[layer["geometry"]], f"{layer['id']}: {types}")


class TestCountryIntelligence(unittest.TestCase):
	def test_find_country_by_coordinate(self):
		netherlands = ne.find_country(4.90, 52.37)  # Amsterdam
		self.assertIsNotNone(netherlands)
		self.assertEqual(ne.iso_code(netherlands), "NLD")
		france = ne.find_country(2.35, 48.85)  # Paris
		self.assertEqual(ne.iso_code(france), "FRA")

	def testiso_code_falls_back_for_ne_minus_99(self):
		# Natural Earth stores France's ISO_A3 as '-99'; ADM0_A3 carries the real code.
		france = ne.find_country(2.35, 48.85)
		self.assertEqual(france.get("ISO_A3"), "-99")
		self.assertEqual(ne.iso_code(france), "FRA")

	def test_find_country_returns_none_over_open_ocean(self):
		self.assertIsNone(ne.find_country(-30.0, -30.0))  # South Atlantic
		self.assertIsNone(ne.find_country(0.0, 0.0))  # Gulf of Guinea

	def test_country_profile_by_code(self):
		profile = ne.country_profile("NLD")
		self.assertIsNotNone(profile)
		self.assertEqual(profile["name"], "Netherlands")
		self.assertEqual(profile["continent"], "Europe")
		self.assertEqual(profile["iso_a2"], "NL")
		self.assertGreater(profile["population_estimate"], 1_000_000)
		self.assertGreater(profile["gdp_million_usd"], 0)
		self.assertGreater(profile["area_km2"], 10_000)
		self.assertIsNotNone(profile["capital"])
		self.assertEqual(profile["capital"]["name"], "Amsterdam")
		self.assertEqual(profile["name_ar"], "هولندا")
		self.assertEqual(profile["capital"]["name_ar"], "أمستردام")
		self.assertEqual(profile["provenance"], "natural_earth_bundle")

	def test_country_profile_by_coordinate_matches_code(self):
		by_point = ne.country_profile(longitude=2.35, latitude=48.85)
		by_code = ne.country_profile("FRA")
		self.assertEqual(by_point["code"], by_code["code"])
		self.assertEqual(by_point["name"], "France")

	def test_country_profile_unknown_returns_none(self):
		self.assertIsNone(ne.country_profile("ZZZ"))
		self.assertIsNone(ne.country_profile(longitude=-30.0, latitude=-30.0))


class TestChoroplethClassification(unittest.TestCase):
	def test_quantile_breaks_are_increasing_and_end_at_max(self):
		result = ne.classify([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], method="quantile", classes=5)
		self.assertFalse(result["empty"])
		self.assertEqual(result["min"], 1)
		self.assertEqual(result["max"], 10)
		self.assertEqual(result["breaks"], sorted(result["breaks"]))
		self.assertEqual(result["breaks"][-1], 10)
		self.assertTrue(all(a < b for a, b in zip(result["breaks"], result["breaks"][1:], strict=False)))

	def test_equal_interval_splits_range_evenly(self):
		result = ne.classify([0, 100], method="equal_interval", classes=4)
		self.assertEqual(result["breaks"], [25, 50, 75, 100])

	def test_empty_and_single_value(self):
		empty = ne.classify([])
		self.assertTrue(empty["empty"])
		self.assertEqual(empty["breaks"], [])
		single = ne.classify([7, 7, 7])
		self.assertEqual(single["breaks"], [7])
		self.assertEqual(ne.class_index(7, single["breaks"]), 0)

	def test_class_index_assignment(self):
		breaks = [25, 50, 75, 100]
		self.assertEqual(ne.class_index(10, breaks), 0)
		self.assertEqual(ne.class_index(25, breaks), 0)
		self.assertEqual(ne.class_index(26, breaks), 1)
		self.assertEqual(ne.class_index(100, breaks), 3)
		self.assertEqual(ne.class_index(999, breaks), 3)

	def test_invalid_method_and_classes_raise(self):
		with self.assertRaises(ne.NaturalEarthError):
			ne.classify([1, 2], method="bogus")
		with self.assertRaises(ne.NaturalEarthError):
			ne.classify([1, 2], classes=1)
		with self.assertRaises(ne.NaturalEarthError):
			ne.classify([1, 2], classes=20)


class TestGeodesicArea(unittest.TestCase):
	def test_one_degree_square_near_equator(self):
		square = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
		area = geodesic_area_m2(square)
		expected = 1.236e10  # ~111.2 km x 111.2 km
		self.assertLess(abs(area - expected) / expected, 0.02)

	def test_hole_subtracts_area(self):
		outer = [[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]
		hole = [[0.5, 0.5], [1.5, 0.5], [1.5, 1.5], [0.5, 1.5], [0.5, 0.5]]
		solid = geodesic_area_m2({"type": "Polygon", "coordinates": [outer]})
		with_hole = geodesic_area_m2({"type": "Polygon", "coordinates": [outer, hole]})
		self.assertLess(with_hole, solid)
		self.assertGreater(with_hole, solid * 0.5)

	def test_multipolygon_sums_parts(self):
		part_a = [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]
		part_b = [[[10, 10], [11, 10], [11, 11], [10, 11], [10, 10]]]
		multi = geodesic_area_m2({"type": "MultiPolygon", "coordinates": [part_a, part_b]})
		single = geodesic_area_m2({"type": "Polygon", "coordinates": part_a})
		self.assertGreater(multi, single * 1.9)


if __name__ == "__main__":
	unittest.main()
