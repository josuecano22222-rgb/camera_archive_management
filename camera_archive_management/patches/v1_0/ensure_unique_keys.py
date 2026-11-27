"""Install concurrency-safe unique constraints after DocType tables exist."""

from __future__ import annotations

import frappe
from frappe.query_builder.functions import Count


def _duplicates(doctype: str, fields: list[str], where_nonempty: str | None = None) -> list:
	doc = frappe.qb.DocType(doctype)
	query = frappe.qb.from_(doc).select(
		*[getattr(doc, field) for field in fields], Count("*").as_("row_count")
	)
	if where_nonempty:
		query = query.where(getattr(doc, where_nonempty).isnotnull() & (getattr(doc, where_nonempty) != ""))
	query = query.groupby(*[getattr(doc, field) for field in fields]).having(Count("*") > 1)
	return query.orderby(*[getattr(doc, field) for field in fields]).limit(10).run(as_dict=True)


def execute() -> None:
	for doctype, fields, constraint in (
		("Geo Admin Area", ["dataset", "code"], "uniq_cam_geo_admin_code"),
		("Geo Boundary", ["dataset", "boundary_code"], "uniq_cam_geo_boundary_code"),
		("Geo Gazetteer Place", ["dataset", "place_code"], "uniq_cam_geo_place_code"),
	):
		if not frappe.db.table_exists(doctype):
			continue
		duplicates = _duplicates(doctype, fields)
		if duplicates:
			frappe.throw(
				f"Cannot install {doctype} dataset/code uniqueness constraint; resolve duplicates first: {duplicates!r}",
				frappe.ValidationError,
			)
		frappe.db.add_unique(doctype, fields, constraint_name=constraint)
