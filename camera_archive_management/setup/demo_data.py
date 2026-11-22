"""Explicit, synthetic-only map scenario for a non-production demonstration site."""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.utils import add_to_date, now_datetime
from frappe.utils.file_manager import save_file

from camera_archive_management.setup.seed import seed_core_reference_data

_SCENARIO = "CAM-MAP-V1-DEMO"
_CAMERAS = [
	("West Canal Overview", 52.3747, 4.8835, "PTZ"),
	("Museum Quarter North", 52.3599, 4.8868, "Dome"),
	("Museum Quarter South", 52.3535, 4.8872, "Fixed"),
	("Central Station West", 52.3782, 4.8973, "ANPR"),
	("Central Station East", 52.3788, 4.9052, "PTZ"),
	("Riverfront Promenade", 52.3679, 4.9113, "Bullet"),
	("Eastern Canal Junction", 52.3658, 4.9210, "Thermal"),
	("Market Square South", 52.3720, 4.8908, "Dome"),
	("Market Square North", 52.3767, 4.8910, "Fixed"),
	("Harbor Approach", 52.3900, 4.9002, "Multi-sensor"),
	("University Quarter", 52.3550, 4.9550, "PTZ"),
	("Parkway Crossing", 52.3478, 4.8698, "ANPR"),
]
_VEHICLES = [
	("Passenger car", "DEMO Vehicle 01", "DEMO-01"),
	("Passenger car", "DEMO Vehicle 02", "DEMO-02"),
	("Van", "DEMO Delivery Van", "DEMO-V1"),
	("Bus", "DEMO City Bus", "DEMO-B1"),
	("Truck", "DEMO Freight Truck", "DEMO-T1"),
	("Motorcycle", "DEMO Motorcycle", "DEMO-M1"),
	("Bicycle", "DEMO Cargo Bicycle", "DEMO-C1"),
	("Emergency vehicle", "DEMO Response Vehicle", "DEMO-E1"),
]


def _guard_non_production() -> None:
	if getattr(frappe.local, "site", None) == "frappe.com":
		frappe.throw("Synthetic map data is never allowed on the production site frappe.com.", frappe.PermissionError)
	if frappe.conf.get("camera_archive_allow_demo_data") is not True:
		frappe.throw(
			"Demo generation is disabled. Set camera_archive_allow_demo_data=true only on a disposable non-production site.",
			frappe.PermissionError,
		)
	if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
		frappe.throw("Only System Managers may generate the synthetic map scenario.", frappe.PermissionError)


def _existing_counts() -> dict[str, int]:
	return {
		"cameras": frappe.db.count("Camera", {"demo_scenario": _SCENARIO}),
		"vehicles": frappe.db.count("CAM Vehicle", {"demo_scenario": _SCENARIO}),
		"events": frappe.db.count("Motion Event", {"demo_scenario": _SCENARIO}),
	}


def create_demo_scenario() -> dict[str, int | str]:
	"""Create a clearly tagged, fictional Amsterdam map/replay scenario, idempotently.

	Run only on a disposable non-production site after explicitly setting
	``camera_archive_allow_demo_data=true`` in that site's config.
	"""
	_guard_non_production()
	existing = _existing_counts()
	if any(existing.values()):
		if existing == {"cameras": len(_CAMERAS), "vehicles": len(_VEHICLES), "events": 72}:
			return {"scenario": _SCENARIO, "created": False, **existing}
		frappe.throw(
			f"Scenario {_SCENARIO} is partially present; remove its tagged records before regenerating.",
			frappe.ValidationError,
		)
	seed_core_reference_data()
	created_cameras = []
	for index, (label, latitude, longitude, camera_type) in enumerate(_CAMERAS):
		camera = frappe.get_doc({
			"doctype": "Camera",
			"naming_series": "CAM-.####",
			"camera_name": f"DEMO · {label}",
			"status": "Active",
			"camera_type": camera_type,
			"importance": ("High", "Medium", "Critical", "Low")[index % 4],
			"address": "SYNTHETIC DEMO DATA — fictional location; not a real camera or address.",
			"latitude": f"{latitude:.6f}",
			"longitude": f"{longitude:.6f}",
			"location": json.dumps({"type": "Point", "coordinates": [longitude, latitude]}, separators=(",", ":")),
			"description": f"Synthetic demonstration record in scenario {_SCENARIO}; safe to delete as a group.",
			"is_demo_record": 1,
			"demo_scenario": _SCENARIO,
		})
		camera.insert(ignore_permissions=True)
		image_path = Path(__file__).resolve().parents[1] / "data" / "demo_camera_images" / f"camera_{index + 1:02d}.png"
		if not image_path.is_file():
			frappe.throw(f"Bundled synthetic demo image is missing: {image_path.name}", frappe.ValidationError)
		file_doc = save_file(
			image_path.name,
			image_path.read_bytes(),
			"Camera",
			camera.name,
			is_private=0,
		)
		camera.camera_photos_json = json.dumps(
			[
				{
					"url": file_doc.file_url,
					"caption": f"Synthetic illustration: {label}",
					"description": "Bundled fictional illustration; not a photograph or real surveillance footage.",
					"is_primary": True,
					"sort_order": 0,
				}
			],
			ensure_ascii=False,
			separators=(",", ":"),
		)
		camera.save(ignore_permissions=True)
		created_cameras.append(camera)

	created_vehicles = []
	for vehicle_type, name, number in _VEHICLES:
		vehicle = frappe.get_doc({
			"doctype": "CAM Vehicle",
			"naming_series": "CAM-VEH-.####",
			"vehicle_name": name,
			"vehicle_number": number,
			"vehicle_type": vehicle_type,
			"status": "Active",
			"description": f"Synthetic map replay asset from scenario {_SCENARIO}; not a real vehicle.",
			"is_demo_record": 1,
			"demo_scenario": _SCENARIO,
		})
		vehicle.insert(ignore_permissions=True)
		created_vehicles.append(vehicle)

	base_time = now_datetime()
	event_count = 0
	for index in range(72):
		camera = created_cameras[(index * 5 + index // 7) % len(created_cameras)]
		vehicle = created_vehicles[(index * 3 + index // 9) % len(created_vehicles)]
		motion_type = "Entry" if index % 2 == 0 else "Exit"
		event = frappe.get_doc({
			"doctype": "Motion Event",
			"naming_series": "MOT-.#####",
			"camera": camera.name,
			"motion_type": motion_type,
			"detected_at": add_to_date(base_time, days=-(index % 14), minutes=-(index * 11)),
			"vehicle": vehicle.name,
			"importance": ("Low", "Medium", "High", "Critical")[index % 4],
			"notes": f"SYNTHETIC DEMO EVENT {index + 1:03d} — generated for map filters and route playback; not an incident.",
			"is_demo_record": 1,
			"demo_scenario": _SCENARIO,
		})
		event.insert(ignore_permissions=True)
		event_count += 1
	return {
		"scenario": _SCENARIO,
		"created": True,
		"cameras": len(created_cameras),
		"vehicles": len(created_vehicles),
		"events": event_count,
	}


def delete_demo_scenario() -> dict[str, int]:
	"""Remove only this generator's records, in dependency-safe order."""
	_guard_non_production()
	counts = _existing_counts()
	for doctype in ("Motion Event", "Camera", "CAM Vehicle"):
		for name in frappe.get_all(doctype, filters={"demo_scenario": _SCENARIO}, pluck="name", limit_page_length=0):
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
	return counts
