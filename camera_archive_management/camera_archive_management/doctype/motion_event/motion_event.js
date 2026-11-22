frappe.ui.form.on("Motion Event", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Show movement on map"), () => {
				frappe.route_options = { event: frm.doc.name };
				frappe.set_route("camera-archive-map");
			}, __("Camera Archive"));
		}
		show_event_vehicle(frm);
	},
	vehicle(frm) {
		show_event_vehicle(frm);
	}
});

async function show_event_vehicle(frm) {
	const host = frm.fields_dict.vehicle_visual?.$wrapper;
	if (!host) return;
	host.empty();
	if (!frm.doc.vehicle) return;
	try {
		const vehicle = await frappe.db.get_doc("CAM Vehicle", frm.doc.vehicle);
		let image = vehicle.vehicle_image;
		if (!image && vehicle.vehicle_type) {
			const result = await frappe.db.get_value("Vehicle Type", vehicle.vehicle_type, "vehicle_type_image");
			image = result?.message?.vehicle_type_image;
		}
		if (image && /^\/(?:private\/)?files\//.test(image)) {
			const img = document.createElement("img");
			img.src = image;
			img.alt = vehicle.vehicle_name || __("Vehicle movement icon");
			img.className = "cam-vehicle-preview";
			host.append(img);
		} else {
			const fallback = document.createElement("div");
			fallback.className = "cam-vehicle-preview-fallback";
			fallback.textContent = "🚘";
			host.append(fallback);
		}
	} catch (error) {
		const fallback = document.createElement("div");
		fallback.className = "cam-vehicle-preview-fallback";
		fallback.textContent = "🚘";
		host.append(fallback);
	}
}
