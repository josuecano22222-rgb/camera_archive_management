from __future__ import annotations

import json
import unittest
from pathlib import Path

from camera_archive_management.geo.geometry import point_in_geometry

DOCTYPE_DIR = Path(__file__).parent / "doctype"


class TestDocTypeInterfaceMetadata(unittest.TestCase):
	def load_doctype(self, folder: str) -> dict:
		path = DOCTYPE_DIR / folder / f"{folder}.json"
		return json.loads(path.read_text(encoding="utf-8"))

	def test_all_doctype_field_orders_match_definitions(self):
		definitions = sorted(DOCTYPE_DIR.glob("*/*.json"))
		self.assertEqual(len(definitions), 18)

		for path in definitions:
			with self.subTest(doctype=path.parent.name):
				definition = json.loads(path.read_text(encoding="utf-8"))
				field_names = [field["fieldname"] for field in definition["fields"]]
				self.assertEqual(len(field_names), len(set(field_names)))
				self.assertEqual(len(definition["field_order"]), len(set(definition["field_order"])))
				self.assertEqual(set(definition["field_order"]), set(field_names))

	def test_core_reference_catalog_is_separate_from_opt_in_demo_scenario(self):
		catalog_path = Path(__file__).parents[1] / "data" / "core_reference_data.json"
		catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
		self.assertGreaterEqual(len(catalog["camera_types"]), 5)
		self.assertGreaterEqual(len(catalog["vehicle_types"]), 6)
		for rows in catalog.values():
			self.assertEqual(len({row["type_name"] for row in rows}), len(rows))
		demo_source = (Path(__file__).parents[1] / "setup" / "demo_data.py").read_text(encoding="utf-8")
		self.assertIn("SYNTHETIC DEMO DATA", demo_source)
		self.assertIn('frappe.conf.get("camera_archive_allow_demo_data") is not True', demo_source)
		self.assertIn("save_file(", demo_source)
		assets = Path(__file__).parents[1] / "data" / "demo_camera_images"
		images = sorted(assets.glob("camera_*.png"))
		self.assertEqual(len(images), 12)
		for image in images:
			with self.subTest(image=image.name):
				self.assertTrue(image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
				self.assertLess(image.stat().st_size, 100_000)
		vehicle_assets = Path(__file__).parents[1] / "data" / "demo_vehicle_images"
		vehicle_images = sorted(vehicle_assets.glob("*.png"))
		self.assertEqual(len(vehicle_images), 4)
		for image in vehicle_images:
			self.assertTrue(image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
		self.assertNotIn("demo_data", (Path(__file__).parents[1] / "hooks.py").read_text(encoding="utf-8"))

	def test_global_country_core_dataset_is_pinned_and_contains_jordan(self):
		data_dir = Path(__file__).parents[1] / "data"
		world = json.loads((data_dir / "natural_earth_admin0_countries.geojson").read_text(encoding="utf-8"))
		self.assertEqual(world["type"], "FeatureCollection")
		self.assertGreater(len(world["features"]), 150)
		jordan = [feature for feature in world["features"] if feature["properties"]["boundary_code"] == "JOR"]
		self.assertEqual(len(jordan), 1)
		self.assertEqual(jordan[0]["properties"]["label"], "Jordan")
		self.assertTrue(point_in_geometry(35.93, 31.95, jordan[0]["geometry"]))  # Amman, Jordan
		self.assertFalse(point_in_geometry(32.0, 32.0, jordan[0]["geometry"]))
		data_readme = (data_dir / "README.md").read_text(encoding="utf-8")
		self.assertIn("public domain", data_readme.lower())
		self.assertIn("not cadastral", data_readme.lower())
		self.assertIn("not legal boundaries or sovereignty", (Path(__file__).parents[1] / "setup" / "seed.py").read_text(encoding="utf-8").lower())

	def test_import_permissions_match_doctype_importability(self):
		definitions = sorted(DOCTYPE_DIR.glob("*/*.json"))
		for path in definitions:
			with self.subTest(doctype=path.parent.name):
				definition = json.loads(path.read_text(encoding="utf-8"))
				import_permissions = [perm for perm in definition.get("permissions", []) if perm.get("import")]
				if import_permissions:
					self.assertTrue(definition.get("allow_import"), "Import permission requires allow_import")
					self.assertFalse(definition.get("issingle"), "Single DocTypes cannot be imported")
					self.assertFalse(definition.get("istable"), "Child DocTypes are not independently imported")
		self.assertTrue(self.load_doctype("camera").get("allow_import"))
		credential = self.load_doctype("camera_credential")
		self.assertFalse(credential.get("allow_import"))
		self.assertFalse(any(perm.get("import") for perm in credential.get("permissions", [])))

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
		self.assertEqual(camera["image_field"], "primary_image")
		map_script = Path(__file__).parent / "page" / "camera_archive_map" / "camera_archive_map.js"
		self.assertIn("iconAnchor: [24, 62]", map_script.read_text(encoding="utf-8"))
		camera_fields = {field["fieldname"]: field for field in camera["fields"]}
		self.assertEqual(camera_fields["importance"]["options"].splitlines()[0], "")
		event_fields = {field["fieldname"]: field for field in self.load_doctype("motion_event")["fields"]}
		self.assertEqual(event_fields["importance"]["options"].splitlines()[0], "")
		self.assertEqual(camera_fields["camera_photos_json"]["fieldtype"], "Long Text")
		self.assertEqual(camera_fields["camera_photo_gallery"]["fieldtype"], "HTML")
		self.assertFalse((DOCTYPE_DIR / "camera_photo" / "camera_photo.json").exists())
		for folder in ("camera", "cam_vehicle", "motion_event", "camera_area", "vehicle_type"):
			fields = {field["fieldname"]: field for field in self.load_doctype(folder)["fields"]}
			self.assertEqual(fields["is_demo_record"]["fieldtype"], "Check")
			self.assertEqual(fields["demo_scenario"]["fieldtype"], "Data")
		map_script_text = map_script.read_text(encoding="utf-8")
		self.assertIn('split("T", 1)', map_script_text)
		self.assertIn("daySpan", map_script_text)
		self.assertIn("Math.max(1, Math.min(12, slot - 4))", map_script_text)
		compat_script = Path(__file__).parents[1] / "public" / "js" / "camera_geolocation_compat.js"
		compat_text = compat_script.read_text(encoding="utf-8")
		self.assertIn('control?.frm?.doctype === "Camera"', compat_text)
		self.assertIn('control?.df?.fieldname === "location"', compat_text)
		self.assertIn("Control.prototype.load_lib", compat_text)
		self.assertIn("leaflet_draw/leaflet.draw.js", compat_text)
		self.assertIn('app_include_js = ["/assets/camera_archive_management/js/camera_geolocation_compat.js"]',
			(Path(__file__).parents[1] / "hooks.py").read_text(encoding="utf-8"))
		camera_list_script = (DOCTYPE_DIR / "camera" / "camera_list.js").read_text(encoding="utf-8")
		self.assertIn("get_custom_map_coords", camera_list_script)
		self.assertIn("render_map_data", camera_list_script)
		self.assertIn("camera_map_detail_card", camera_list_script)
		self.assertIn("mouseover", camera_list_script)
		self.assertIn("marker.openPopup()", camera_list_script)
		self.assertIn("originalEvent?.stopPropagation()", camera_list_script)
		self.assertIn("disableClickPropagation", camera_list_script)
		self.assertIn("autoPanPaddingTopLeft", camera_list_script)
		self.assertIn("Camera Area", camera_list_script)
		self.assertIn("Type & Endpoint", camera_list_script)
		self.assertIn("Status & Activity", camera_list_script)
		self.assertIn("Camera identity", camera_list_script)
		self.assertIn("Geographic context", camera_list_script)
		self.assertIn("Coordinate quality", camera_list_script)
		self.assertIn("Photo gallery", camera_list_script)
		self.assertIn("View camera events", camera_list_script)
		self.assertIn("View camera photo gallery", camera_list_script)
		self.assertIn("ip_address", camera_list_script)
		self.assertNotIn('"username"', camera_list_script)
		self.assertNotIn('"password"', camera_list_script)
		self.assertIn("camera_pin_initials", map_script_text)
		self.assertIn("camera.latest_activity", map_script_text)
		self.assertIn('sirajIcons.pin("Camera"', map_script_text)
		self.assertIn('sirajIcons.pin("Camera"', camera_list_script)
		self.assertIn("sx-pin-wrapper", map_script_text)
		self.assertIn("is-selected", map_script_text)
		self.assertIn("autoPanPaddingTopLeft", map_script_text)
		self.assertIn("Camera Area", map_script_text)
		self.assertIn("Type & Status", map_script_text)
		self.assertIn("Gallery & Actions", map_script_text)
		self.assertIn("Camera identity", map_script_text)
		self.assertIn("Geographic context", map_script_text)
		self.assertIn("Coordinate quality", map_script_text)
		self.assertIn("Photo gallery", map_script_text)
		self.assertIn("append_archive_camera_info_group", map_script_text)
		self.assertIn("cam-camera-gallery", (Path(__file__).parents[1] / "public" / "css" / "camera_archive.css").read_text(encoding="utf-8"))
		self.assertIn("cam-camera-detail-card", (Path(__file__).parents[1] / "public" / "css" / "camera_archive.css").read_text(encoding="utf-8"))
		map_css_text = (Path(__file__).parents[1] / "public" / "css" / "camera_archive.css").read_text(encoding="utf-8")
		self.assertIn(".cam-camera-card-section", map_css_text)
		self.assertIn(".cam-camera-card-coordinate", map_css_text)
		self.assertIn("height: 128px", map_css_text)
		for feature in (
			"Measure distance", "Measure area", "Locate me", "Country borders", "cam-map-time", "include_demo",
			"cam-map-activity-chart", "render_map_insights", "data-kpi-vehicles",
			"cam-map-status", 'data-cam-link="area"', "camera_status", "has_page_route_options",
			"CAM_MAP_OFFLINE_DB", "cache_map_snapshot", "cache_viewed_detail", "show_cached_popup_details",
			"cam-map-save-offline", "cam-map-show-saved", "Not saved for offline use",
			"maxNativeZoom", "update_tile_telemetry", "cam-map-tile-telemetry", "cam-camera-status-${status}",
			"cam-pin-selected", "sync_page_route_to_controls", "Cameras in view", "Recent motion events",
			"Coordinate latitude snapshot", "cam-map-fit", "Fit results", "fit_map_to_results(page)",
			"cam_map_auto_fitted", "cam_map_user_navigated", "errorTileUrl", "missing_tile_fallback",
			'cam-map-include-demo").addEventListener', "cam-camera-card-avatar", "cam-camera-card-meta",
			"cam-camera-card-coordinate", "Gallery & Actions", "Type & Status", "cam-camera-gallery",
			"show_image_unavailable",
		):
			self.assertIn(feature, map_script_text)

		arabic_translations = (Path(__file__).parents[1] / "translations" / "ar.csv").read_text(encoding="utf-8")
		self.assertIn("Fit results,احتواء النتائج", arabic_translations)
		self.assertIn("Tile unavailable,المربع غير متاح", arabic_translations)
		self.assertIn("Type & Status,النوع والحالة", arabic_translations)
		self.assertIn("Gallery & Actions,المعرض والإجراءات", arabic_translations)

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
