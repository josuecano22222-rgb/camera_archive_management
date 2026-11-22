from __future__ import annotations

import frappe
from frappe.model.document import Document

from camera_archive_management.utils.files import is_safe_frappe_file_url


class CameraPhoto(Document):
	def validate(self) -> None:
		if self.sort_order is not None and int(self.sort_order) < 0:
			frappe.throw("Photo sort order cannot be negative.", frappe.ValidationError)
		if self.is_primary and not self.image:
			frappe.throw("A primary camera photo requires an image.", frappe.ValidationError)
		if self.image:
			if not is_safe_frappe_file_url(self.image):
				frappe.throw("Camera photos must use a local Frappe File URL.", frappe.ValidationError)
			if not frappe.db.exists("File", {"file_url": self.image}):
				frappe.throw("Camera photo must reference a registered Frappe File.", frappe.ValidationError)
