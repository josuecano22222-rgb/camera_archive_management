frappe.ui.form.on("Archive Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Open camera map"), () => frappe.set_route("camera-archive-map"), __("Camera Archive"));
		frm.set_intro(__("Camera images, vehicle movement markers, and map tiles use the shared Siraj tile cache."), "blue");
	}
});
