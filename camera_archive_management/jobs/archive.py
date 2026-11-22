"""Background workers for manifest-driven archive metadata ingest and indexing."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import frappe

MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_ASSETS_PER_BATCH = 1000
_ITEM_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ALLOWED_ITEM_FIELDS = {
	"item_key",
	"title",
	"camera",
	"motion_event",
	"storage_backend",
	"file_url",
	"external_reference",
	"external_storage_scope",
	"checksum_sha256",
	"size_bytes",
	"media_type",
	"recorded_from",
	"recorded_to",
	"retention_state",
	"metadata_json",
}


def _load_manifest(batch) -> dict:
	if batch.manifest_json:
		raw = batch.manifest_json.encode("utf-8")
	else:
		file_name = frappe.db.get_value("File", {"file_url": batch.source_manifest}, "name")
		if not file_name:
			frappe.throw("Ingest manifest is not registered as a Frappe File.", frappe.ValidationError)
		file_doc = frappe.get_doc("File", file_name)
		if not file_doc.is_private:
			frappe.throw("Ingest manifest attachment must be private.", frappe.ValidationError)
		if int(file_doc.file_size or 0) > MAX_MANIFEST_BYTES:
			frappe.throw("Ingest manifest exceeds the 2 MiB limit.", frappe.ValidationError)
		raw = file_doc.get_content()
		if isinstance(raw, str):
			raw = raw.encode("utf-8")
	if len(raw) > MAX_MANIFEST_BYTES:
		frappe.throw("Ingest manifest exceeds the 2 MiB limit.", frappe.ValidationError)
	try:
		payload = json.loads(raw.decode("utf-8"))
	except (UnicodeDecodeError, json.JSONDecodeError) as exc:
		frappe.throw(f"Ingest manifest is not valid UTF-8 JSON: {exc}", frappe.ValidationError)
	if not isinstance(payload, dict) or not isinstance(payload.get("assets"), list):
		frappe.throw("Manifest must contain an assets array.", frappe.ValidationError)
	if len(payload["assets"]) > MAX_ASSETS_PER_BATCH:
		frappe.throw(f"A batch may contain at most {MAX_ASSETS_PER_BATCH} assets.", frappe.ValidationError)
	return payload


def _validate_item(item: object, batch_name: str) -> dict:
	if not isinstance(item, dict):
		frappe.throw("Each manifest asset must be an object.", frappe.ValidationError)
	unknown = set(item) - _ALLOWED_ITEM_FIELDS
	if unknown:
		frappe.throw(f"Unsupported manifest fields: {', '.join(sorted(unknown))}.", frappe.ValidationError)
	key = item.get("item_key")
	if not isinstance(key, str) or not _ITEM_KEY.fullmatch(key):
		frappe.throw("Each asset requires a safe item_key.", frappe.ValidationError)
	if not isinstance(item.get("title"), str) or not item["title"].strip():
		frappe.throw("Each asset requires a title.", frappe.ValidationError)
	if not isinstance(item.get("camera"), str) or not item["camera"]:
		frappe.throw("Each asset must reference an existing Camera.", frappe.ValidationError)
	if item.get("motion_event") and not isinstance(item["motion_event"], str):
		frappe.throw("motion_event must be a document name.", frappe.ValidationError)
	if item.get("metadata_json"):
		metadata = item["metadata_json"]
		if isinstance(metadata, str):
			if len(metadata.encode("utf-8")) > 64 * 1024:
				frappe.throw("Per-asset metadata exceeds 64 KiB.", frappe.ValidationError)
			try:
				metadata = json.loads(metadata)
			except json.JSONDecodeError:
				frappe.throw("metadata_json must contain valid JSON.", frappe.ValidationError)
		if not isinstance(metadata, dict):
			frappe.throw("metadata_json must be a JSON object.", frappe.ValidationError)
		item = dict(item)
		item["metadata_json"] = json.dumps(metadata, sort_keys=True, ensure_ascii=False)
	else:
		item = dict(item)
	item["ingest_batch"] = batch_name
	item["ingest_item_key"] = key
	return item


def process_ingest_batch(batch_name: str) -> None:
	"""Validate and create Archive Asset metadata; media bytes are never imported."""
	if not isinstance(batch_name, str) or len(batch_name) > 140:
		frappe.throw("Invalid ingest batch name.", frappe.ValidationError)
	batch = frappe.get_doc("Archive Ingest Batch", batch_name)
	if batch.status == "Complete":
		return
	if batch.status not in {"Queued", "Running"}:
		return
	batch.status = "Running"
	batch.started_at = frappe.utils.now_datetime()
	batch.error_log = None
	batch.flags.worker_update = True
	batch.save(ignore_permissions=True)
	savepoint = "cam_ingest_process"
	frappe.db.savepoint(savepoint)
	try:
		manifest = _load_manifest(batch)
		items = [_validate_item(item, batch.name) for item in manifest["assets"]]
		keys = [item["ingest_item_key"] for item in items]
		if len(keys) != len(set(keys)):
			frappe.throw("Manifest contains duplicate item_key values.", frappe.ValidationError)

		camera_names = sorted({item["camera"] for item in items})
		known_cameras = (
			{
				row.name
				for row in frappe.get_all(
					"Camera",
					filters={"name": ["in", camera_names]},
					fields=["name"],
					order_by="name asc",
					limit_page_length=MAX_ASSETS_PER_BATCH,
				)
			}
			if camera_names
			else set()
		)
		missing_cameras = set(camera_names) - known_cameras
		if missing_cameras:
			frappe.throw(
				f"Manifest references unknown cameras: {sorted(missing_cameras)!r}", frappe.ValidationError
			)

		event_names = sorted({item["motion_event"] for item in items if item.get("motion_event")})
		known_events = (
			{
				row.name
				for row in frappe.get_all(
					"Motion Event",
					filters={"name": ["in", event_names]},
					fields=["name"],
					order_by="name asc",
					limit_page_length=MAX_ASSETS_PER_BATCH,
				)
			}
			if event_names
			else set()
		)
		missing_events = set(event_names) - known_events
		if missing_events:
			frappe.throw(
				f"Manifest references unknown Motion Events: {sorted(missing_events)!r}",
				frappe.ValidationError,
			)

		file_urls = sorted({item["file_url"] for item in items if item.get("file_url")})
		file_records = (
			frappe.get_all(
				"File",
				filters={"file_url": ["in", file_urls]},
				fields=["file_url", "is_private"],
				order_by="file_url asc",
				limit_page_length=MAX_ASSETS_PER_BATCH,
			)
			if file_urls
			else []
		)
		file_matches = {}
		for row in file_records:
			file_matches.setdefault(row.file_url, []).append(bool(row.is_private))
		private_files = {
			url: len(file_matches.get(url, [])) == 1 and file_matches[url][0] for url in file_urls
		}
		if any(not private_files.get(url, False) for url in file_urls):
			frappe.throw(
				"Every Frappe File asset must reference an existing private File.", frappe.ValidationError
			)

		existing_rows = frappe.get_all(
			"Archive Asset",
			filters={"ingest_batch": batch.name},
			fields=["ingest_item_key"],
			order_by="ingest_item_key asc",
			limit_page_length=MAX_ASSETS_PER_BATCH + 1,
		)
		existing = {row.ingest_item_key for row in existing_rows if row.ingest_item_key}
		processed = 0
		previous_worker_flag = frappe.flags.get("cam_archive_ingest_worker", False)
		frappe.flags.cam_archive_ingest_worker = True
		try:
			for item in items:
				if item["ingest_item_key"] in existing:
					processed += 1
					continue
				item["index_status"] = "Queued"
				asset = frappe.get_doc({"doctype": "Archive Asset", **item})
				if item.get("file_url"):
					asset.flags.prevalidated_private_file = private_files[item["file_url"]]
				asset.insert(ignore_permissions=True)
				existing.add(item["ingest_item_key"])
				processed += 1
		finally:
			frappe.flags.cam_archive_ingest_worker = previous_worker_flag
		batch = frappe.get_doc("Archive Ingest Batch", batch.name)
		batch.status = "Complete"
		batch.processed_count = processed
		batch.finished_at = frappe.utils.now_datetime()
		batch.flags.worker_update = True
		batch.save(ignore_permissions=True)
	except Exception as exc:
		frappe.db.rollback(save_point=savepoint)
		failed = frappe.get_doc("Archive Ingest Batch", batch_name)
		failed.status = "Failed"
		failed.finished_at = frappe.utils.now_datetime()
		failed.error_log = "Ingest failed; check server logs. Source data is intentionally omitted."
		failed.flags.worker_update = True
		failed.save(ignore_permissions=True)
		frappe.logger("camera_archive_management.archive").error(
			"Archive ingest failed for batch %s (%s)", batch_name, type(exc).__name__
		)


def _private_file_path(file_doc) -> Path:
	"""Resolve a Frappe File only under the current site's private/files root."""
	if not file_doc.is_private:
		frappe.throw("Archive Asset source file must be private.", frappe.ValidationError)
	private_root = Path(frappe.get_site_path("private", "files")).resolve(strict=True)
	raw_path = Path(file_doc.get_full_path())
	for component in (raw_path, *raw_path.parents):
		if component.is_symlink():
			frappe.throw("Symlinked archive files are not permitted.", frappe.ValidationError)
	resolved = raw_path.resolve(strict=True)
	try:
		resolved.relative_to(private_root)
	except ValueError:
		frappe.throw(
			"Archive file path is outside the site's private file directory.", frappe.ValidationError
		)
	if not resolved.is_file():
		frappe.throw("Archive File is not a regular file.", frappe.ValidationError)
	return resolved


def index_archive_asset(asset_name: str) -> None:
	"""Index stored-file metadata/checksum on a long queue without DB binary storage."""
	if not isinstance(asset_name, str) or len(asset_name) > 140:
		frappe.throw("Invalid Archive Asset name.", frappe.ValidationError)
	asset = frappe.get_doc("Archive Asset", asset_name)
	if asset.index_status == "Complete":
		return
	if asset.index_status not in {"Queued", "Running"}:
		return
	asset.index_status = "Running"
	asset.index_error = None
	asset.flags.worker_update = True
	asset.save(ignore_permissions=True)
	try:
		settings = frappe.get_single("Archive Settings")
		if asset.storage_backend == "External":
			if settings.require_archive_checksum and not asset.checksum_sha256:
				frappe.throw(
					"External archive reference requires a source-provided checksum.", frappe.ValidationError
				)
		else:
			file_name = frappe.db.get_value("File", {"file_url": asset.file_url}, "name")
			if not file_name:
				frappe.throw("Archive Asset File record is missing.", frappe.ValidationError)
			file_doc = frappe.get_doc("File", file_name)
			path = _private_file_path(file_doc)
			digest = hashlib.sha256()
			total_size = 0
			with path.open("rb") as stream:
				for block in iter(lambda: stream.read(1024 * 1024), b""):
					total_size += len(block)
					digest.update(block)
			asset.checksum_sha256 = digest.hexdigest()
			asset.size_bytes = total_size
			asset.media_type = asset.media_type or file_doc.file_type
		asset.index_status = "Complete"
		asset.index_error = None
		asset.flags.worker_update = True
		asset.save(ignore_permissions=True)
	except Exception as exc:
		failed = frappe.get_doc("Archive Asset", asset_name)
		failed.index_status = "Failed"
		failed.index_error = "Indexing failed; inspect server logs for details."
		failed.flags.worker_update = True
		failed.save(ignore_permissions=True)
		frappe.logger("camera_archive_management.archive").error(
			"Archive Asset indexing failed for %s (%s)", asset_name, type(exc).__name__
		)
