// Frappe's standard Calendar and Gantt views share this date map.
// Archive Asset records represent capture intervals, so both views can display
// the same recorded-from / recorded-to range without inventing task dates.
frappe.views.calendar["Archive Asset"] = {
	field_map: {
		start: "recorded_from",
		end: "recorded_to",
		id: "name",
		title: "title",
	},
	gantt: true,
	get_events_method: "frappe.desk.calendar.get_events",
};
