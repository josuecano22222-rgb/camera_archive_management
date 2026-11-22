from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from camera_archive_management.patches.v1_0 import (
	assert_doctype_namespace,
	ensure_child_table_columns,
	ensure_unique_keys,
	isolate_camera_credentials,
	migrate_archive_settings_single,
	rename_geo_settings,
	rename_vehicle_camera,
)


class TestMigrationGuards(FrappeTestCase):
	def test_namespace_check_is_repeatable_when_no_app_tables_exist_yet(self):
		with patch.object(frappe.db, "exists", return_value=False):
			assert_doctype_namespace.execute()
			assert_doctype_namespace.execute()

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

	def test_absent_legacy_settings_and_credential_tables_are_repeatable(self):
		with patch.object(frappe.db, "table_exists", return_value=False), patch.object(
			frappe, "reload_doc"
		) as reload_doc:
			migrate_archive_settings_single.execute()
			migrate_archive_settings_single.execute()
			isolate_camera_credentials.execute()
			isolate_camera_credentials.execute()
		self.assertEqual(reload_doc.call_count, 2)

	def test_absent_child_and_unique_tables_are_repeatable(self):
		with patch.object(frappe, "get_all", return_value=[]), patch.object(
			frappe.db, "table_exists", return_value=False
		):
			ensure_child_table_columns.execute()
			ensure_child_table_columns.execute()
			ensure_unique_keys.execute()
			ensure_unique_keys.execute()
