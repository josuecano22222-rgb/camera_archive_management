frappe.ui.form.on("CAM Vehicle", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("View movements on map"), () => {
			frappe.route_options = { vehicle: frm.doc.name };
			frappe.set_route("camera-archive-map");
		}, __("Camera Archive"));
		show_vehicle_image(frm);
	},
	vehicle_image(frm) {
		show_vehicle_image(frm);
	},
	vehicle_type(frm) {
		show_vehicle_image(frm);
	}
});

async function show_vehicle_image(frm) {
	const host = frm.fields_dict.vehicle_image_preview?.$wrapper;
	if (!host) return;
	let image = frm.doc.vehicle_image;
	if (!image && frm.doc.vehicle_type) {
		try {
			const result = await frappe.db.get_value("Vehicle Type", frm.doc.vehicle_type, "vehicle_type_image");
			image = result?.message?.vehicle_type_image;
		} catch (error) {
			image = null;
		}
	}
	host.empty();
	if (image && /^\/(?:private\/)?files\//.test(image)) {
		const img = document.createElement("img");
		img.src = image;
		img.alt = frm.doc.vehicle_name || __("Vehicle movement icon");
		img.className = "cam-vehicle-preview";
		host.append(img);
	} else {
		host.html(`<div class="cam-vehicle-preview-fallback" aria-label="${frappe.utils.escape_html(__("Vehicle icon fallback"))}">🚘</div>`);
	}
}
