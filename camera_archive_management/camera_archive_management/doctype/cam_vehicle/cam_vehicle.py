from __future__ import annotations

import frappe
from frappe.model.document import Document

from camera_archive_management.utils.files import is_safe_frappe_file_url


class CAMVehicle(Document):
	def validate(self) -> None:
		self.vehicle_name = (self.vehicle_name or "").strip()
		self.vehicle_number = (self.vehicle_number or "").strip()
		if not self.vehicle_name:
			frappe.throw("Vehicle name is required.", frappe.ValidationError)
		if self.vehicle_image:
			if not is_safe_frappe_file_url(self.vehicle_image):
				frappe.throw("Vehicle image must use a local Frappe File URL.", frappe.ValidationError)
			if not frappe.db.exists("File", {"file_url": self.vehicle_image}):
				frappe.throw("Vehicle image must reference a registered Frappe File.", frappe.ValidationError)
		self.vehicle_list_image = self.vehicle_image
		if not self.vehicle_list_image and self.vehicle_type:
			type_image = frappe.db.get_value("Vehicle Type", self.vehicle_type, "vehicle_type_image")
			if type_image and is_safe_frappe_file_url(type_image) and frappe.db.exists("File", {"file_url": type_image}):
				self.vehicle_list_image = type_image
