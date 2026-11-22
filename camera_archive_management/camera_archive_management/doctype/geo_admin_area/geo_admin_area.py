from __future__ import annotations

import frappe
from frappe.model.document import Document

from camera_archive_management.geo.coordinates import validate_pair


class GeoAdminArea(Document):
	def validate(self) -> None:
		self.code = (self.code or "").strip()
		self.label = (self.label or "").strip()
		if not self.code or len(self.code) > 140 or not self.label:
			frappe.throw("Administrative area code and label are required.", frappe.ValidationError)
		if self.parent_area == self.name:
			frappe.throw("An administrative area cannot be its own parent.", frappe.ValidationError)
		if self.parent_area:
			parent = frappe.db.get_value(
				"Geo Admin Area", self.parent_area, ["dataset", "is_group"], as_dict=True
			)
			if not parent or parent.dataset != self.dataset:
				frappe.throw(
					"Parent administrative area must belong to the same dataset.", frappe.ValidationError
				)
			if not parent.is_group:
				frappe.throw("Parent administrative area must be a group.", frappe.ValidationError)
		try:
			validate_pair(self.latitude, self.longitude)
		except ValueError as exc:
			frappe.throw(str(exc), frappe.ValidationError)

		filters = {"dataset": self.dataset, "code": self.code}
		if self.name:
			filters["name"] = ["!=", self.name]
		if frappe.db.exists("Geo Admin Area", filters):
			frappe.throw("This area code already exists within the dataset.", frappe.DuplicateEntryError)
