from __future__ import annotations

import frappe
from frappe.model.document import Document

from camera_archive_management.geo.coordinates import parse_coordinate
from camera_archive_management.geo.geometry import geometry_bounds


class GeoBoundary(Document):
	def validate(self) -> None:
		self.boundary_code = (self.boundary_code or "").strip()
		self.label = (self.label or "").strip()
		if not self.boundary_code or len(self.boundary_code) > 140 or not self.label:
			frappe.throw("Boundary code and label are required.", frappe.ValidationError)
		if not self.flags.get("prevalidated_boundary_code"):
			filters = {"dataset": self.dataset, "boundary_code": self.boundary_code}
			if self.name:
				filters["name"] = ["!=", self.name]
			if frappe.db.exists("Geo Boundary", filters):
				frappe.throw("Boundary code already exists in this dataset.", frappe.DuplicateEntryError)
		if self.parent_boundary == self.name:
			frappe.throw("A boundary cannot be its own parent.", frappe.ValidationError)
		if not self.flags.get("prevalidated_dataset_links"):
			for link_field, target in (("parent_boundary", "Geo Boundary"), ("admin_area", "Geo Admin Area")):
				linked = self.get(link_field)
				if linked:
					linked_dataset = frappe.db.get_value(target, linked, "dataset")
					if linked_dataset != self.dataset:
						frappe.throw(
							f"{link_field.replace('_', ' ').title()} must belong to the same dataset."
						)

		if not self.geometries:
			frappe.throw("At least one boundary geometry is required.", frappe.ValidationError)
		geometry_rows = [row for row in self.geometries if row.geometry_role == "Resolution"]
		if not geometry_rows:
			frappe.throw("A Resolution geometry is required for spatial lookup.", frappe.ValidationError)
		geometry = geometry_rows[0].geojson
		try:
			geometry_west, geometry_south, geometry_east, geometry_north = geometry_bounds(geometry)
			parse_coordinate(self.centroid_lat, 90)
			parse_coordinate(self.centroid_lon, 180)
			if (self.centroid_lat in (None, "")) != (self.centroid_lon in (None, "")):
				frappe.throw("Boundary centroid requires both latitude and longitude.", frappe.ValidationError)
			west = parse_coordinate(self.west, 180) if self.west not in (None, "") else geometry_west
			east = parse_coordinate(self.east, 180) if self.east not in (None, "") else geometry_east
			south = parse_coordinate(self.south, 90) if self.south not in (None, "") else geometry_south
			north = parse_coordinate(self.north, 90) if self.north not in (None, "") else geometry_north
		except ValueError as exc:
			frappe.throw(str(exc), frappe.ValidationError)
		if self.west in (None, ""):
			self.west = str(geometry_west)
		if self.south in (None, ""):
			self.south = str(geometry_south)
		if self.east in (None, ""):
			self.east = str(geometry_east)
		if self.north in (None, ""):
			self.north = str(geometry_north)
		if south > north:
			frappe.throw("Boundary latitude bounds must have south <= north.", frappe.ValidationError)
		if south > geometry_south or north < geometry_north:
			frappe.throw(
				"Boundary latitude bounds must contain the full resolution geometry.", frappe.ValidationError
			)
		if west <= east and (west > geometry_west or east < geometry_east):
			frappe.throw(
				"Boundary longitude bounds must contain the full resolution geometry.", frappe.ValidationError
			)
