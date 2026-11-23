from __future__ import annotations

import frappe
from frappe.model.document import Document


class CameraArea(Document):
	def validate(self) -> None:
		if self.parent_camera_area == self.name:
			frappe.throw("A Camera Area cannot be its own parent.", frappe.ValidationError)
		if self.parent_camera_area:
			parent = frappe.db.get_value("Camera Area", self.parent_camera_area, "is_group")
			if parent is None:
				frappe.throw("Parent Camera Area does not exist.", frappe.ValidationError)
			if not parent:
				frappe.throw("Parent Camera Area must be a group.", frappe.ValidationError)
