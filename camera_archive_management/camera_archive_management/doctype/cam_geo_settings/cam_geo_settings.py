from __future__ import annotations

import frappe
from frappe.model.document import Document


class CAMGeoSettings(Document):
	def validate(self) -> None:
		if self.online_provider not in {"Disabled", "Nominatim (OpenStreetMap)"}:
			frappe.throw("Unsupported external geocoder provider.", frappe.ValidationError)
		if self.enable_online_geocoder and self.online_provider == "Disabled":
			frappe.throw("Choose a provider before enabling online geocoding.", frappe.ValidationError)
		user_agent = (self.online_user_agent or "").strip()
		if self.enable_online_geocoder and not user_agent:
			frappe.throw(
				"Provide a contact-bearing User-Agent before enabling Nominatim.", frappe.ValidationError
			)
		if user_agent and (
			len(user_agent) > 250
			or any(char in user_agent for char in "\r\n")
			or not ("@" in user_agent or "https://" in user_agent.lower())
		):
			frappe.throw(
				"User-Agent must be a single-line contact email or HTTPS contact URL (max 250 chars).",
				frappe.ValidationError,
			)
		if self.online_rate_limit_per_min is not None and not 1 <= int(self.online_rate_limit_per_min) <= 60:
			frappe.throw(
				"Online geocoder rate limit must be between 1 and 60 per minute.", frappe.ValidationError
			)
		if self.default_search_radius_m is not None and not 1 <= int(self.default_search_radius_m) <= 100000:
			frappe.throw("Default search radius must be between 1 and 100000 meters.", frappe.ValidationError)
		if int(self.allow_tile_cache_write or 0) and not int(self.enable_online_tile_fetch or 0):
			frappe.throw("Enable online tile fetching before allowing shared cache writes.", frappe.ValidationError)
		for fieldname, label in (
			("tile_connect_timeout_seconds", "Tile connect timeout"),
			("tile_read_timeout_seconds", "Tile read timeout"),
		):
			value = getattr(self, fieldname, None)
			if value is not None and not 1 <= int(value) <= 5:
				frappe.throw(f"{label} must be between 1 and 5 seconds.", frappe.ValidationError)
		if self.nearby_camera_radius is not None and not 0 <= int(self.nearby_camera_radius) <= 100_000:
			frappe.throw("Nearby-camera radius must be between 0 and 100000 meters.", frappe.ValidationError)
