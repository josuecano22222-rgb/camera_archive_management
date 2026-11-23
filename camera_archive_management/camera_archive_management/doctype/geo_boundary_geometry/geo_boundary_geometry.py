from __future__ import annotations

import hashlib
from decimal import Decimal

import frappe
from frappe.model.document import Document

from camera_archive_management.geo.geometry import dumps_geojson, geometry_bounds, load_geometry


class GeoBoundaryGeometry(Document):
	def validate(self) -> None:
		try:
			geometry = load_geometry(self.geojson)
			geometry_bounds(geometry)
		except ValueError as exc:
			frappe.throw(str(exc), frappe.ValidationError)
		self.geometry_type = geometry["type"]
		canonical = dumps_geojson(geometry)
		self.geojson = canonical
		self.sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
		self.vertex_count = sum(1 for _ in _positions(geometry.get("coordinates")))
		if self.srid and int(self.srid) != 4326:
			frappe.throw("Spatial geometry must use WGS84 / EPSG:4326 (SRID 4326).", frappe.ValidationError)


def _positions(value):
	if (
		isinstance(value, list)
		and len(value) >= 2
		and all(isinstance(part, int | float | Decimal) for part in value[:2])
	):
		yield value
	elif isinstance(value, list):
		for child in value:
			yield from _positions(child)
