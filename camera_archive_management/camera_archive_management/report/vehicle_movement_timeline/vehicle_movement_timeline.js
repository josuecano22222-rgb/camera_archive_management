frappe.query_reports["Vehicle Movement Timeline"] = {
	filters: [
		{ fieldname: "start_date", label: __("From"), fieldtype: "Date" },
		{ fieldname: "end_date", label: __("To"), fieldtype: "Date" },
		{ fieldname: "vehicle", label: __("CAM Vehicle"), fieldtype: "Link", options: "CAM Vehicle" }
	],
	formatter(value, row, column, data, default_formatter) {
		if (column.fieldname === "vehicle_image" && value && /^\/(?:private\/)?files\//.test(value)) {
			const safe = frappe.utils.escape_html(value);
			const alt = frappe.utils.escape_html(data?.vehicle_name || __("Vehicle"));
			return `<img src="${safe}" alt="${alt}" class="cam-report-vehicle-image">`;
		}
		return default_formatter(value, row, column, data);
	}
};
