from __future__ import annotations

import json
import math

import frappe
from frappe.model.document import Document
from frappe.query_builder.functions import Cast

from camera_archive_management.geo.coordinates import validate_pair
from camera_archive_management.geo.geometry import bearing_degrees, compass_8, haversine_m


class MotionEvent(Document):
	def before_insert(self) -> None:
		self._snapshot_camera_context()
		self._populate_nearby_cameras()

	def validate(self) -> None:
		previous = self.get_doc_before_save()
		if previous and not self.flags.get("allow_snapshot_edit"):
			for field in (
				"camera_name_snapshot",
				"camera_type_snapshot",
				"camera_area_snapshot",
				"address_snapshot",
				"latitude_snapshot",
				"longitude_snapshot",
				"location_snapshot",
				"geo_admin_area_snapshot",
				"location_source_snapshot",
				"location_confidence_snapshot",
				"location_ambiguous_snapshot",
				"location_resolved_at_snapshot",
			):
				if self.get(field) != previous.get(field):
					frappe.throw(
						"Motion Event camera/location snapshots are immutable.", frappe.PermissionError
					)
		try:
			validate_pair(self.latitude_snapshot, self.longitude_snapshot)
		except ValueError as exc:
			frappe.throw(str(exc), frappe.ValidationError)
		if self.detected_at and not self.camera:
			frappe.throw("A Motion Event requires a Camera.", frappe.ValidationError)

	def before_submit(self) -> None:
		if not self.camera or not self.detected_at or not self.motion_type:
			frappe.throw("Camera, event time, and motion type are required before submission.")

	def _snapshot_camera_context(self) -> None:
		if not self.camera:
			return
		fields = [
			"camera_name",
			"camera_type",
			"area",
			"address",
			"latitude",
			"longitude",
			"location",
			"geo_admin_area",
			"lookup_source",
			"lookup_confidence",
			"lookup_ambiguous",
			"lookup_resolved_at",
		]
		camera = frappe.db.get_value("Camera", self.camera, fields, as_dict=True)
		if not camera:
			frappe.throw("Selected Camera does not exist.", frappe.ValidationError)
		mappings = {
			"camera_name_snapshot": "camera_name",
			"camera_type_snapshot": "camera_type",
			"camera_area_snapshot": "area",
			"address_snapshot": "address",
			"latitude_snapshot": "latitude",
			"longitude_snapshot": "longitude",
			"geo_admin_area_snapshot": "geo_admin_area",
			"location_source_snapshot": "lookup_source",
			"location_confidence_snapshot": "lookup_confidence",
			"location_ambiguous_snapshot": "lookup_ambiguous",
			"location_resolved_at_snapshot": "lookup_resolved_at",
		}
		for target, source in mappings.items():
			self.set(target, camera.get(source))
		value = camera.get("location")
		self.location_snapshot = (
			value if isinstance(value, str) else json.dumps(value, separators=(",", ":")) if value else None
		)
		if not camera.get("lookup_source") and (
			camera.get("latitude") is not None or camera.get("longitude") is not None
		):
			self.location_source_snapshot = "manual"

	def _populate_nearby_cameras(self) -> None:
		if (
			self.nearby_cameras
			or not self.camera
			or self.latitude_snapshot is None
			or self.longitude_snapshot is None
		):
			return
		try:
			settings = frappe.get_single("Archive Settings")
			radius = int(settings.nearby_camera_radius or 0)
		except Exception:
			radius = 0
			settings = None
		if not radius or (settings and not settings.enable_nearby_camera_alerts):
			return
		lat, lon = float(self.latitude_snapshot), float(self.longitude_snapshot)
		lat_delta = radius / 110_574.0
		lon_delta = min(180.0, radius / (111_320.0 * max(0.01, math.cos(math.radians(lat)))))
		Camera = frappe.qb.DocType("Camera")
		latitude = Cast(Camera.latitude, "DECIMAL(65,30)")
		longitude = Cast(Camera.longitude, "DECIMAL(65,30)")
		west, east = lon - lon_delta, lon + lon_delta
		if west < -180:
			longitude_matches = (longitude >= west + 360) | (longitude <= east)
		elif east > 180:
			longitude_matches = (longitude >= west) | (longitude <= east - 360)
		else:
			longitude_matches = (longitude >= west) & (longitude <= east)
		rows = (
			frappe.qb.from_(Camera)
			.select(Camera.name, Camera.area, Camera.status, Camera.latitude, Camera.longitude)
			.where((Camera.status == "Active") & (Camera.name != self.camera))
			.where((latitude >= max(-90, lat - lat_delta)) & (latitude <= min(90, lat + lat_delta)))
			.where(longitude_matches)
			.orderby(Camera.name)
			.limit(500)
			.run(as_dict=True)
		)
		for row in rows:
			try:
				distance = haversine_m(lat, lon, float(row.latitude), float(row.longitude))
			except (TypeError, ValueError):
				continue
			if distance > radius:
				continue
			bearing = bearing_degrees(lat, lon, float(row.latitude), float(row.longitude))
			self.append(
				"nearby_cameras",
				{
					"camera": row.name,
					"distance_m": round(distance, 1),
					"bearing_deg": round(bearing, 1),
					"bearing_compass": compass_8(bearing),
					"area": row.area,
					"camera_status": row.status,
				},
			)
