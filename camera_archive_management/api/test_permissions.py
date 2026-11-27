from __future__ import annotations

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from camera_archive_management.api import map as map_api


class TestCameraCredentialsProtection(FrappeTestCase):
	"""Credentials merged into Camera stay System Manager-only at permlevel 1."""

	def _camera_with_credentials(self):
		# camera_name is unique; give every test its own value so repeated inserts
		# never collide, and clean the record up even if the transaction commits.
		camera = frappe.get_doc(
			{
				"doctype": "Camera",
				"naming_series": "CAM-.####",
				"camera_name": f"Credential protection {frappe.generate_hash(length=10)}",
				"status": "Active",
				"latitude": "52.3",
				"longitude": "4.9",
				"camera_photos_json": "[]",
				"nearby_cameras": [],
				"credential_label": "Main account",
				"username": "DO_NOT_EXPOSE_USERNAME",
				"password": "DO_NOT_EXPOSE_PASSWORD",
				"secondary_secret": "DO_NOT_EXPOSE_SECONDARY",
			}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Camera", camera.name, force=True, ignore_permissions=True)
		return camera

	def test_credential_fields_are_stripped_for_non_admin_reads(self):
		original_user = frappe.session.user
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, original_user)
		camera = self._camera_with_credentials()

		frappe.set_user("cam-viewer@example.invalid")
		with patch.object(frappe, "get_roles", return_value=["CAM Viewer"]):
			camera.apply_fieldlevel_read_permissions()
		for fieldname in ("credential_label", "username", "password", "secondary_secret", "credential_notes"):
			self.assertFalse(hasattr(camera, fieldname), f"{fieldname} leaked to a CAM Viewer read")
		self.assertTrue(camera.camera_name.startswith("Credential protection"))

	def test_system_manager_keeps_credential_fields_on_read(self):
		original_user = frappe.session.user
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, original_user)
		camera = self._camera_with_credentials()

		frappe.set_user("manager@example.invalid")
		with patch.object(frappe, "get_roles", return_value=["System Manager"]):
			camera.apply_fieldlevel_read_permissions()
		self.assertEqual(camera.username, "DO_NOT_EXPOSE_USERNAME")
		self.assertTrue(hasattr(camera, "password"))

	def test_unauthorized_credential_writes_are_reset_to_stored_values(self):
		original_user = frappe.session.user
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, original_user)
		camera = self._camera_with_credentials()
		credential_fields = [
			"credential_label",
			"credentials_active",
			"username",
			"password",
			"secondary_secret",
			"last_rotated_at",
			"credential_notes",
		]
		original = frappe.db.get_value("Camera", camera.name, credential_fields, as_dict=True)

		# The insert above intentionally used ignore_permissions=True. Reload a fresh
		# document so that privileged flag cannot leak into the operator save path.
		camera = frappe.get_doc("Camera", camera.name)
		frappe.set_user("cam-operator@example.invalid")
		with patch.object(frappe, "get_roles", return_value=["CAM Operator"]):
			self.assertFalse(camera.flags.ignore_permissions)
			camera.username = "ATTACKER_USERNAME"
			camera.credential_label = "ATTACKER_LABEL"
			camera.credentials_active = 0
			camera.password = "ATTACKER_PASSWORD"
			camera.secondary_secret = "ATTACKER_SECONDARY"
			camera.last_rotated_at = "2030-01-01 00:00:00"
			camera.credential_notes = "ATTACKER_NOTES"
			camera.save(ignore_permissions=False)

		stored = frappe.db.get_value("Camera", camera.name, credential_fields, as_dict=True)
		self.assertEqual(stored, original)
		frappe.set_user("Administrator")
		reloaded = frappe.get_doc("Camera", camera.name)
		self.assertEqual(reloaded.get_password("password"), "DO_NOT_EXPOSE_PASSWORD")
		self.assertEqual(reloaded.get_password("secondary_secret"), "DO_NOT_EXPOSE_SECONDARY")

	def test_password_values_are_encrypted_and_not_stored_in_the_column(self):
		original_user = frappe.session.user
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, original_user)
		camera = self._camera_with_credentials()

		stored = frappe.db.get_value("Camera", camera.name, ["username", "password"], as_dict=True)
		self.assertEqual(stored.username, "DO_NOT_EXPOSE_USERNAME")
		self.assertNotEqual(stored.password, "DO_NOT_EXPOSE_PASSWORD")
		self.assertTrue(set(stored.password) == {"*"})
		self.assertEqual(camera.get_password("password"), "DO_NOT_EXPOSE_PASSWORD")
		self.assertEqual(camera.get_password("secondary_secret"), "DO_NOT_EXPOSE_SECONDARY")

	def test_map_payload_never_serializes_camera_credentials(self):
		original_user = frappe.session.user
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, original_user)
		camera = self._camera_with_credentials()
		payload = map_api.map_payload(camera=camera.name)
		serialized = json.dumps(payload, sort_keys=True)
		self.assertNotIn("DO_NOT_EXPOSE_USERNAME", serialized)
		self.assertNotIn("DO_NOT_EXPOSE_PASSWORD", serialized)
		self.assertNotIn("DO_NOT_EXPOSE_SECONDARY", serialized)
		self.assertNotIn("credential_label", serialized)
		self.assertNotIn("secondary_secret", serialized)
