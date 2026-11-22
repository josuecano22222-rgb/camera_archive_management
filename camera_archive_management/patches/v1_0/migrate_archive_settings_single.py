"""Copy the former Archive Settings document into its Single DocType values."""

from __future__ import annotations

import frappe

_FIELDS = (
	"default_report_days",
	"default_motion_importance",
	"enable_daily_integrity_check",
	"enable_nearby_camera_alerts",
	"nearby_camera_radius",
	"nearby_alert_roles",
	"report_schedule_note",
)


def execute() -> None:
	if not frappe.db.table_exists("Archive Settings"):
		return
	columns = set(frappe.db.get_table_columns("Archive Settings"))
	fields = [field for field in _FIELDS if field in columns]
	if not fields:
		return
	selected = ", ".join(f"`{field}`" for field in fields)
	rows = frappe.db.sql(
		f"SELECT `name`, {selected} FROM `tabArchive Settings` ORDER BY `modified` ASC, `name` ASC",
		as_dict=True,
	)
	if not rows:
		return

	def signature(row):
		return tuple(row.get(field) for field in fields)

	signatures = {signature(row) for row in rows}
	if len(signatures) > 1:
		frappe.throw(
			"Cannot convert Archive Settings to Single: multiple legacy settings documents contain different values. "
			f"Review and consolidate records before retrying. Legacy names: {[row.name for row in rows]!r}",
			frappe.ValidationError,
		)
	for field, value in zip(fields, signature(rows[0]), strict=True):
		if value is not None:
			frappe.db.set_single_value("Archive Settings", field, value, update_modified=False)
