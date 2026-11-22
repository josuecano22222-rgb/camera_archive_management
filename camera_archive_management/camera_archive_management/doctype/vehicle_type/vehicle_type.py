from __future__ import annotations

import frappe
from frappe.model.document import Document

from camera_archive_management.utils.files import is_safe_frappe_file_url


class VehicleType(Document):
	def validate(self) -> None:
		self.type_name = (self.type_name or "").strip()
		if not self.type_name:
			frappe.throw("Vehicle Type name is required.", frappe.ValidationError)
		if self.vehicle_type_image:
			if not is_safe_frappe_file_url(self.vehicle_type_image):
				frappe.throw("Vehicle type image must use a local Frappe File URL.", frappe.ValidationError)
			if not frappe.db.exists("File", {"file_url": self.vehicle_type_image}):
				frappe.throw("Vehicle type image must reference a registered Frappe File.", frappe.ValidationError)

	def on_update(self) -> None:
		"""Refresh list-image fallbacks for vehicles without a dedicated image."""
		vehicles = frappe.get_all(
			"CAM Vehicle",
			filters={"vehicle_type": self.name},
			fields=["name", "vehicle_image"],
			order_by="name asc",
			limit_page_length=5000,
		)
		for vehicle in vehicles:
			if vehicle.vehicle_image:
				continue
			frappe.db.set_value(
				"CAM Vehicle", vehicle.name, "vehicle_list_image", self.vehicle_type_image or None,
				update_modified=False,
			)
