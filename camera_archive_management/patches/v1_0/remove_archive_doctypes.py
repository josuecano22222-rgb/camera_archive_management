"""Remove the retired archive-media DocTypes and every dependent standard record.

Archive Asset, Archive Ingest Batch, and Archive Settings (plus the Archive
Integrity report) are retired. The Motion Event settings that used to live in
Archive Settings are preserved into CAM Geo Settings before anything is
dropped. The patch is repeatable, verifies app ownership, and fails closed when
an external DocType still references a retired one.
"""

from __future__ import annotations

import frappe

APP_NAME = "camera_archive_management"
RETIRED_DOCTYPES = ("Archive Asset", "Archive Ingest Batch", "Archive Settings")
RETIRED_REPORTS = ("Archive Integrity",)
RETIRED_ONBOARDING_STEPS = (
	"Review archive policy and defaults",
	"Create an archive asset record",
	"Prepare an idempotent ingest batch",
	"Check archive integrity and indexing",
)
# Motion Event keeps these defaults; they move to the surviving CAM Geo Settings Single.
MOTION_SETTINGS_FIELDS = (
	"default_motion_importance",
	"enable_nearby_camera_alerts",
	"nearby_camera_radius",
)


def _doctype_app(doctype: str) -> str | None:
	module = frappe.db.get_value("DocType", doctype, "module")
	return frappe.db.get_value("Module Def", module, "app_name") if module else None


def _assert_app_owned() -> None:
	for doctype in RETIRED_DOCTYPES:
		if frappe.db.exists("DocType", doctype) and _doctype_app(doctype) != APP_NAME:
			frappe.throw(
				f"{doctype} is not owned by {APP_NAME}; refusing to remove it.",
				frappe.PermissionError,
			)


def _assert_no_external_references() -> None:
	# DocField stores its owning DocType in `parent`; Custom Field stores it in `dt`.
	for field_doctype, owner_field in (("DocField", "parent"), ("Custom Field", "dt")):
		for field in frappe.get_all(
			field_doctype,
			filters={"options": ["in", RETIRED_DOCTYPES]},
			fields=[owner_field, "fieldname", "options"],
			limit_page_length=0,
		):
			owner = field.get(owner_field)
			if owner not in RETIRED_DOCTYPES:
				frappe.throw(
					f"Cannot remove the archive DocTypes: {owner}.{field.fieldname} still references "
					f"{field.options}. Remove that link first.",
					frappe.ValidationError,
				)


def _motion_settings_values() -> dict:
	"""Read the surviving Motion Event defaults from Archive Settings.

	Values are read from ``tabSingles`` directly so the patch also works after the
	DocType metadata is gone. A pre-consolidation site may still hold legacy table
	rows; conflicting rows fail closed instead of silently picking a winner.
	"""
	values: dict = {}
	rows = frappe.db.sql(
		"SELECT `field`, `value` FROM `tabSingles` WHERE `doctype` = 'Archive Settings'",
		as_dict=True,
	)
	values.update({row.field: row.value for row in rows})

	if frappe.db.table_exists("Archive Settings"):
		columns = set(frappe.db.get_table_columns("Archive Settings"))
		legacy_fields = [field for field in MOTION_SETTINGS_FIELDS if field in columns]
		if legacy_fields:
			selected = ", ".join(f"`{field}`" for field in legacy_fields)
			legacy_rows = frappe.db.sql(
				f"SELECT {selected} FROM `tabArchive Settings` ORDER BY `modified` ASC, `name` ASC",
				as_dict=True,
			)
			signatures = {tuple(row.get(field) for field in legacy_fields) for row in legacy_rows}
			if len(signatures) > 1:
				frappe.throw(
					"Cannot retire Archive Settings: legacy settings rows contain different Motion Event "
					"defaults. Consolidate them before retrying.",
					frappe.ValidationError,
				)
			if legacy_rows:
				for field, value in zip(legacy_fields, legacy_rows[0], strict=True):
					if values.get(field) is None and value is not None:
						values[field] = value
	return {field: values[field] for field in MOTION_SETTINGS_FIELDS if values.get(field) is not None}


def _preserve_motion_settings() -> None:
	if not frappe.db.exists("DocType", "Archive Settings") and not frappe.db.table_exists("Archive Settings"):
		return
	for field, value in _motion_settings_values().items():
		frappe.db.set_single_value("CAM Geo Settings", field, value, update_modified=False)


def _delete_dependent_records() -> None:
	for report in frappe.get_all("Report", filters={"ref_doctype": ["in", RETIRED_DOCTYPES]}, pluck="name"):
		frappe.delete_doc("Report", report, force=True, ignore_permissions=True)
	for card in frappe.get_all(
		"Number Card", filters={"document_type": ["in", RETIRED_DOCTYPES]}, pluck="name"
	):
		frappe.delete_doc("Number Card", card, force=True, ignore_permissions=True)
	for chart in frappe.get_all(
		"Dashboard Chart", filters={"document_type": ["in", RETIRED_DOCTYPES]}, pluck="name"
	):
		frappe.delete_doc("Dashboard Chart", chart, force=True, ignore_permissions=True)
	for step in frappe.get_all(
		"Onboarding Step", filters={"reference_document": ["in", RETIRED_DOCTYPES]}, pluck="name"
	):
		frappe.delete_doc("Onboarding Step", step, force=True, ignore_permissions=True)
	for step in frappe.get_all(
		"Onboarding Step", filters={"reference_report": ["in", RETIRED_REPORTS]}, pluck="name"
	):
		frappe.delete_doc("Onboarding Step", step, force=True, ignore_permissions=True)

	# Standard Workspace/Onboarding JSON sync already replaces these children; clean
	# defensively so no custom workspace keeps a widget pointed at a retired record.
	retired_links = [*RETIRED_DOCTYPES, *RETIRED_REPORTS]
	frappe.db.delete("Workspace Link", {"link_to": ["in", retired_links]})
	frappe.db.delete("Workspace Shortcut", {"link_to": ["in", retired_links]})
	frappe.db.delete("Onboarding Step Map", {"step": ["in", RETIRED_ONBOARDING_STEPS]})
	frappe.db.delete(
		"Workspace Number Card",
		{"number_card_name": ["in", ("Archive Assets", "Pending Archive Index", "Failed Ingest Batches")]},
	)
	frappe.db.delete(
		"Workspace Chart",
		{
			"chart_name": [
				"in",
				(
					"Camera Archive - Archive Retention State",
					"Camera Archive - Archive Index Status",
					"Camera Archive - Ingest Batch Pipeline",
					"Camera Archive - Archive Intake Trend",
				),
			]
		},
	)

	# Attachments (ingest manifests and similar) belong to the retired records.
	for file_name in frappe.get_all(
		"File", filters={"attached_to_doctype": ["in", RETIRED_DOCTYPES]}, pluck="name"
	):
		frappe.delete_doc("File", file_name, force=True, ignore_permissions=True)
	frappe.db.delete("__Auth", {"doctype": ["in", RETIRED_DOCTYPES]})


def _drop_retired_storage() -> None:
	"""Frappe keeps the physical table after DocType deletion; drop it explicitly.

	Archive Settings is a Single, so its values live in ``tabSingles`` rather than
	a dedicated table. Both stores are removed so nothing survives the retirement.
	``sql_ddl`` commits before executing, which makes a partial failure safe: the
	patch is repeatable and a re-run finishes the remaining cleanup.
	"""
	frappe.db.delete("Singles", {"doctype": "Archive Settings"})
	for doctype in RETIRED_DOCTYPES:
		if frappe.db.table_exists(doctype, cached=False):
			frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{doctype}`")


def execute() -> None:
	if any(frappe.db.exists("DocType", doctype) for doctype in RETIRED_DOCTYPES):
		_assert_app_owned()
		_assert_no_external_references()
		_preserve_motion_settings()
	# Repeat runs also clear orphaned dependent records left behind by older versions.
	_delete_dependent_records()
	for doctype in RETIRED_DOCTYPES:
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True)
			frappe.clear_cache(doctype=doctype)
	_drop_retired_storage()
