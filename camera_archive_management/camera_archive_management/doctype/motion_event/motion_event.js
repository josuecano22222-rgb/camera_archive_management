frappe.ui.form.on("Motion Event", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Show movement on map"), () => {
				frappe.route_options = { event: frm.doc.name, view: "movement" };
				frappe.set_route("camera-archive-map");
			}, __("Camera Archive"));
		}
		inherit_camera_importance(frm);
		show_event_vehicle(frm);
	},
	camera(frm) {
		inherit_camera_importance(frm);
	},
	importance(frm) {
		frm.__cam_importance_request = (frm.__cam_importance_request || 0) + 1;
		frm.__cam_importance_inherited = false;
	},
	vehicle(frm) {
		show_event_vehicle(frm);
	}
});

async function inherit_camera_importance(frm) {
	if (!frm.is_new() || !frm.doc.camera) return;
	if (frm.doc.importance && !frm.__cam_importance_inherited) return;
	const existingImportance = frm.doc.importance;
	const cameraName = frm.doc.camera;
	const request = (frm.__cam_importance_request || 0) + 1;
	frm.__cam_importance_request = request;
	try {
		const result = await frappe.db.get_value("Camera", cameraName, "importance");
		const configuredDefault = await frappe.db.get_single_value("Archive Settings", "default_motion_importance");
		if (frm.doc.camera !== cameraName || frm.__cam_importance_request !== request) return;
		if (frm.doc.importance !== existingImportance && !frm.__cam_importance_inherited) return;
		const importance = result?.message?.importance || configuredDefault || "Medium";
		if (frm.doc.importance !== importance) await frm.set_value("importance", importance);
		frm.__cam_importance_inherited = true;
	} catch (_error) {
		// The server remains authoritative when an operator saves the event.
	}
}

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
