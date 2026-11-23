from __future__ import annotations

import frappe
from frappe.model.document import Document


class CameraCredential(Document):
	def validate(self) -> None:
		if not self.camera:
			frappe.throw("A credential record must be linked to a Camera.", frappe.ValidationError)
		if not self.username and not self.password and not self.secondary_secret:
			frappe.throw("At least one credential value is required.", frappe.ValidationError)
