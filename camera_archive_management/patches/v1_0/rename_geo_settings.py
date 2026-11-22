"""Move this app's Geo Settings Single away from Siraj's DocType name."""

from __future__ import annotations

import frappe

_APP_NAME = "camera_archive_management"
_OLD_NAME = "Geo Settings"
_NEW_NAME = "CAM Geo Settings"


def _doctype_app(doctype: str) -> str | None:
	module = frappe.db.get_value("DocType", doctype, "module")
	return frappe.db.get_value("Module Def", module, "app_name") if module else None


def execute() -> None:
	new_exists = bool(frappe.db.exists("DocType", _NEW_NAME))
	if new_exists and _doctype_app(_NEW_NAME) != _APP_NAME:
		frappe.throw("CAM Geo Settings is already owned by another app; refusing to modify it.")
	if not frappe.db.exists("DocType", _OLD_NAME):
		return

	# The installed Geo Settings DocType belongs to Siraj. Leave its metadata,
	# Singles rows, permissions and map settings entirely untouched.
	if _doctype_app(_OLD_NAME) != _APP_NAME:
		return
	if new_exists:
		frappe.throw("Both CAM Geo Settings and this app's legacy Geo Settings exist; resolve the conflict.")

	frappe.rename_doc(
		"DocType",
		_OLD_NAME,
		_NEW_NAME,
		ignore_permissions=True,
		show_alert=False,
		rebuild_search=False,
	)
	frappe.clear_cache(doctype=_OLD_NAME)
	frappe.clear_cache(doctype=_NEW_NAME)
