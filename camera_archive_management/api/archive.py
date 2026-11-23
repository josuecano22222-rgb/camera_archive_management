from __future__ import annotations

import frappe


@frappe.whitelist(methods=["POST"])
def queue_asset_index(asset_name):
	if not isinstance(asset_name, str) or not asset_name or len(asset_name) > 140:
		frappe.throw("Invalid Archive Asset name.", frappe.ValidationError)
	if not frappe.has_permission("Archive Asset", "write", asset_name):
		frappe.throw("Only Archive Managers may queue asset indexing.", frappe.PermissionError)
	asset = frappe.get_doc("Archive Asset", asset_name)
	if asset.index_status not in {"Pending", "Failed", "Queued"}:
		frappe.throw("Only Pending, Failed, or already Queued assets may be queued.", frappe.ValidationError)
	asset.index_status = "Queued"
	asset.index_error = None
	asset.save()
	return {"queued": True, "asset": asset.name}
