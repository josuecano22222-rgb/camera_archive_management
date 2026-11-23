frappe.listview_settings["Motion Event"] = {
	get_coords_method: "camera_archive_management.api.map.get_custom_map_coords",
	onload(listview) {
		listview.page.add_inner_button(__("Open vehicle movement map"), () => {
			frappe.route_options = { view: "movement" };
			frappe.set_route("camera-archive-map");
		});
	},
};
