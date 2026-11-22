frappe.query_reports["Archive Integrity"] = {
	filters: [
		{ fieldname: "storage_backend", label: __("Storage Backend"), fieldtype: "Select", options: "\nFrappe File\nExternal" },
		{ fieldname: "index_status", label: __("Index Status"), fieldtype: "Select", options: "\nPending\nQueued\nRunning\nComplete\nFailed" },
		{ fieldname: "retention_state", label: __("Retention State"), fieldtype: "Select", options: "\nActive\nHold\nExpired\nDeleted" }
	]
};
