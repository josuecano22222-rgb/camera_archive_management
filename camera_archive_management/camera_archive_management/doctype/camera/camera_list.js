frappe.listview_settings["Camera"] = {
	onload(listview) {
		listview.page.add_inner_button(__("Open camera image map"), () => {
			frappe.route_options = { view: "camera" };
			frappe.set_route("camera-archive-map");
		});
	},
};
