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
