from __future__ import annotations

import hashlib
import json

import frappe

from camera_archive_management.geo.coordinates import validate_pair
from camera_archive_management.geo.online import reverse_lookup
from camera_archive_management.geo.resolver import resolve_point


def _strict_flag(value, name: str) -> bool:
	if value in (True, 1, "1"):
		return True
	if value in (False, 0, "0", None, ""):
		return False
	frappe.throw(f"{name} must be 0 or 1.", frappe.ValidationError)


def _require_read_access(dataset: str | None) -> None:
	if dataset and not frappe.has_permission("Geo Dataset", "read", dataset):
		frappe.throw(
			"You do not have permission to read the requested geographic dataset.", frappe.PermissionError
		)
	if not dataset and not frappe.has_permission("Geo Dataset", "read"):
		frappe.throw("You do not have permission to use geographic lookup.", frappe.PermissionError)


@frappe.whitelist(methods=["GET", "POST"])
def resolve_coordinates(latitude=None, longitude=None, dataset=None, radius_m=None, allow_external=0):
	"""Resolve one point locally; external lookup is opt-in both in settings and request."""
	try:
		lat, lon = validate_pair(latitude, longitude)
	except ValueError as exc:
		frappe.throw(str(exc), frappe.ValidationError)
	if lat is None or lon is None:
		frappe.throw("Latitude and longitude are required.", frappe.ValidationError)
	allow_external = _strict_flag(allow_external, "allow_external")
	if allow_external and getattr(frappe.request, "method", "POST") != "POST":
		frappe.throw("External geocoding requires a POST request.", frappe.PermissionError)
	_require_read_access(dataset)
	result = resolve_point(lat, lon, dataset=dataset, radius_m=radius_m)
	if result.get("provenance") in {"no_local_match", "local_gazetteer"} and allow_external:
		external = reverse_lookup(float(lat), float(lon))
		if external:
			result["external_result"] = external
			if result.get("provenance") == "no_local_match":
				result["provenance"] = "external_provider"
				result["confidence"] = external["confidence"]
	return result


@frappe.whitelist(methods=["POST"])
def queue_camera_resolution(camera_names, dataset=None, overwrite=0):
	"""Enqueue a bounded bulk resolution job; only Geo Admin/System Manager may write matches."""
	overwrite = _strict_flag(overwrite, "overwrite")
	if not frappe.has_permission("CAM Geo Settings", "write"):
		frappe.throw("Only Geo Administrators may queue bulk location updates.", frappe.PermissionError)
	if isinstance(camera_names, str):
		try:
			camera_names = json.loads(camera_names)
		except json.JSONDecodeError:
			frappe.throw("camera_names must be a JSON array.", frappe.ValidationError)
	if not isinstance(camera_names, list) or not 1 <= len(camera_names) <= 250:
		frappe.throw("Provide between 1 and 250 camera names.", frappe.ValidationError)
	if any(not isinstance(name, str) or not name or len(name) > 140 for name in camera_names):
		frappe.throw(
			"Every camera name must be a non-empty string of at most 140 characters.", frappe.ValidationError
		)
	if len(set(camera_names)) != len(camera_names):
		frappe.throw("Duplicate camera names are not allowed.", frappe.ValidationError)
	for name in camera_names:
		if not frappe.has_permission("Camera", "write", name):
			frappe.throw(f"No write permission for Camera {name}.", frappe.PermissionError)
	job_material = json.dumps([sorted(camera_names), dataset or "", overwrite], separators=(",", ":"))
	job_key = hashlib.sha256(job_material.encode("utf-8")).hexdigest()[:20]
	frappe.enqueue(
		"camera_archive_management.jobs.geo.resolve_camera_batch",
		queue="long",
		camera_names=camera_names,
		dataset=dataset,
		overwrite=overwrite,
		requested_by=frappe.session.user,
		job_id=f"cam-camera-resolve-{job_key}",
		deduplicate=True,
		enqueue_after_commit=True,
	)
	return {"queued": True, "count": len(camera_names), "job_id": f"cam-camera-resolve-{job_key}"}


@frappe.whitelist(methods=["POST"])
def queue_geo_dataset_import(dataset_name):
	if not isinstance(dataset_name, str) or len(dataset_name) > 140:
		frappe.throw("Invalid dataset name.", frappe.ValidationError)
	if not frappe.has_permission("Geo Dataset", "write", dataset_name):
		frappe.throw("Only Geo Administrators may import geographic datasets.", frappe.PermissionError)
	doc = frappe.get_doc("Geo Dataset", dataset_name)
	if not doc.source_file:
		frappe.throw("Attach a private GeoJSON FeatureCollection before importing.", frappe.ValidationError)
	doc.import_status = "Queued"
	doc.import_progress = 0
	doc.import_error = None
	doc.save()
	return {"queued": True, "dataset": doc.name}


@frappe.whitelist(methods=["POST"])
def queue_archive_ingest(batch_name):
	if not isinstance(batch_name, str) or len(batch_name) > 140:
		frappe.throw("Invalid ingest batch name.", frappe.ValidationError)
	if not frappe.has_permission("Archive Ingest Batch", "write", batch_name):
		frappe.throw("Only Archive Managers may queue ingest batches.", frappe.PermissionError)
	doc = frappe.get_doc("Archive Ingest Batch", batch_name)
	if doc.status not in {"Draft", "Failed", "Queued"}:
		frappe.throw("Only Draft, Failed, or already Queued batches may be queued.", frappe.ValidationError)
	doc.status = "Queued"
	doc.queued_by = frappe.session.user
	doc.error_log = None
	doc.save()
	return {"queued": True, "batch": doc.name}
