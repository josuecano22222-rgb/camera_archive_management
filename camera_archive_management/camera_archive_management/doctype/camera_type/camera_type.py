from __future__ import annotations

import frappe
from frappe.model.document import Document


class CameraType(Document):
	def validate(self) -> None:
		self.type_name = (self.type_name or "").strip()
		if not self.type_name:
			frappe.throw("Camera Type name is required.", frappe.ValidationError)
