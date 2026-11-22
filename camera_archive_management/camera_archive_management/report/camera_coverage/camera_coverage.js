frappe.query_reports["Camera Coverage"] = {
	filters: [
		{ fieldname: "camera_area", label: __("Camera Area"), fieldtype: "Link", options: "Camera Area" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nActive\nInactive\nMaintenance" }
	]
};
