from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestCAMVehicle(FrappeTestCase):
    def test_cam_vehicle_uses_collision_safe_series(self):
        vehicle = frappe.get_doc(
            {
                "doctype": "CAM Vehicle",
                "naming_series": "CAM-VEH-.####",
                "vehicle_name": "Collision-safe test vehicle",
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        self.assertTrue(vehicle.name.startswith("CAM-VEH-"))
