from __future__ import annotations

from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from camera_archive_management.patches.v1_0 import (
	assert_doctype_namespace,
	ensure_child_table_columns,
	ensure_unique_keys,
	merge_camera_credentials,
	migrate_camera_photo_gallery,
	normalize_camera_geolocation,
	remove_archive_doctypes,
	rename_geo_settings,
	rename_vehicle_camera,
)


class TestMigrationGuards(FrappeTestCase):
	def test_camera_geolocation_patch_wraps_legacy_point_for_native_map(self):
		row = frappe._dict(
			name="CAM-LEGACY-POINT",
			location='{"type":"Point","coordinates":[4.90000000000000000001,52.30000000000000000002]}',
			latitude="52.30000000000000000002",
			longitude="4.90000000000000000001",
		)
		with (
			patch.object(frappe, "get_all", return_value=[row]),
			patch.object(frappe.db, "set_value") as set_value,
			patch.object(frappe, "logger"),
		):
			normalize_camera_geolocation.execute()
		updates = set_value.call_args.args[2]
		self.assertIn('"type":"FeatureCollection"', updates["location"])
		self.assertIn('"point_type":"marker"', updates["location"])
		self.assertIn("[4.90000000000000000001,52.30000000000000000002]", updates["location"])

	def test_namespace_check_is_repeatable_when_no_app_tables_exist_yet(self):
		with patch.object(frappe.db, "exists", return_value=False):
			assert_doctype_namespace.execute()
			assert_doctype_namespace.execute()

	def test_camera_photo_gallery_patch_is_noop_when_legacy_doctype_is_absent(self):
		with (
			patch.object(frappe.db, "exists", return_value=False),
			patch.object(frappe.db, "table_exists", return_value=False),
		):
			migrate_camera_photo_gallery.execute()
			migrate_camera_photo_gallery.execute()

	def _run_gallery_migration_with_file(self, file_doc):
		legacy_row = frappe._dict(
			name="CAM-PHOTO-1",
			parent="CAM-1",
			parenttype="Camera",
			parentfield="camera_photos",
			idx=1,
			image="/private/files/legacy-camera.jpg",
			caption="Legacy caption",
			description="Legacy description",
			is_primary=1,
			sort_order=0,
		)

		def get_all(doctype, filters=None, pluck=None, **kwargs):
			if doctype in ("DocField", "Custom Field"):
				return []
			if doctype == "Camera":
				return ["CAM-1"]
			if doctype == "Camera Photo":
				return [legacy_row]
			if doctype == "File":
				if filters and "file_url" in filters:
					return [file_doc] if file_doc else []
				return []
			return []

		with (
			patch.object(
				frappe.db, "exists", side_effect=lambda dt, name: dt == "DocType" and name == "Camera Photo"
			),
			patch.object(frappe.db, "table_exists", side_effect=lambda dt: dt == "Camera Photo"),
			patch.object(
				frappe.db,
				"get_value",
				side_effect=lambda dt, name, field: "Camera Archive Management"
				if dt == "DocType"
				else "camera_archive_management",
			),
			patch.object(frappe.db, "has_column", return_value=True),
			patch.object(frappe.db, "count", return_value=1),
			patch.object(frappe.db, "set_value") as set_value,
			patch.object(frappe, "get_all", side_effect=get_all),
			patch.object(frappe, "delete_doc") as delete_doc,
			patch.object(frappe, "clear_cache"),
		):
			migrate_camera_photo_gallery.execute()
		return set_value.call_args_list, delete_doc

	def test_gallery_reference_scan_uses_the_correct_owner_column_per_doctype(self):
		with patch.object(frappe, "get_all", return_value=[]) as get_all:
			migrate_camera_photo_gallery._assert_no_references()
		self.assertEqual(get_all.call_args_list[0].args[0], "DocField")
		self.assertEqual(get_all.call_args_list[0].kwargs["fields"], ["parent", "fieldname"])
		self.assertEqual(get_all.call_args_list[1].args[0], "Custom Field")
		self.assertEqual(get_all.call_args_list[1].kwargs["fields"], ["dt", "fieldname"])

	def test_gallery_reference_scan_blocks_external_custom_field(self):
		def get_all(doctype, **kwargs):
			if doctype == "Custom Field":
				return [frappe._dict(dt="Camera", fieldname="legacy_photo_link")]
			return []

		with patch.object(frappe, "get_all", side_effect=get_all):
			with self.assertRaises(frappe.ValidationError):
				migrate_camera_photo_gallery._assert_no_references()

	def test_gallery_migration_preserves_metadata_and_reassigns_legacy_file(self):
		file_doc = frappe._dict(
			name="FILE-1",
			file_url="/private/files/legacy-camera.jpg",
			file_name="legacy-camera.jpg",
			attached_to_doctype="Camera Photo",
			attached_to_name="CAM-PHOTO-1",
			attached_to_field=None,
		)
		updates, delete_doc = self._run_gallery_migration_with_file(file_doc)
		file_update = next(args for args, _kwargs in updates if args[0] == "File")
		self.assertEqual(file_update[2]["attached_to_doctype"], "Camera")
		self.assertEqual(file_update[2]["attached_to_name"], "CAM-1")
		camera_update = next(args for args, _kwargs in updates if args[0] == "Camera")
		photos = frappe.parse_json(camera_update[2]["camera_photos_json"])
		self.assertEqual(photos[0]["caption"], "Legacy caption")
		self.assertEqual(photos[0]["description"], "Legacy description")
		self.assertTrue(photos[0]["is_primary"])
		self.assertEqual(camera_update[2]["primary_image"], file_doc.file_url)
		delete_doc.assert_called_once_with("DocType", "Camera Photo", force=True, ignore_permissions=True)

	def test_gallery_migration_keeps_already_camera_attached_file_and_is_repeatable(self):
		file_doc = frappe._dict(
			name="FILE-1",
			file_url="/private/files/legacy-camera.jpg",
			file_name="legacy-camera.jpg",
			attached_to_doctype="Camera",
			attached_to_name="CAM-1",
			attached_to_field=None,
		)
		first_updates, _delete_doc = self._run_gallery_migration_with_file(file_doc)
		second_updates, _delete_doc = self._run_gallery_migration_with_file(file_doc)
		self.assertEqual([args[0] for args, _kwargs in first_updates], ["Camera"])
		self.assertEqual([args[0] for args, _kwargs in second_updates], ["Camera"])
		self.assertEqual(first_updates[0][0][2], second_updates[0][0][2])

	def test_siraj_owned_geo_settings_is_never_renamed(self):
		def exists(doctype, name):
			return doctype == "DocType" and name == "Geo Settings"

		def get_value(doctype, name, fieldname):
			if doctype == "DocType" and name == "Geo Settings":
				return "Siraj Geo Settings"
			if doctype == "Module Def" and name == "Siraj Geo Settings":
				return "siraj_research"
			return None

		with (
			patch.object(frappe.db, "exists", side_effect=exists),
			patch.object(frappe.db, "get_value", side_effect=get_value),
			patch.object(frappe, "rename_doc") as rename_doc,
		):
			rename_geo_settings.execute()
			rename_geo_settings.execute()
		rename_doc.assert_not_called()

	def test_vehicle_rename_fails_closed_on_foreign_target(self):
		def exists(doctype, name):
			return doctype == "DocType" and name == "CAM Vehicle"

		def get_value(doctype, name, fieldname):
			if doctype == "DocType" and name == "CAM Vehicle":
				return "Foreign Module"
			if doctype == "Module Def" and name == "Foreign Module":
				return "another_app"
			return None

		with (
			patch.object(frappe.db, "exists", side_effect=exists),
			patch.object(frappe.db, "table_exists", return_value=False),
			patch.object(frappe.db, "get_value", side_effect=get_value),
			patch.object(frappe, "rename_doc") as rename_doc,
		):
			with self.assertRaises(frappe.ValidationError):
				rename_vehicle_camera.execute()
		rename_doc.assert_not_called()

	def test_absent_credential_sources_are_repeatable(self):
		with (
			patch.object(frappe.db, "exists", return_value=False),
			patch.object(frappe.db, "table_exists", return_value=False),
			patch.object(frappe.db, "has_column", return_value=False),
			patch.object(frappe, "delete_doc") as delete_doc,
		):
			merge_camera_credentials.execute()
			merge_camera_credentials.execute()
		delete_doc.assert_not_called()

	def test_credential_merge_moves_secrets_and_retires_the_doctype(self):
		credential_row = frappe._dict(
			name="CRED-1",
			camera="CAM-1",
			credential_label="Main account",
			active=1,
			username="operator",
			last_rotated_at=None,
			notes="",
		)
		camera_doc = frappe._dict(name="CAM-1")
		camera_doc.save = Mock()
		credential_doc = frappe._dict(name="CRED-1", password="*****", secondary_secret=None)
		credential_doc.get_password = Mock(
			side_effect=lambda fieldname, raise_exception=True: "s3cret" if fieldname == "password" else None
		)

		def exists(doctype, name=None):
			if doctype == "DocType":
				return name == "Camera Credential"
			return doctype == "Camera"

		def get_value(doctype, name, fieldname):
			if doctype == "DocType":
				return "Camera Archive Management"
			if doctype == "Module Def":
				return "camera_archive_management"
			return None

		def get_doc(doctype, name=None):
			if doctype == "Camera":
				return camera_doc
			if doctype == "Camera Credential":
				return credential_doc
			raise AssertionError(doctype)

		with (
			patch.object(frappe.db, "exists", side_effect=exists),
			patch.object(
				frappe.db,
				"table_exists",
				side_effect=lambda dt, cached=True: dt in ("Camera", "Camera Credential"),
			),
			patch.object(frappe.db, "has_column", return_value=True),
			patch.object(frappe.db, "sql", return_value=[]),
			patch.object(frappe.db, "get_value", side_effect=get_value),
			patch.object(frappe, "get_all", return_value=[credential_row]),
			patch.object(frappe, "get_doc", side_effect=get_doc),
			patch.object(frappe.db, "delete") as delete,
			patch.object(frappe.db, "sql_ddl") as sql_ddl,
			patch.object(frappe, "delete_doc") as delete_doc,
			patch.object(frappe, "clear_cache"),
			patch.object(frappe, "logger"),
		):
			merge_camera_credentials.execute()

		self.assertEqual(camera_doc.username, "operator")
		self.assertEqual(camera_doc.password, "s3cret")
		self.assertEqual(camera_doc.credential_label, "Main account")
		self.assertEqual(camera_doc.credentials_active, 1)
		camera_doc.save.assert_called_once_with(ignore_permissions=True)
		delete.assert_called_once_with("__Auth", {"doctype": "Camera Credential"})
		sql_ddl.assert_called_once_with("DROP TABLE IF EXISTS `tabCamera Credential`")
		delete_doc.assert_called_once_with(
			"DocType", "Camera Credential", force=True, ignore_permissions=True
		)

	def test_credential_merge_fails_closed_on_duplicate_camera_credentials(self):
		rows = [
			frappe._dict(name="CRED-1", camera="CAM-1"),
			frappe._dict(name="CRED-2", camera="CAM-1"),
		]
		with (
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe.db, "table_exists", return_value=True),
			patch.object(frappe.db, "has_column", return_value=True),
			patch.object(frappe.db, "sql", return_value=[]),
			patch.object(
				frappe.db,
				"get_value",
				side_effect=lambda dt, name, field: "Camera Archive Management"
				if dt == "DocType"
				else "camera_archive_management",
			),
			patch.object(frappe, "get_all", return_value=rows),
			patch.object(frappe, "delete_doc") as delete_doc,
		):
			with self.assertRaises(frappe.ValidationError):
				merge_camera_credentials.execute()
		delete_doc.assert_not_called()

	def test_credential_merge_fails_closed_on_foreign_ownership(self):
		with (
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe.db, "table_exists", return_value=True),
			patch.object(frappe.db, "has_column", return_value=True),
			patch.object(frappe.db, "sql", return_value=[]),
			patch.object(
				frappe.db,
				"get_value",
				side_effect=lambda dt, name, field: "Foreign Module" if dt == "DocType" else "another_app",
			),
			patch.object(frappe, "delete_doc") as delete_doc,
		):
			with self.assertRaises(frappe.PermissionError):
				merge_camera_credentials.execute()
		delete_doc.assert_not_called()

	def test_absent_archive_doctypes_are_repeatable(self):
		with (
			patch.object(frappe.db, "exists", return_value=False),
			patch.object(frappe, "get_all", return_value=[]),
			patch.object(frappe.db, "table_exists", return_value=False),
			patch.object(frappe.db, "delete"),
			patch.object(frappe.db, "sql_ddl") as sql_ddl,
			patch.object(frappe, "delete_doc") as delete_doc,
		):
			remove_archive_doctypes.execute()
			remove_archive_doctypes.execute()
		delete_doc.assert_not_called()
		sql_ddl.assert_not_called()

	def test_archive_removal_drops_retired_tables_and_single_values(self):
		with (
			patch.object(frappe.db, "exists", return_value=False),
			patch.object(frappe, "get_all", return_value=[]),
			patch.object(
				frappe.db,
				"table_exists",
				side_effect=lambda dt, cached=True: dt in ("Archive Asset", "Archive Ingest Batch"),
			),
			patch.object(frappe.db, "delete") as delete,
			patch.object(frappe.db, "sql_ddl") as sql_ddl,
			patch.object(frappe, "delete_doc") as delete_doc,
		):
			remove_archive_doctypes.execute()
		delete.assert_any_call("Singles", {"doctype": "Archive Settings"})
		self.assertEqual(sql_ddl.call_count, 2)
		sql_ddl.assert_any_call("DROP TABLE IF EXISTS `tabArchive Asset`")
		sql_ddl.assert_any_call("DROP TABLE IF EXISTS `tabArchive Ingest Batch`")
		delete_doc.assert_not_called()

	def test_archive_removal_fails_closed_on_external_link(self):
		external_field = frappe._dict(parent="Motion Event", fieldname="asset", options="Archive Asset")
		with (
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(
				frappe.db,
				"get_value",
				side_effect=lambda dt, name, field: "Camera Archive Management"
				if dt == "DocType"
				else "camera_archive_management",
			),
			patch.object(frappe, "get_all", return_value=[external_field]),
			patch.object(frappe, "delete_doc") as delete_doc,
		):
			with self.assertRaises(frappe.ValidationError):
				remove_archive_doctypes.execute()
		delete_doc.assert_not_called()

	def test_archive_removal_preserves_motion_settings_before_deleting(self):
		singles_rows = [
			frappe._dict(field="default_motion_importance", value="High"),
			frappe._dict(field="nearby_camera_radius", value="250"),
		]
		with (
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(
				frappe.db,
				"get_value",
				side_effect=lambda dt, name, field: "Camera Archive Management"
				if dt == "DocType"
				else "camera_archive_management",
			),
			patch.object(frappe, "get_all", return_value=[]),
			patch.object(frappe.db, "table_exists", return_value=False),
			patch.object(frappe.db, "sql", return_value=singles_rows),
			patch.object(frappe.db, "set_single_value") as set_single_value,
			patch.object(frappe.db, "delete"),
			patch.object(frappe, "delete_doc") as delete_doc,
			patch.object(frappe, "clear_cache"),
		):
			remove_archive_doctypes.execute()
		set_single_value.assert_any_call(
			"CAM Geo Settings", "default_motion_importance", "High", update_modified=False
		)
		set_single_value.assert_any_call(
			"CAM Geo Settings", "nearby_camera_radius", "250", update_modified=False
		)
		self.assertEqual(delete_doc.call_count, 3)
		for call in delete_doc.call_args_list:
			self.assertEqual(call.args[0], "DocType")
			self.assertIn(call.args[1], ("Archive Asset", "Archive Ingest Batch", "Archive Settings"))

	def test_archive_removal_fails_closed_on_conflicting_legacy_settings(self):
		legacy_rows = [
			frappe._dict(
				default_motion_importance="High", enable_nearby_camera_alerts=1, nearby_camera_radius=250
			),
			frappe._dict(
				default_motion_importance="Low", enable_nearby_camera_alerts=1, nearby_camera_radius=250
			),
		]
		with (
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(
				frappe.db,
				"get_value",
				side_effect=lambda dt, name, field: "Camera Archive Management"
				if dt == "DocType"
				else "camera_archive_management",
			),
			patch.object(frappe, "get_all", return_value=[]),
			patch.object(frappe.db, "table_exists", return_value=True),
			patch.object(frappe.db, "get_table_columns", return_value=list(legacy_rows[0].keys())),
			patch.object(frappe.db, "sql", side_effect=[[], legacy_rows]),
			patch.object(frappe, "delete_doc") as delete_doc,
		):
			with self.assertRaises(frappe.ValidationError):
				remove_archive_doctypes.execute()
		delete_doc.assert_not_called()

	def test_absent_child_and_unique_tables_are_repeatable(self):
		with (
			patch.object(frappe, "get_all", return_value=[]),
			patch.object(frappe.db, "table_exists", return_value=False),
		):
			ensure_child_table_columns.execute()
			ensure_child_table_columns.execute()
			ensure_unique_keys.execute()
			ensure_unique_keys.execute()
