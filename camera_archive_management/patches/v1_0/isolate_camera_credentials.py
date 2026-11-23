"""Move legacy plain-text camera credentials into Password-backed records."""

from __future__ import annotations

import frappe


def _legacy_columns(doctype: str) -> list[str]:
	if not frappe.db.table_exists(doctype):
		return []
	return [field for field in ("username", "password") if frappe.db.has_column(doctype, field)]


def _read_legacy_camera_credentials(columns: list[str]) -> list[dict]:
	if not columns:
		return []
	selected = ", ".join(f"`{field}`" for field in columns)
	return frappe.db.sql(
		f"SELECT `name`, {selected} FROM `tabCamera` WHERE "
		+ " OR ".join(f"`{field}` IS NOT NULL AND `{field}` <> ''" for field in columns),
		as_dict=True,
	)


def _migrate_camera_credentials(rows: list[dict]) -> None:
	for row in rows:
		if not frappe.db.exists("Camera", row.name):
			continue
		name = frappe.db.get_value("Camera Credential", {"camera": row.name}, "name")
		credential = (
			frappe.get_doc("Camera Credential", name) if name else frappe.new_doc("Camera Credential")
		)
		credential.camera = row.name
		if row.get("username") and not credential.username:
			credential.username = row.username
		if row.get("password") and not credential.password:
			credential.password = row.password
		credential.active = 1
		credential.flags.ignore_permissions = True
		if name:
			credential.save(ignore_permissions=True)
		else:
			credential.insert(ignore_permissions=True)


def _clear_legacy_columns(doctype: str) -> None:
	columns = _legacy_columns(doctype)
	if not columns:
		return
	Doc = frappe.qb.DocType(doctype)
	query = frappe.qb.update(Doc)
	for field in columns:
		query = query.set(getattr(Doc, field), None)
	query.run()


def execute() -> None:
	# This patch runs before app model sync drops removed credential columns.
	# Ensure the protected destination DocType exists early so Password values
	# are encrypted through Frappe's normal document save lifecycle.
	frappe.reload_doc("camera_archive_management", "doctype", "camera_credential")
	camera_columns = _legacy_columns("Camera")
	if camera_columns and frappe.db.table_exists("Camera Credential"):
		_migrate_camera_credentials(_read_legacy_camera_credentials(camera_columns))
		_clear_legacy_columns("Camera")

	# Motion Event fields were fetched copies, not independent credentials.
	# Purge them rather than copying historical secrets into the new credential store.
	_clear_legacy_columns("Motion Event")
