"""Install additive, app-owned reference catalogs without overwriting site customizations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import frappe

from camera_archive_management.geo.geometry import geometry_bounds

_APP_ROOT = Path(__file__).parents[1]
_REFERENCE_PATH = _APP_ROOT / "data" / "core_reference_data.json"
_COUNTRIES_PATH = _APP_ROOT / "data" / "natural_earth_admin0_countries.geojson"
_COUNTRY_DATASET_ID = "natural-earth-admin0-110m"
_COUNTRY_DATASET_VERSION = "ca96624a56bd078437bca8184e78163e5039ad19"
_COUNTRY_DATA_SHA256 = "b587b32dc343c5896752d472f637bb050c8b8eccfbc7e5c8af72ada3072ac226"
_COUNTRY_SOURCE = (
	"https://github.com/nvkelso/natural-earth-vector/blob/"
	f"{_COUNTRY_DATASET_VERSION}/geojson/ne_110m_admin_0_countries.geojson"
)
_COUNTRY_LICENSE = "Public Domain"
_COUNTRY_ATTRIBUTION = (
	"Natural Earth 1:110m Admin 0; public domain. Generalized map, not legal boundaries or sovereignty. "
	f"Revision {_COUNTRY_DATASET_VERSION[:12]}."
)


def _seed_classifications() -> dict[str, int]:
	if not _REFERENCE_PATH.is_file():
		frappe.throw("The Camera Archive core reference catalog is missing.", frappe.ValidationError)
	catalog = json.loads(_REFERENCE_PATH.read_text(encoding="utf-8"))
	created = {"camera_types": 0, "vehicle_types": 0}
	for doctype, key in (("Camera Type", "camera_types"), ("Vehicle Type", "vehicle_types")):
		for row in catalog[key]:
			name = row["type_name"]
			if frappe.db.exists(doctype, name):
				continue
			doc = frappe.get_doc({
				"doctype": doctype,
				"type_name": name,
				"description": row["description"],
				"is_active": 1,
			})
			doc.insert(ignore_permissions=True)
			created[key] += 1
	return created


def _seed_world_country_boundaries() -> dict[str, int]:
	if not _COUNTRIES_PATH.is_file():
		frappe.throw("The bundled Natural Earth core boundary dataset is missing.", frappe.ValidationError)
	raw = _COUNTRIES_PATH.read_bytes()
	if hashlib.sha256(raw).hexdigest() != _COUNTRY_DATA_SHA256:
		frappe.throw("The bundled Natural Earth dataset failed its integrity check.", frappe.ValidationError)
	payload = json.loads(raw.decode("utf-8"))
	features = payload.get("features") if isinstance(payload, dict) else None
	if not isinstance(features, list):
		frappe.throw("The bundled Natural Earth core boundary dataset is invalid.", frappe.ValidationError)
	codes = []
	for feature in features:
		properties = feature.get("properties") if isinstance(feature, dict) else None
		if not isinstance(properties, dict):
			frappe.throw("The bundled Natural Earth core boundary dataset is invalid.", frappe.ValidationError)
		codes.append(properties.get("boundary_code"))
	if len(features) != 177 or len(codes) != len(set(codes)) or any(not code for code in codes):
		frappe.throw("The bundled Natural Earth core boundary dataset is invalid.", frappe.ValidationError)

	dataset_name = frappe.db.get_value("Geo Dataset", {"dataset_id": _COUNTRY_DATASET_ID}, "name")
	created_dataset = 0
	if dataset_name:
		dataset = frappe.get_doc("Geo Dataset", dataset_name)
		if dataset.source != _COUNTRY_SOURCE or dataset.license_id != _COUNTRY_LICENSE:
			frappe.throw(
				f"Dataset ID {_COUNTRY_DATASET_ID} already belongs to a different source; refusing to replace it.",
				frappe.ValidationError,
			)
	else:
		dataset = frappe.get_doc({
			"doctype": "Geo Dataset",
			"dataset_id": _COUNTRY_DATASET_ID,
			"label": "Natural Earth — World Countries (1:110m)",
			"version": _COUNTRY_DATASET_VERSION,
			"source": _COUNTRY_SOURCE,
			"license_id": _COUNTRY_LICENSE,
			"attribution": _COUNTRY_ATTRIBUTION,
			"west": "-180",
			"south": "-90",
			"east": "180",
			"north": "90",
			"import_status": "Complete",
			"import_progress": 100,
			"feature_count": len(features),
			"index_version": 1,
			"last_imported_at": frappe.utils.now_datetime(),
		})
		dataset.flags.job_update = True
		dataset.insert(ignore_permissions=True)
		dataset_name = dataset.name
		created_dataset = 1

	created_boundaries = 0
	for feature in features:
		properties = feature.get("properties") or {}
		code = properties.get("boundary_code")
		label = properties.get("label")
		geometry = feature.get("geometry")
		if not isinstance(code, str) or not code or not isinstance(label, str) or not label:
			frappe.throw("A bundled world boundary has no stable code or label.", frappe.ValidationError)
		if frappe.db.exists("Geo Boundary", {"dataset": dataset_name, "boundary_code": code}):
			continue
		west, south, east, north = geometry_bounds(geometry)
		doc = frappe.get_doc({
			"doctype": "Geo Boundary",
			"dataset": dataset_name,
			"boundary_code": code,
			"label": label,
			"level": 0,
			"source_id": properties.get("source_id") or code,
			"source_kind": "Imported",
			"west": str(west),
			"south": str(south),
			"east": str(east),
			"north": str(north),
			"geometries": [{
				"geometry_role": "Resolution",
				"geojson": json.dumps(geometry, separators=(",", ":"), allow_nan=False),
				"srid": 4326,
			}],
		})
		doc.flags.prevalidated_dataset_links = True
		doc.flags.prevalidated_boundary_code = True
		doc.insert(ignore_permissions=True)
		created_boundaries += 1

	settings = frappe.get_single("CAM Geo Settings")
	if not settings.active_dataset:
		settings.active_dataset = dataset_name
		settings.save(ignore_permissions=True)
	return {
		"datasets": created_dataset,
		"country_boundaries": created_boundaries,
		"expected_country_boundaries": len(features),
	}


def seed_core_reference_data() -> dict[str, int]:
	"""Create missing classifications and global coarse country boundaries.

	Existing classifications, Geo Dataset metadata, boundaries, and active dataset
	selection are never overwritten. Country polygons are bundled from a pinned,
	public-domain Natural Earth revision and are cartographic, not legal borders.
	"""
	created = _seed_classifications()
	created.update(_seed_world_country_boundaries())
	return created
