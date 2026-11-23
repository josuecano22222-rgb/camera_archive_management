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
	},
	after_save(frm) {
		if (!frm.doc.docstatus) show_nearby_camera_alert(frm);
	},
	on_submit(frm) {
		show_nearby_camera_alert(frm);
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

function show_nearby_camera_alert(frm) {
	const rows = (Array.isArray(frm.doc.nearby_cameras) ? frm.doc.nearby_cameras : []).filter((row) => row.camera);
	if (!rows.length) return;

	const phase = frm.doc.docstatus === 1 ? __("submitted") : __("saved");
	const signature = `${frm.doc.docstatus}:${rows.map((row) => `${row.camera}:${row.note || ""}`).join("|")}`;
	if (frm.__camNearbyCameraAlerted === signature) return;
	frm.__camNearbyCameraAlerted = signature;

	const list = rows.slice(0, 8).map((row) => {
		const camera = frappe.utils.escape_html(row.camera);
		const relationship = String(row.note || "").startsWith("Configured connection")
			? __("configured camera connection")
			: __("within the configured nearby-camera radius");
		const details = [relationship];
		if (row.distance_m !== null && row.distance_m !== undefined && row.distance_m !== "") {
			const distance = Number(row.distance_m);
			if (Number.isFinite(distance)) details.push(`${distance.toFixed(1)} m`);
		}
		if (row.bearing_compass) details.push(frappe.utils.escape_html(row.bearing_compass));
		if (row.area) details.push(__("area: {0}", [frappe.utils.escape_html(row.area)]));
		return `<li><strong>${camera}</strong> — ${details.join(" · ")}</li>`;
	});
	if (rows.length > list.length) {
		list.push(`<li>${__("and {0} more camera(s)", [rows.length - list.length])}</li>`);
	}

	frappe.msgprint({
		title: __("Nearby camera alert"),
		message: `<p>${__("Movement {0}. Other camera coverage is available for this location:", [phase])}</p><ul>${list.join("")}</ul>`,
		indicator: "orange",
	});
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
			fallback.className = "cam-vehicle-preview-fallback cam-map-user-location-point";
			fallback.setAttribute("aria-label", __("No user-configured vehicle image"));
			host.append(fallback);
		}
	} catch (error) {
		const fallback = document.createElement("div");
		fallback.className = "cam-vehicle-preview-fallback cam-map-user-location-point";
		fallback.setAttribute("aria-label", __("Vehicle image unavailable"));
		host.append(fallback);
	}
}
