// The standard Gantt view consumes its dates from the list query. Keep these
// timeline fields available to the view without crowding the everyday list.
frappe.listview_settings["Archive Asset"] = {
	add_fields: ["recorded_from", "recorded_to"],
};
