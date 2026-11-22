from __future__ import annotations

import frappe
from frappe.model.document import Document


class MotionEventNearbyCamera(Document):
	def validate(self) -> None:
		if self.distance_m is not None and float(self.distance_m) < 0:
			frappe.throw("Nearby-camera distance cannot be negative.", frappe.ValidationError)
		if self.bearing_deg is not None and not 0 <= float(self.bearing_deg) < 360:
			frappe.throw("Bearing must be in the range [0, 360).", frappe.ValidationError)
