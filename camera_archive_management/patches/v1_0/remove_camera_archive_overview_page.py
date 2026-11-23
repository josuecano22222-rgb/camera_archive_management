"""Remove the retired Camera Archive Overview desk page."""

from __future__ import annotations

import frappe


def execute() -> None:
	page_name = "camera-archive-overview"
	if frappe.db.exists("Page", page_name):
		frappe.delete_doc("Page", page_name, force=True, ignore_permissions=True)
