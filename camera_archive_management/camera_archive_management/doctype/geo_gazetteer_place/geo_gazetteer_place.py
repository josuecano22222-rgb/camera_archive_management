from __future__ import annotations

import frappe
from frappe.model.document import Document

from camera_archive_management.geo.coordinates import validate_pair


class GeoGazetteerPlace(Document):
	def validate(self) -> None:
		self.place_code = (self.place_code or "").strip()
		self.place_name = (self.place_name or "").strip()
		if not self.place_code or not self.place_name:
			frappe.throw("Gazetteer place code and name are required.", frappe.ValidationError)
		filters = {"dataset": self.dataset, "place_code": self.place_code}
		if self.name:
			filters["name"] = ["!=", self.name]
		if frappe.db.exists("Geo Gazetteer Place", filters):
			frappe.throw("Gazetteer place code already exists in this dataset.", frappe.DuplicateEntryError)
		try:
			latitude, longitude = validate_pair(self.latitude, self.longitude)
		except ValueError as exc:
			frappe.throw(str(exc), frappe.ValidationError)
		if latitude is None or longitude is None:
			frappe.throw("Gazetteer place requires latitude and longitude.", frappe.ValidationError)
		if self.admin_area:
			linked_dataset = frappe.db.get_value("Geo Admin Area", self.admin_area, "dataset")
			if linked_dataset != self.dataset:
				frappe.throw("Gazetteer admin area must belong to the same dataset.", frappe.ValidationError)
