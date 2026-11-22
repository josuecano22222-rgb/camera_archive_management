"""Ensure legacy app child tables have Frappe's parent-link columns.

Early app metadata omitted `istable` for the two nearby-camera child DocTypes.
Frappe model sync marks them as child tables but does not add the three system
columns when altering an existing table, so add them idempotently after model
sync. New child tables already have these columns.
"""

from __future__ import annotations

import frappe
from frappe.database.schema import add_column

_CHILD_COLUMNS = ("parent", "parenttype", "parentfield")


def execute() -> None:
	for doctype in frappe.get_all(
		"DocType",
		filters={"module": "Camera Archive Management", "istable": 1},
		pluck="name",
		order_by="name asc",
	):
		if not frappe.db.table_exists(doctype):
			continue
		for column in _CHILD_COLUMNS:
			if not frappe.db.has_column(doctype, column):
				add_column(doctype, column, "Data")
		frappe.db.add_index(doctype, ["parent"], index_name="parent")
