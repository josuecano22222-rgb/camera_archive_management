from __future__ import annotations

import re

import frappe
from frappe.model.document import Document

from camera_archive_management.geo.coordinates import parse_coordinate

_DATASET_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class GeoDataset(Document):
	def validate(self) -> None:
		previous = self.get_doc_before_save()
		status_changed = not previous or previous.import_status != self.import_status
		if (
			status_changed
			and self.import_status in {"Running", "Complete", "Failed"}
			and not self.flags.get("job_update")
		):
			frappe.throw(
				"Only the dataset importer may set Running, Complete, or Failed status.",
				frappe.PermissionError,
			)
		self.dataset_id = (self.dataset_id or "").strip().lower()
		if not _DATASET_ID.fullmatch(self.dataset_id):
			frappe.throw("Dataset ID must match [a-z0-9][a-z0-9._-]{0,63}.", frappe.ValidationError)

		if self.source_file:
			if not str(self.source_file).startswith("/private/files/"):
				frappe.throw(
					"Dataset GeoJSON source must be a private Frappe attachment.", frappe.ValidationError
				)
			file_doc = frappe.db.get_value(
				"File", {"file_url": self.source_file}, ["name", "is_private"], as_dict=True
			)
			if not file_doc or not file_doc.is_private:
				frappe.throw(
					"Dataset GeoJSON source must be a registered private File.", frappe.ValidationError
				)
		if any(value not in (None, "") for value in (self.west, self.east, self.south, self.north)):
			if any(value in (None, "") for value in (self.west, self.south, self.east, self.north)):
				frappe.throw("Coverage bounds require W, S, E, and N values.", frappe.ValidationError)
			try:
				parse_coordinate(self.west, 180)
				parse_coordinate(self.east, 180)
				south = parse_coordinate(self.south, 90)
				north = parse_coordinate(self.north, 90)
			except ValueError as exc:
				frappe.throw(f"Dataset coverage has invalid WGS84 bounds: {exc}", frappe.ValidationError)
			if south > north:
				frappe.throw(
					"Dataset latitude bounds must have south <= north.", frappe.ValidationError
				)
