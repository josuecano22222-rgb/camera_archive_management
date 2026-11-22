"""Move Camera Photo child rows into Camera's embedded image gallery and retire the child DocType."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import PurePosixPath

import frappe

from camera_archive_management.utils.files import is_safe_frappe_file_url

LEGACY_DOCTYPE = "Camera Photo"
APP_NAME = "camera_archive_management"
_ALLOWED_IMAGE_SUFFIXES = {".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def _doctype_app(doctype: str) -> str | None:
	module = frappe.db.get_value("DocType", doctype, "module")
	return frappe.db.get_value("Module Def", module, "app_name") if module else None


def _assert_no_references() -> None:
	for child_doctype in ("DocField", "Custom Field"):
		for field in frappe.get_all(
			child_doctype,
			filters={"options": LEGACY_DOCTYPE},
			fields=["parent", "fieldname"],
			limit_page_length=0,
		):
			if field.parent != LEGACY_DOCTYPE:
				frappe.throw(
					f"Cannot remove {LEGACY_DOCTYPE}: {field.parent}.{field.fieldname} still references it.",
					frappe.ValidationError,
				)


def _file_map(urls: set[str]) -> dict[str, list]:
	if not urls:
		return {}
	rows = frappe.get_all(
		"File",
		filters={"file_url": ["in", sorted(urls)]},
		fields=["name", "file_url", "file_name", "attached_to_doctype", "attached_to_name", "attached_to_field"],
		limit_page_length=0,
	)
	result = defaultdict(list)
	for row in rows:
		result[row.file_url].append(row)
	return result


def _chunks(items: list[str], size: int):
	for offset in range(0, len(items), size):
		yield items[offset : offset + size]


def execute() -> None:
	"""Preserve image metadata and Frappe File links before dropping the legacy child table."""
	legacy_meta = bool(frappe.db.exists("DocType", LEGACY_DOCTYPE))
	legacy_table = bool(frappe.db.table_exists(LEGACY_DOCTYPE))
	if not legacy_meta and not legacy_table:
		return
	if not legacy_meta:
		frappe.throw(
			f"{LEGACY_DOCTYPE} table exists without DocType metadata; refusing destructive cleanup.",
			frappe.ValidationError,
		)
	if _doctype_app(LEGACY_DOCTYPE) != APP_NAME:
		frappe.throw(
			f"{LEGACY_DOCTYPE} is not owned by {APP_NAME}; refusing to modify it.",
			frappe.PermissionError,
		)
	if not frappe.db.has_column("Camera", "camera_photos_json") or not frappe.db.has_column("Camera", "primary_image"):
		frappe.throw("Camera gallery fields are not present after model sync; no images were migrated.")

	_assert_no_references()

	if legacy_table:
		required_columns = {
			"name", "parent", "parenttype", "parentfield", "idx", "image", "caption", "description",
			"is_primary", "sort_order",
		}
		missing = sorted(column for column in required_columns if not frappe.db.has_column(LEGACY_DOCTYPE, column))
		if missing:
			frappe.throw(
				f"{LEGACY_DOCTYPE} is missing expected columns ({', '.join(missing)}); refusing to drop it."
			)

		camera_names = frappe.get_all("Camera", pluck="name", order_by="name asc", limit_page_length=0)
		total_rows = frappe.db.count(LEGACY_DOCTYPE)
		migrated_rows = 0
		for camera_batch in _chunks(camera_names, 100):
			rows = frappe.get_all(
				LEGACY_DOCTYPE,
				filters={"parent": ["in", camera_batch]},
				fields=[
					"name", "parent", "parenttype", "parentfield", "idx", "image", "caption", "description",
					"is_primary", "sort_order",
				],
				order_by="parent asc, sort_order asc, idx asc, name asc",
				limit_page_length=0,
			)
			by_camera = defaultdict(list)
			for row in rows:
				if row.parenttype != "Camera" or row.parentfield != "camera_photos":
					frappe.throw(
						f"Unexpected parent link on {LEGACY_DOCTYPE} {row.name}; refusing to drop the table."
					)
				by_camera[row.parent].append(row)

			image_urls = {row.image for row in rows if row.image}
			files_by_url = _file_map(image_urls)
			for camera_name in camera_batch:
				camera_rows = by_camera.get(camera_name, [])
				ordered = sorted(
					camera_rows,
					key=lambda row: (
						row.sort_order if isinstance(row.sort_order, int) and row.sort_order >= 0 else 2**31,
						row.idx or 0,
						row.name,
					),
				)
				photos = []
				for row in ordered:
					if not row.image:
						if row.caption or row.description or row.is_primary:
							frappe.throw(
								f"Camera Photo {row.name} has metadata but no image; refusing to discard it."
							)
						continue
					if not is_safe_frappe_file_url(row.image):
						frappe.throw(f"Camera Photo {row.name} has an unsafe file URL; refusing migration.")
					file_records = files_by_url.get(row.image, [])
					if len(file_records) != 1:
						frappe.throw(
							f"Camera Photo {row.name} does not resolve to exactly one Frappe File; refusing migration."
						)
					file_doc = file_records[0]
					suffix = PurePosixPath(file_doc.file_name or "").suffix.lower()
					if suffix not in _ALLOWED_IMAGE_SUFFIXES:
						frappe.throw(f"Camera Photo {row.name} is not a recognized image file.")
					if file_doc.attached_to_doctype == LEGACY_DOCTYPE and file_doc.attached_to_name == row.name:
						frappe.db.set_value(
							"File",
						file_doc.name,
						{
							"attached_to_doctype": "Camera",
							"attached_to_name": camera_name,
							"attached_to_field": None,
						},
						update_modified=False,
					)
					elif (
						file_doc.attached_to_doctype != "Camera"
						or file_doc.attached_to_name != camera_name
					):
						frappe.throw(
							f"Frappe File for Camera Photo {row.name} is linked elsewhere; refusing to reassign it."
						)
					elif file_doc.attached_to_field:
						frappe.db.set_value(
							"File", file_doc.name, "attached_to_field", None, update_modified=False
						)
					photos.append(
						{
							"url": row.image,
							"caption": row.caption or "",
							"description": row.description or "",
							"is_primary": bool(row.is_primary),
						"sort_order": len(photos),
						"_legacy_primary": bool(row.is_primary),
						}
					)

				if photos:
					primary_index = next((i for i, photo in enumerate(photos) if photo["_legacy_primary"]), 0)
					for index, photo in enumerate(photos):
						photo.pop("_legacy_primary")
						photo["sort_order"] = index
						photo["is_primary"] = index == primary_index
					if len({photo["url"] for photo in photos}) != len(photos):
						frappe.throw(f"Camera {camera_name} has duplicate image URLs; refusing to drop gallery rows.")
					primary_image = photos[primary_index]["url"]
				else:
					primary_image = None
				frappe.db.set_value(
					"Camera",
					camera_name,
					{
						"camera_photos_json": json.dumps(photos, ensure_ascii=False, separators=(",", ":")),
						"primary_image": primary_image,
					},
					update_modified=False,
				)
				migrated_rows += len(camera_rows)

		if migrated_rows != total_rows:
			frappe.throw(
				f"Migrated {migrated_rows} of {total_rows} Camera Photo rows; orphaned rows remain, so the table was kept."
			)

	remaining_files = frappe.get_all(
		"File",
		filters={"attached_to_doctype": LEGACY_DOCTYPE},
		fields=["name", "attached_to_name"],
		limit_page_length=0,
	)
	if remaining_files:
		frappe.throw(
			f"{len(remaining_files)} File records still reference {LEGACY_DOCTYPE}; refusing to orphan them."
		)

	_assert_no_references()
	frappe.delete_doc("DocType", LEGACY_DOCTYPE, force=True, ignore_permissions=True)
	frappe.clear_cache(doctype=LEGACY_DOCTYPE)
