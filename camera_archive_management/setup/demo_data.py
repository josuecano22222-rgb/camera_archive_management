"""Explicit, synthetic-only map scenario requiring an authorized operator opt-in."""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.utils import add_to_date, now_datetime
from frappe.utils.file_manager import save_file

from camera_archive_management.geo.geometry import bearing_degrees, compass_8, haversine_m
from camera_archive_management.setup.seed import seed_core_reference_data

_SCENARIO = "CAM-MAP-V1-DEMO"
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
_CAMERAS = [
	("West Canal Overview", "52.3747123", "4.8835127", "PTZ"),
	("Museum Quarter North", "52.3599128", "4.8868124", "Dome"),
	("Museum Quarter South", "52.3535126", "4.8872129", "Fixed"),
	("Central Station West", "52.3782125", "4.8973122", "ANPR"),
	("Central Station East", "52.3788127", "4.9052128", "PTZ"),
	("Riverfront Promenade", "52.3679124", "4.9113126", "Bullet"),
	("Eastern Canal Junction", "52.3658129", "4.9210123", "Thermal"),
	("Market Square South", "52.3720126", "4.8908127", "Dome"),
	("Market Square North", "52.3767128", "4.8910125", "Fixed"),
	("Harbor Approach", "52.3900124", "4.9002128", "Multi-sensor"),
	("University Quarter", "52.3550127", "4.9550124", "PTZ"),
	("Parkway Crossing", "52.3478126", "4.8698123", "ANPR"),
]
_AREAS = (
	"DEMO · Canal District",
	"DEMO · Museum Quarter",
	"DEMO · Central Transit",
	"DEMO · East Waterfront",
)
_VEHICLE_TYPES = (
	("DEMO · Passenger car", "sedan.png"),
	("DEMO · Delivery van", "van.png"),
	("DEMO · City bus", "bus.png"),
	("DEMO · Cargo bicycle", "bike.png"),
)
_VEHICLES = [
	(0, "DEMO Vehicle 01", "DEMO-01", True),
	(0, "DEMO Vehicle 02", "DEMO-02", False),
	(1, "DEMO Delivery Van", "DEMO-V1", True),
	(2, "DEMO City Bus", "DEMO-B1", False),
	(1, "DEMO Freight Van", "DEMO-T1", True),
	(0, "DEMO Response Car", "DEMO-E1", False),
	(3, "DEMO Cargo Bicycle", "DEMO-C1", True),
	(2, "DEMO Shuttle Bus", "DEMO-B2", False),
]


def _guard_demo_generation() -> str | None:
	"""Require an explicit site opt-in and operator permission; never seed implicitly."""
	if frappe.conf.get("camera_archive_allow_demo_data") is not True:
		return "Demo generation is disabled. Explicitly set camera_archive_allow_demo_data=true to run it."
	if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
		return "Only System Managers may generate the synthetic map scenario."
	return None


def _demo_record_names(doctype: str) -> list[str]:
	"""Find tagged records, plus exact area/type fixtures whose marker may be unavailable."""
	names = set(
		frappe.get_all(
			doctype,
			filters={"demo_scenario": _SCENARIO},
			pluck="name",
			limit_page_length=0,
		)
	)
	known_names = {
		"Camera Area": _AREAS,
		"Vehicle Type": tuple(type_name for type_name, _ in _VEHICLE_TYPES),
	}.get(doctype, ())
	if known_names:
		rows = frappe.get_all(
			doctype,
			filters={"name": ["in", known_names]},
			fields=["name", "description", "is_demo_record"],
			limit_page_length=0,
		)
		names.update(
			row.name
			for row in rows
			if row.is_demo_record or _SCENARIO in (row.description or "")
		)
	return sorted(names)


def _existing_counts() -> dict[str, int]:
	return {
		"cameras": frappe.db.count("Camera", {"demo_scenario": _SCENARIO}),
		"camera_areas": len(_demo_record_names("Camera Area")),
		"vehicles": frappe.db.count("CAM Vehicle", {"demo_scenario": _SCENARIO}),
		"vehicle_types": len(_demo_record_names("Vehicle Type")),
		"events": frappe.db.count("Motion Event", {"demo_scenario": _SCENARIO}),
	}


def _attach_image(doctype: str, doc, path: Path, filename: str):
	if not path.is_file():
		frappe.throw(f"Bundled synthetic demo image is missing: {path.name}", frappe.ValidationError)
	return save_file(filename, path.read_bytes(), doctype, doc.name, is_private=0)


def _create_vehicle_types() -> list:
	created = []
	for type_name, image_name in _VEHICLE_TYPES:
		vehicle_type = frappe.get_doc({
			"doctype": "Vehicle Type",
			"type_name": type_name,
			"description": f"Synthetic map-test classification for {_SCENARIO}; not operational reference data.",
			"is_active": 1,
			"is_demo_record": 1,
			"demo_scenario": _SCENARIO,
		})
		vehicle_type.insert(ignore_permissions=True)
		image = _attach_image(
			"Vehicle Type",
			vehicle_type,
			_DATA_ROOT / "demo_vehicle_images" / image_name,
			f"{_SCENARIO.lower()}_type_{image_name}",
		)
		vehicle_type.vehicle_type_image = image.file_url
		vehicle_type.save(ignore_permissions=True)
		created.append(vehicle_type)
	return created


def _nearby_camera_context(camera, all_cameras: list) -> list[dict]:
	"""Provide deterministic, useful synthetic proximity rows independent of site alert settings."""
	origin = (float(camera.latitude), float(camera.longitude))
	nearby = []
	for other in all_cameras:
		if other.name == camera.name:
			continue
		target = (float(other.latitude), float(other.longitude))
		distance = haversine_m(*origin, *target)
		nearby.append((distance, other, bearing_degrees(*origin, *target)))
	nearby.sort(key=lambda item: (item[0], item[1].name))
	return [
		{
			"camera": other.name,
			"distance_m": round(distance, 1),
			"bearing_deg": round(bearing, 1),
			"bearing_compass": compass_8(bearing),
			"area": other.area,
			"camera_status": other.status,
		}
		for distance, other, bearing in nearby[:4]
	]


def create_demo_scenario() -> dict[str, int | str | bool]:
	"""Create a fictional, image-rich Amsterdam scenario for map, track and report testing.

	Requires ``camera_archive_allow_demo_data=True`` and an Administrator or
	System Manager. All records and attachments are scenario-tagged, and are
	never created by install or migrate.
	"""
	blocked = _guard_demo_generation()
	if blocked:
		return {"scenario": _SCENARIO, "created": False, "reason": blocked}
	existing = _existing_counts()
	expected = {
		"cameras": len(_CAMERAS),
		"camera_areas": len(_AREAS),
		"vehicles": len(_VEHICLES),
		"vehicle_types": len(_VEHICLE_TYPES),
		"events": 72,
	}
	if any(existing.values()):
		if existing == expected:
			return {"scenario": _SCENARIO, "created": False, **existing}
		return {
			"scenario": _SCENARIO,
			"created": False,
			"reason": f"Scenario {_SCENARIO} is partially present; delete its tagged records before regenerating.",
		}

	seed_core_reference_data()
	areas = []
	for area_name in _AREAS:
		area = frappe.get_doc({
			"doctype": "Camera Area",
			"area_name": area_name,
			"is_group": 0,
			"description": f"Synthetic filter-test area for scenario {_SCENARIO}.",
			"is_demo_record": 1,
			"demo_scenario": _SCENARIO,
		})
		area.insert(ignore_permissions=True)
		areas.append(area)

	created_cameras = []
	for index, (label, latitude, longitude, camera_type) in enumerate(_CAMERAS):
		camera = frappe.get_doc({
			"doctype": "Camera",
			"naming_series": "CAM-.####",
			"camera_name": f"DEMO · {label}",
			"status": "Active",
			"camera_type": camera_type,
			"importance": ("High", "Medium", "Critical", "Low")[index % 4],
			"area": areas[index % len(areas)].name,
			"address": "SYNTHETIC DEMO DATA — fictional location; not a real camera or address.",
			"latitude": latitude,
			"longitude": longitude,
			"location": f'{{"type":"Point","coordinates":[{longitude},{latitude}]}}',
			"description": f"Synthetic demonstration record in scenario {_SCENARIO}; safe to delete as a group.",
			"is_demo_record": 1,
			"demo_scenario": _SCENARIO,
		})
		camera.insert(ignore_permissions=True)
		first_index = index
		second_index = (index + 5) % len(_CAMERAS)
		gallery = []
		for order, source_index in enumerate((first_index, second_index)):
			asset = _DATA_ROOT / "demo_camera_images" / f"camera_{source_index + 1:02d}.png"
			file_doc = _attach_image(
				"Camera",
				camera,
				asset,
				f"{_SCENARIO.lower()}_camera_{index + 1:02d}_photo_{order + 1}.png",
			)
			gallery.append({
				"url": file_doc.file_url,
				"caption": f"Synthetic illustrated view {order + 1}: {label}",
				"description": "Bundled fictional illustration; not a photograph or real surveillance footage.",
				"is_primary": order == 0,
				"sort_order": order,
			})
		camera.camera_photos_json = json.dumps(gallery, ensure_ascii=False, separators=(",", ":"))
		camera.save(ignore_permissions=True)
		created_cameras.append(camera)

	created_types = _create_vehicle_types()
	created_vehicles = []
	for index, (type_index, name, number, has_primary_image) in enumerate(_VEHICLES):
		vehicle_type = created_types[type_index]
		vehicle = frappe.get_doc({
			"doctype": "CAM Vehicle",
			"naming_series": "CAM-VEH-.####",
			"vehicle_name": name,
			"vehicle_number": number,
			"vehicle_type": vehicle_type.name,
			"status": "Active",
			"description": f"Synthetic map replay asset from scenario {_SCENARIO}; not a real vehicle.",
			"is_demo_record": 1,
			"demo_scenario": _SCENARIO,
		})
		vehicle.insert(ignore_permissions=True)
		if has_primary_image:
			image_name = _VEHICLE_TYPES[type_index][1]
			asset = _DATA_ROOT / "demo_vehicle_images" / image_name
			image = _attach_image(
				"CAM Vehicle",
				vehicle,
				asset,
				f"{_SCENARIO.lower()}_vehicle_{index + 1:02d}_{image_name}",
			)
			vehicle.vehicle_image = image.file_url
			vehicle.save(ignore_permissions=True)
		created_vehicles.append(vehicle)

	base_time = add_to_date(now_datetime(), minutes=-5)
	event_count = 0
	for vehicle_index, vehicle in enumerate(created_vehicles):
		for step in range(9):
			event_index = vehicle_index * 9 + step
			camera_index = (vehicle_index * 2 + step * (1 + vehicle_index % 3) + step // 3) % len(created_cameras)
			camera = created_cameras[camera_index]
			event = frappe.get_doc({
				"doctype": "Motion Event",
				"naming_series": "MOT-.#####",
				"camera": camera.name,
				"motion_type": "Entry" if step % 2 == 0 else "Exit",
				"detected_at": add_to_date(base_time, minutes=-(71 - event_index) * 11),
				"vehicle": vehicle.name,
				"importance": ("Low", "Medium", "High", "Critical")[event_index % 4],
				"notes": (
					f"SYNTHETIC DEMO EVENT {event_index + 1:03d} — generated for map filters and route playback; "
					"not an incident."
				),
				"nearby_cameras": _nearby_camera_context(camera, created_cameras),
				"is_demo_record": 1,
				"demo_scenario": _SCENARIO,
			})
			event.insert(ignore_permissions=True)
			event_count += 1
	return {
		"scenario": _SCENARIO,
		"created": True,
		"cameras": len(created_cameras),
		"camera_areas": len(areas),
		"vehicle_types": len(created_types),
		"vehicles": len(created_vehicles),
		"events": event_count,
	}


def _delete_attached_files(doctype: str, docname: str) -> None:
	for file_name in frappe.get_all(
		"File",
		filters={"attached_to_doctype": doctype, "attached_to_name": docname},
		pluck="name",
		limit_page_length=0,
	):
		frappe.delete_doc("File", file_name, ignore_permissions=True, force=True)


def delete_demo_scenario() -> dict[str, int | str | bool]:
	"""Remove only scenario-tagged records and files, in dependency-safe order."""
	blocked = _guard_demo_generation()
	if blocked:
		return {"deleted": False, "reason": blocked}
	counts = _existing_counts()
	retained_links = {"camera_areas": 0, "vehicle_types": 0}
	for doctype in ("Motion Event", "Camera", "CAM Vehicle", "Camera Area", "Vehicle Type"):
		names = _demo_record_names(doctype)
		for name in names:
			if doctype == "Camera Area" and frappe.db.exists("Camera", {"area": name}):
				retained_links["camera_areas"] += 1
				continue
			if doctype == "Vehicle Type" and frappe.db.exists("CAM Vehicle", {"vehicle_type": name}):
				retained_links["vehicle_types"] += 1
				continue
			if doctype in {"Camera", "CAM Vehicle", "Vehicle Type"}:
				_delete_attached_files(doctype, name)
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
	return {"deleted": True, "scenario": _SCENARIO, **counts, **retained_links}
