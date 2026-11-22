from __future__ import annotations

import json

import frappe
from frappe.model.document import Document

from camera_archive_management.geo.coordinates import point_from_geojson, validate_pair


class Camera(Document):
	def validate(self) -> None:
		try:
			latitude, longitude = validate_pair(self.latitude, self.longitude)
			point = point_from_geojson(self.location)
		except ValueError as exc:
			frappe.throw(str(exc), frappe.ValidationError)
			return

		if point and latitude is None:
			self.latitude, self.longitude = str(point[0]), str(point[1])
		elif point and (latitude != point[0] or longitude != point[1]):
			frappe.throw(
				"Camera Location point and latitude/longitude disagree. Update them together explicitly.",
				frappe.ValidationError,
			)

		if self.port and not 1 <= int(self.port) <= 65535:
			frappe.throw("Port must be between 1 and 65535.", frappe.ValidationError)
		if sum(1 for row in self.camera_photos if row.is_primary) > 1:
			frappe.throw("A Camera may have only one primary photo.", frappe.ValidationError)
		nearby_names = [row.camera for row in self.nearby_cameras if row.camera]
		if self.name in nearby_names or len(nearby_names) != len(set(nearby_names)):
			frappe.throw(
				"Nearby cameras must be unique and cannot include this camera.", frappe.ValidationError
			)

		if self.area:
			parent = frappe.db.get_value("Camera Area", self.area, "is_group")
			if parent is None:
				frappe.throw("Selected Camera Area does not exist.", frappe.ValidationError)

	def before_save(self) -> None:
		# Location and address are deliberately not reverse-geocoded here. A user
		# must call the explicit lookup API and choose which fields to apply.
		if self.location and not isinstance(self.location, str):
			self.location = json.dumps(self.location, separators=(",", ":"))
