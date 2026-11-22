from __future__ import annotations

import json
import unittest
from pathlib import Path

DOCTYPE_DIR = Path(__file__).parent / "doctype"


class TestDocTypeInterfaceMetadata(unittest.TestCase):
	def load_doctype(self, folder: str) -> dict:
		path = DOCTYPE_DIR / folder / f"{folder}.json"
		return json.loads(path.read_text(encoding="utf-8"))

	def test_all_doctype_field_orders_match_definitions(self):
		definitions = sorted(DOCTYPE_DIR.glob("*/*.json"))
		self.assertEqual(len(definitions), 19)

		for path in definitions:
			with self.subTest(doctype=path.parent.name):
				definition = json.loads(path.read_text(encoding="utf-8"))
				field_names = [field["fieldname"] for field in definition["fields"]]
				self.assertEqual(len(field_names), len(set(field_names)))
				self.assertEqual(len(definition["field_order"]), len(set(definition["field_order"])))
				self.assertEqual(set(definition["field_order"]), set(field_names))

	def test_nested_table_targets_exist(self):
		for path in sorted(DOCTYPE_DIR.glob("*/*.json")):
			definition = json.loads(path.read_text(encoding="utf-8"))
			for field in definition["fields"]:
				if field["fieldtype"] == "Table":
					child_folder = field["options"].lower().replace(" ", "_")
					self.assertTrue((DOCTYPE_DIR / child_folder / f"{child_folder}.json").is_file())

	def test_views_are_enabled_only_where_schema_supports_them(self):
		camera = self.load_doctype("camera")
		self.assertTrue(any(f["fieldname"] == "location" and f["fieldtype"] == "Geolocation" for f in camera["fields"]))

		for folder in ("camera_area", "geo_admin_area"):
			self.assertEqual(self.load_doctype(folder)["is_tree"], 1)

		vehicle = self.load_doctype("cam_vehicle")
		self.assertEqual(vehicle["image_field"], "vehicle_list_image")
		vehicle_type = self.load_doctype("vehicle_type")
		self.assertEqual(vehicle_type["image_field"], "vehicle_type_image")

		for folder in ("geo_admin_area", "geo_gazetteer_place"):
			fields = {field["fieldname"] for field in self.load_doctype(folder)["fields"]}
			self.assertTrue({"latitude", "longitude"} <= fields)

		asset_dir = DOCTYPE_DIR / "archive_asset"
		calendar_script = (asset_dir / "archive_asset_calendar.js").read_text(encoding="utf-8")
		list_script = (asset_dir / "archive_asset_list.js").read_text(encoding="utf-8")
		self.assertIn('start: "recorded_from"', calendar_script)
		self.assertIn('end: "recorded_to"', calendar_script)
		self.assertIn('"recorded_from", "recorded_to"', list_script)

		boundary = self.load_doctype("geo_boundary")
		boundary_fields = {field["fieldname"] for field in boundary["fields"]}
		self.assertNotIn("latitude", boundary_fields)
		self.assertNotIn("longitude", boundary_fields)
		for folder in ("geo_boundary", "motion_event"):
			list_script = (DOCTYPE_DIR / folder / f"{folder}_list.js").read_text(encoding="utf-8")
			self.assertIn("get_custom_map_coords", list_script)


if __name__ == "__main__":
	unittest.main()
