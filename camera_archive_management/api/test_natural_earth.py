"""Site tests for the bundled Natural Earth API endpoints."""

from __future__ import annotations

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from camera_archive_management.api import natural_earth as ne_api


class TestNaturalEarthEndpoints(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.original_user = frappe.session.user
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, self.original_user)

	def test_catalog_requires_camera_read_permission(self):
		frappe.set_user("ne-reader-without-access@example.invalid")
		with patch.object(frappe, "has_permission", return_value=False) as has_permission:
			with self.assertRaises(frappe.PermissionError):
				ne_api.get_catalog()
		has_permission.assert_called_once_with("Camera", "read")

	def test_catalog_returns_layers_provenance_and_summary(self):
		with patch.object(frappe, "has_permission", return_value=True):
			result = ne_api.get_catalog()
		self.assertEqual(len(result["layers"]), 18)
		self.assertEqual(result["license"], "Public Domain")
		self.assertTrue(result["attribution"])
		self.assertTrue(result["limitations"])
		self.assertEqual(result["summary"]["layers"], 18)
		self.assertEqual(result["summary"]["cultural"] + result["summary"]["physical"], 18)

	def test_get_layer_returns_checked_geojson_with_style(self):
		with patch.object(frappe, "has_permission", return_value=True):
			result = ne_api.get_layer("countries_110m")
		self.assertEqual(result["geojson"]["type"], "FeatureCollection")
		self.assertEqual(len(result["geojson"]["features"]), 177)
		self.assertEqual(result["layer"]["geometry"], "polygon")
		self.assertIn("color", result["layer"]["style"])
		self.assertTrue(result["attribution"])

	def test_get_layer_rejects_unknown_and_malformed_ids(self):
		with patch.object(frappe, "has_permission", return_value=True):
			with self.assertRaises(frappe.ValidationError):
				ne_api.get_layer("not_a_layer")
			with self.assertRaises(frappe.ValidationError):
				ne_api.get_layer("x" * 100)
			with self.assertRaises(frappe.ValidationError):
				ne_api.get_layer(123)

	def test_country_profile_by_code_and_by_coordinate(self):
		with patch.object(frappe, "has_permission", return_value=True):
			by_code = ne_api.get_country_profile(code="NLD")
			by_point = ne_api.get_country_profile(latitude="52.37", longitude="4.90")
		self.assertEqual(by_code["profile"]["name"], "Netherlands")
		self.assertEqual(by_code["profile"]["capital"]["name"], "Amsterdam")
		self.assertEqual(by_point["profile"]["code"], "NLD")

	def test_country_profile_validates_input(self):
		with patch.object(frappe, "has_permission", return_value=True):
			with self.assertRaises(frappe.ValidationError):
				ne_api.get_country_profile()
			with self.assertRaises(frappe.ValidationError):
				ne_api.get_country_profile(code="x" * 20)
			with self.assertRaises(frappe.ValidationError):
				ne_api.get_country_profile(latitude="999", longitude="4.9")
			missing = ne_api.get_country_profile(code="ZZZ")
		self.assertIsNone(missing["profile"])

	def test_choropleth_cameras_joins_permission_filtered_rows(self):
		rows = [
			frappe._dict(name="CAM-A", latitude="52.37", longitude="4.90"),
			frappe._dict(name="CAM-B", latitude="48.85", longitude="2.35"),
			frappe._dict(name="CAM-C", latitude="-30.0", longitude="-30.0"),
			frappe._dict(name="CAM-D", latitude=None, longitude=None),
		]
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_list", return_value=rows) as get_list,
		):
			result = ne_api.get_country_choropleth(metric="cameras")
		get_list.assert_called_once()
		self.assertEqual(get_list.call_args.args[0], "Camera")
		self.assertEqual(result["values"], {"NLD": 1, "FRA": 1})
		self.assertEqual(result["meta"]["located_cameras"], 3)
		self.assertFalse(result["classification"]["empty"])

	def test_choropleth_movements_requires_motion_event_permission(self):
		rows = [frappe._dict(name="CAM-A", latitude="52.37", longitude="4.90")]

		def only_camera(doctype, *args, **kwargs):
			return doctype == "Camera"

		with (
			patch.object(frappe, "has_permission", side_effect=only_camera),
			patch.object(frappe, "get_list", return_value=rows),
		):
			with self.assertRaises(frappe.PermissionError):
				ne_api.get_country_choropleth(metric="movements")

	def test_choropleth_movements_sums_events_through_cameras(self):
		camera_rows = [frappe._dict(name="CAM-A", latitude="52.37", longitude="4.90")]
		event_rows = [frappe._dict(camera="CAM-A", total=7), frappe._dict(camera="CAM-UNKNOWN", total=3)]
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_list", side_effect=[camera_rows, event_rows]),
		):
			result = ne_api.get_country_choropleth(metric="movements")
		self.assertEqual(result["values"], {"NLD": 7})

	def test_choropleth_population_uses_bundle_estimates(self):
		with patch.object(frappe, "has_permission", return_value=True):
			result = ne_api.get_country_choropleth(metric="population", method="quantile", classes=5)
		self.assertGreater(result["values"]["NLD"], 1_000_000)
		self.assertEqual(result["meta"]["provenance"], "natural_earth_bundle")
		self.assertTrue(result["classification"]["breaks"])

	def test_choropleth_custom_values_join(self):
		payload = json.dumps({"NLD": 42, "fra": 17.5})
		with patch.object(frappe, "has_permission", return_value=True):
			result = ne_api.get_country_choropleth(
				metric="custom", values=payload, method="equal_interval", classes=3
			)
		self.assertEqual(result["values"], {"NLD": 42.0, "FRA": 17.5})
		self.assertEqual(result["meta"]["provenance"], "external_join")

	def test_choropleth_custom_values_reject_invalid_payloads(self):
		with patch.object(frappe, "has_permission", return_value=True):
			with self.assertRaises(frappe.ValidationError):
				ne_api.get_country_choropleth(metric="custom", values='{"NLD": "many"}')
			with self.assertRaises(frappe.ValidationError):
				ne_api.get_country_choropleth(metric="custom", values="[1,2]")
			with self.assertRaises(frappe.ValidationError):
				ne_api.get_country_choropleth(
					metric="custom", values=json.dumps({f"C{i}": i for i in range(301)})
				)
			with self.assertRaises(frappe.ValidationError):
				ne_api.get_country_choropleth(metric="custom", values="not json")

	def test_choropleth_rejects_unknown_metric_and_bad_classes(self):
		with patch.object(frappe, "has_permission", return_value=True):
			with self.assertRaises(frappe.ValidationError):
				ne_api.get_country_choropleth(metric="traffic")
			with self.assertRaises(frappe.ValidationError):
				ne_api.get_country_choropleth(metric="population", classes="many")
			with self.assertRaises(frappe.ValidationError):
				ne_api.get_country_choropleth(metric="population", classes=99)
