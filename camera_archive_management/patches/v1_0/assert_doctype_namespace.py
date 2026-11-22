"""Fail closed if any shipped app DocType name is already owned elsewhere."""

from __future__ import annotations

import json
from pathlib import Path

import frappe

_APP_NAME = "camera_archive_management"


def execute() -> None:
	doctype_root = Path(frappe.get_app_path(_APP_NAME)) / "camera_archive_management" / "doctype"
	for schema_path in sorted(doctype_root.glob("*/*.json")):
		try:
			schema = json.loads(schema_path.read_text(encoding="utf-8"))
		except (OSError, json.JSONDecodeError) as exc:
			frappe.throw(f"Could not inspect DocType schema {schema_path.name}: {exc}", frappe.ValidationError)
		name = schema.get("name")
		if not name or not frappe.db.exists("DocType", name):
			continue
		module = frappe.db.get_value("DocType", name, "module")
		owner = frappe.db.get_value("Module Def", module, "app_name") if module else None
		if owner != _APP_NAME:
			frappe.throw(
				f"DocType name collision: {name!r} is already owned by app {owner or 'unknown'!r}. "
				"Rename the app DocType before migration; existing data was not modified.",
				frappe.ValidationError,
			)
