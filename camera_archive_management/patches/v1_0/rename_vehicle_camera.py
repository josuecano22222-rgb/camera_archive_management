"""Safely migrate this app's legacy vehicle DocType to CAM Vehicle."""

from __future__ import annotations

import frappe

LEGACY_DOCTYPE = "Vehicle Camera"
INTERMEDIATE_DOCTYPE = "Vehicle"
TARGET_DOCTYPE = "CAM Vehicle"
_APP_NAME = "camera_archive_management"


def _doctype_app(doctype: str) -> str | None:
	module = frappe.db.get_value("DocType", doctype, "module")
	return frappe.db.get_value("Module Def", module, "app_name") if module else None


def _rename_metadata(old_name: str) -> None:
	frappe.rename_doc(
		"DocType",
		old_name,
		TARGET_DOCTYPE,
		show_alert=False,
		rebuild_search=False,
	)


def execute() -> None:
	"""Rename app-owned metadata/table while never touching another app's Vehicle."""
	legacy_meta = bool(frappe.db.exists("DocType", LEGACY_DOCTYPE))
	legacy_table = bool(frappe.db.table_exists(LEGACY_DOCTYPE))
	intermediate_meta = bool(frappe.db.exists("DocType", INTERMEDIATE_DOCTYPE))
	target_meta = bool(frappe.db.exists("DocType", TARGET_DOCTYPE))
	target_table = bool(frappe.db.table_exists(TARGET_DOCTYPE))

	if target_meta and _doctype_app(TARGET_DOCTYPE) != _APP_NAME:
		frappe.throw("CAM Vehicle is already owned by another app; refusing to modify it.")
	if target_meta and legacy_meta:
		frappe.throw("Both CAM Vehicle and legacy DocType metadata exist; resolve the conflict before migration.")
	if target_meta and legacy_table and target_table:
		frappe.throw("Both CAM Vehicle and legacy vehicle tables exist; no rows were merged or deleted.")

	# Vehicle was the DocType name used by an early, not-yet-released Phase 3
	# iteration. Only rename it when its metadata belongs to this app. A foreign
	# Vehicle DocType is intentionally left alone.
	if intermediate_meta and _doctype_app(INTERMEDIATE_DOCTYPE) == _APP_NAME:
		if target_meta or target_table:
			frappe.throw("Cannot rename this app's Vehicle: CAM Vehicle already exists.")
		_rename_metadata(INTERMEDIATE_DOCTYPE)
		target_meta = True
		target_table = bool(frappe.db.table_exists(TARGET_DOCTYPE))

	if legacy_meta:
		if target_meta or target_table:
			frappe.throw("Cannot migrate Vehicle Camera: CAM Vehicle already exists.")
		_rename_metadata(LEGACY_DOCTYPE)
		target_meta = True
		target_table = bool(frappe.db.table_exists(TARGET_DOCTYPE))
		legacy_table = False
	elif legacy_table:
		if target_meta and not target_table:
			frappe.db.rename_table(LEGACY_DOCTYPE, TARGET_DOCTYPE)
			target_table = True
		elif target_table:
			frappe.throw("Both legacy and target vehicle tables exist; no rows were merged or deleted.")
		else:
			frappe.throw(
				"Vehicle Camera table exists without DocType metadata. Restore metadata or perform reviewed recovery."
			)

	if target_meta and frappe.db.table_exists("File") and frappe.db.has_column("File", "attached_to_doctype"):
		File = frappe.qb.DocType("File")
		for old_name in (LEGACY_DOCTYPE, INTERMEDIATE_DOCTYPE):
			frappe.qb.update(File).set(File.attached_to_doctype, TARGET_DOCTYPE).where(
				File.attached_to_doctype == old_name
			).run()

	for doctype in (LEGACY_DOCTYPE, INTERMEDIATE_DOCTYPE, TARGET_DOCTYPE):
		frappe.clear_cache(doctype=doctype)
