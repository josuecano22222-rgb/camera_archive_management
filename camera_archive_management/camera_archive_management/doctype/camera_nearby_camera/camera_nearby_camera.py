from __future__ import annotations

import frappe
from frappe.model.document import Document


class CameraNearbyCamera(Document):
	def validate(self) -> None:
		if self.parent and self.camera == self.parent:
			frappe.throw("A Camera cannot be listed as its own nearby camera.", frappe.ValidationError)
