from __future__ import annotations

import frappe
from frappe.model.document import Document


class ArchiveSettings(Document):
	def validate(self) -> None:
		if self.default_report_days is not None and not 1 <= int(self.default_report_days) <= 3650:
			frappe.throw("Default report days must be between 1 and 3650.", frappe.ValidationError)
		if self.nearby_camera_radius is not None and not 0 <= int(self.nearby_camera_radius) <= 100_000:
			frappe.throw("Nearby-camera radius must be between 0 and 100000 meters.", frappe.ValidationError)
		if self.default_retention_days is not None and int(self.default_retention_days) < 0:
			frappe.throw("Retention days cannot be negative.", frappe.ValidationError)
