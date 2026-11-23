frappe.query_reports["Geo Location Quality"] = {
	filters: [
		{ fieldname: "lookup_source", label: __("Provenance"), fieldtype: "Data" },
		{ fieldname: "only_ambiguous", label: __("Only ambiguous"), fieldtype: "Check", default: 0 }
	]
};
