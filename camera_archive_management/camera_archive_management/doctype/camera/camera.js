frappe.ui.form.on("Camera", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Open map"), () => {
			frappe.route_options = { camera: frm.doc.name };
			frappe.set_route("camera-archive-map");
		}, __("Camera Archive"));
	}
});
