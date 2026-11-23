from __future__ import annotations

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from camera_archive_management.api import map as map_api
from camera_archive_management.api import permissions


class TestCredentialPermissions(FrappeTestCase):
	def test_credential_query_is_hidden_from_non_admin_roles(self):
		with patch.object(frappe, "get_roles", return_value=["CAM Viewer"]):
			self.assertFalse(permissions.camera_credential_has_permission(user="cam-viewer@example.invalid"))
			self.assertEqual(permissions.camera_credential_query_conditions("cam-viewer@example.invalid"), "1=0")

	def test_system_manager_and_site_administrator_are_authorized(self):
		with patch.object(frappe, "get_roles", return_value=["System Manager"]):
			self.assertTrue(permissions.camera_credential_has_permission(user="manager@example.invalid"))
			self.assertTrue(permissions._is_credential_authorized(user="manager@example.invalid"))
		self.assertTrue(permissions.camera_credential_has_permission(user="Administrator"))

	def test_query_condition_follows_authorization_decision(self):
		with patch.object(permissions, "_is_credential_authorized", return_value=True) as authorize:
			self.assertEqual(permissions.camera_credential_query_conditions("manager@example.invalid"), "")
		authorize.assert_called_once_with("manager@example.invalid")
		with patch.object(permissions, "_is_credential_authorized", return_value=False) as authorize:
			self.assertEqual(permissions.camera_credential_query_conditions("viewer@example.invalid"), "1=0")
		authorize.assert_called_once_with("viewer@example.invalid")

	def test_map_payload_never_serializes_camera_credentials(self):
		original_user = frappe.session.user
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, original_user)
		camera = frappe.get_doc(
			{
				"doctype": "Camera",
				"naming_series": "CAM-.####",
				"camera_name": "Credential disclosure test camera",
				"status": "Active",
				"latitude": "52.3",
				"longitude": "4.9",
				"camera_photos_json": "[]",
				"nearby_cameras": [],
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Camera Credential",
				"camera": camera.name,
				"username": "DO_NOT_EXPOSE_USERNAME",
				"password": "DO_NOT_EXPOSE_PASSWORD",
				"active": 1,
			}
		).insert(ignore_permissions=True)
		payload = map_api.map_payload(camera=camera.name)
		serialized = json.dumps(payload, sort_keys=True)
		self.assertNotIn("DO_NOT_EXPOSE_USERNAME", serialized)
		self.assertNotIn("DO_NOT_EXPOSE_PASSWORD", serialized)
		self.assertNotIn("Camera Credential", serialized)
