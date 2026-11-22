frappe.ui.form.on("CAM Geo Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Open shared-cache map"), () => frappe.set_route("camera-archive-map"), __("Spatial Tools"));
		frm.set_intro(__("CAM Geo Settings is separate from Siraj Geo Settings. The map reads only the shared private/siraj_tile_cache allow-list."), "blue");
	}
});
