"""Normalize Camera.location to the FeatureCollection shape used by Frappe Geolocation."""

from __future__ import annotations

import frappe

from camera_archive_management.geo.coordinates import (
	normalize_frappe_geolocation,
	point_feature_collection,
	point_from_geojson,
	validate_pair,
)


def execute() -> None:
	"""Repair legacy Point values that break Frappe's native Geolocation list/form maps."""
	rows = frappe.get_all(
		"Camera",
		fields=["name", "location", "latitude", "longitude"],
		order_by="name asc",
		limit_page_length=0,
	)
	updated = 0
	for row in rows:
		try:
			latitude, longitude = validate_pair(row.latitude, row.longitude)
		except ValueError:
			latitude = longitude = None
		try:
			point = point_from_geojson(row.location) if row.location else None
		except ValueError:
			point = None

		if latitude is None and longitude is None and point:
			latitude, longitude = point
		if latitude is None or longitude is None:
			continue

		try:
			if point == (latitude, longitude) and row.location:
				location = normalize_frappe_geolocation(row.location)
			else:
				# Keep the explicitly stored coordinate fields authoritative when a
				# legacy location disagrees or cannot be parsed.
				location = point_feature_collection(latitude, longitude)
		except ValueError:
			continue

		values = {"location": location}
		if row.latitude != str(latitude):
			values["latitude"] = str(latitude)
		if row.longitude != str(longitude):
			values["longitude"] = str(longitude)
		if row.location != location or len(values) > 1:
			frappe.db.set_value("Camera", row.name, values, update_modified=False)
			updated += 1
	if updated:
		frappe.logger("camera_archive_management.geo").info(
			"Normalized %s Camera.location values for Frappe Geolocation compatibility.", updated
		)
