frappe.ui.form.on("CAM Geo Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Open shared-cache map"), () => frappe.set_route("camera-archive-map"), __("Spatial Tools"));
		frm.set_intro(__("Map tiles use Siraj Research's configured provider catalog and shared private/siraj_tile_cache. Online fetching requires both CAM online-fetch/cache-write flags and Siraj Geo Settings > Allow server to fetch from provider. Review provider terms and attribution before enabling."), "blue");
	}
});
