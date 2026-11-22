frappe.pages["camera-archive-map"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Camera Archive Map"), single_column: true });
	page.set_primary_action(__("Refresh"), () => load_map(page), "refresh");
	page.cam_map_options = Object.assign(
		{ camera: null, vehicle: null, event: null },
		page.cam_map_options || {}
	);
	page.cam_map_context = {
		host: window.location.host,
		origin: window.location.origin || `${window.location.protocol}//${window.location.host}`
	};
	const route_state = sync_route_filters_to_page(page, { force: true });
	const host = page.main.get(0);
	host.innerHTML = `
		<div class="cam-map-toolbar">
		<label>${__("From")} <input class="form-control cam-map-from" type="date"></label>
		<label>${__("To")} <input class="form-control cam-map-to" type="date"></label>
		<label>${__("Camera ID")} <input class="form-control cam-map-camera" type="text" maxlength="140"></label>
		<label>${__("CAM Vehicle ID")} <input class="form-control cam-map-vehicle" type="text" maxlength="140"></label>
		<label>${__("Motion Event ID")} <input class="form-control cam-map-event" type="text" maxlength="140"></label>
		<label>${__("Basemap")} <select class="form-control cam-map-layer">
				<option value="standard">${__("Standard")}</option>
				<option value="aerial">${__("Aerial")}</option>
				<option value="hybrid">${__("Hybrid")}</option>
			</select></label>
			<button class="btn btn-primary cam-map-apply">${__("Apply filters")}</button>
			<span class="cam-map-filter-note"></span>
		</div>
		<div class="cam-map-shell">
			<div class="cam-map-canvas" role="application" aria-label="${__("Camera and vehicle movement map")}"></div>
			<aside class="cam-map-sidebar">
				<div class="cam-map-summary text-muted">${__("Loading cameras and movements…")}</div>
				<div class="cam-map-movement-list"></div>
			</aside>
		</div>`;

	const today = new Date();
	const start = new Date(today);
	start.setDate(today.getDate() - 30);
	const default_start = start.toISOString().slice(0, 10);
	const default_end = today.toISOString().slice(0, 10);
	host.querySelector(".cam-map-from").value = route_state.controls.start || default_start;
	host.querySelector(".cam-map-to").value = route_state.controls.end || default_end;
	host.querySelector(".cam-map-camera").value = page.cam_map_options.camera || "";
	host.querySelector(".cam-map-vehicle").value = page.cam_map_options.vehicle || "";
	host.querySelector(".cam-map-event").value = page.cam_map_options.event || "";
	if (["standard", "aerial", "hybrid"].includes(route_state.controls.layer)) {
		host.querySelector(".cam-map-layer").value = route_state.controls.layer;
	}
	page.$filter_note = $(host.querySelector(".cam-map-filter-note"));
	update_filter_note(page);
	page.cam_map = L.map(host.querySelector(".cam-map-canvas"), { zoomControl: true }).setView([52.37, 4.90], 5);
	if (!page.cam_map_route_listener && frappe.router?.on) {
		page.cam_map_route_listener = () => {
			const current_route = frappe.get_route() || [];
			if (current_route[0] !== "camera-archive-map") page.cam_map_was_away = true;
		};
		frappe.router.on("change", page.cam_map_route_listener);
	}
	page.cam_base_layers = {};
	page.cam_overlay = null;
	page.cam_markers = L.featureGroup().addTo(page.cam_map);
	page.cam_tracks = L.featureGroup().addTo(page.cam_map);
	host.querySelector(".cam-map-apply").addEventListener("click", () => {
		read_filter_controls(page);
		update_filter_note(page);
		load_map(page);
	});
	host.querySelector(".cam-map-layer").addEventListener("change", () => set_basemap(page));
	for (const selector of [".cam-map-camera", ".cam-map-vehicle", ".cam-map-event"]) {
		const input = host.querySelector(selector);
		input.addEventListener("input", () => {
			read_filter_controls(page);
			update_filter_note(page);
			queue_map_reload(page);
		});
		input.addEventListener("change", () => {
			clearTimeout(page.cam_map_reload_timer);
			read_filter_controls(page);
			update_filter_note(page);
			load_map(page);
		});
		input.addEventListener("keydown", (event) => {
			if (event.key === "Enter") {
				clearTimeout(page.cam_map_reload_timer);
				read_filter_controls(page);
				update_filter_note(page);
				load_map(page);
			}
		});
	}
	for (const selector of [".cam-map-from", ".cam-map-to"]) {
		host.querySelector(selector).addEventListener("change", () => load_map(page));
	}
	load_map(page);
};

frappe.pages["camera-archive-map"].on_page_show = function (wrapper) {
	const page = wrapper.page;
	if (!page?.cam_map) return;
	const route_state = sync_route_filters_to_page(page);
	if (!route_state.changed) return;
	const host = page.main.get(0);
	page.$filter_note = $(host.querySelector(".cam-map-filter-note"));
	host.querySelector(".cam-map-camera").value = page.cam_map_options.camera || "";
	host.querySelector(".cam-map-vehicle").value = page.cam_map_options.vehicle || "";
	host.querySelector(".cam-map-event").value = page.cam_map_options.event || "";
	const today = new Date();
	const start = new Date(today);
	start.setDate(today.getDate() - 30);
	host.querySelector(".cam-map-from").value = route_state.controls.start || start.toISOString().slice(0, 10);
	host.querySelector(".cam-map-to").value = route_state.controls.end || today.toISOString().slice(0, 10);
	if (["standard", "aerial", "hybrid"].includes(route_state.controls.layer)) {
		host.querySelector(".cam-map-layer").value = route_state.controls.layer;
	}
	update_filter_note(page);
	load_map(page);
};

const CAM_MAP_FILTER_KEYS = ["camera", "vehicle", "event"];
const CAM_MAP_ROUTE_KEYS = [...CAM_MAP_FILTER_KEYS, "start", "end", "layer"];

function clean_route_value(value) {
	if (value === undefined || value === null) return null;
	const text = String(value).trim();
	return text || null;
}

function sync_route_filters_to_page(page, { force = false } = {}) {
	page.cam_map_options = Object.assign(
		{ camera: null, vehicle: null, event: null },
		page.cam_map_options || {}
	);
	page.cam_map_route_values = Object.assign(
		{ start: null, end: null, layer: null },
		page.cam_map_route_values || {}
	);
	const route = frappe.get_route() || [];
	const route_options = frappe.route_options && typeof frappe.route_options === "object"
		? frappe.route_options
		: {};
	const from_route = {};
	for (let i = 1; i < route.length; i += 2) {
		const key = route[i];
		if (key && CAM_MAP_ROUTE_KEYS.includes(key)) from_route[key] = route[i + 1] || null;
	}
	const has_route_filters = CAM_MAP_FILTER_KEYS.some((key) => Object.hasOwn(route_options, key));
	const has_positional_filters = CAM_MAP_FILTER_KEYS.some((key) => Object.hasOwn(from_route, key));
	const has_route_controls = ["start", "end", "layer"].some(
		(key) => Object.hasOwn(route_options, key) || Object.hasOwn(from_route, key)
	);
	const identity = JSON.stringify(route);
	const route_changed = identity !== page.cam_map_route_identity;
	const route_was_away = Boolean(page.cam_map_was_away);
	const has_route_options = Object.keys(route_options).length > 0;
	let changed = route_changed || route_was_away || has_route_options || force;

	if (has_route_filters || has_positional_filters) {
		for (const key of CAM_MAP_FILTER_KEYS) {
			const value = Object.hasOwn(route_options, key) ? route_options[key] : from_route[key];
			const normalized = clean_route_value(value);
			if (page.cam_map_options[key] !== normalized) changed = true;
			page.cam_map_options[key] = normalized;
		}
	} else if (route_changed || route_was_away || has_route_options || force) {
		for (const key of CAM_MAP_FILTER_KEYS) {
			if (page.cam_map_options[key] !== null) changed = true;
			page.cam_map_options[key] = null;
		}
	}

	if (has_route_controls || route_changed || route_was_away || has_route_options || force) {
		for (const key of ["start", "end", "layer"]) {
			const value = Object.hasOwn(route_options, key) ? route_options[key] : from_route[key];
			const normalized = clean_route_value(value);
			if (page.cam_map_route_values[key] !== normalized) changed = true;
			page.cam_map_route_values[key] = normalized;
		}
	}
	page.cam_map_route_identity = identity;
	page.cam_map_was_away = false;
	if (has_route_options) frappe.route_options = {};
	return { changed, controls: page.cam_map_route_values };
}

function read_filter_controls(page) {
	const host = page.main.get(0);
	page.cam_map_options = Object.assign(
		{ camera: null, vehicle: null, event: null },
		page.cam_map_options || {}
	);
	page.cam_map_options.camera = clean_route_value(host.querySelector(".cam-map-camera").value);
	page.cam_map_options.vehicle = clean_route_value(host.querySelector(".cam-map-vehicle").value);
	page.cam_map_options.event = clean_route_value(host.querySelector(".cam-map-event").value);
}

function queue_map_reload(page) {
	clearTimeout(page.cam_map_reload_timer);
	page.cam_map_reload_timer = window.setTimeout(() => load_map(page), 350);
}

function update_filter_note(page) {
	const { camera, vehicle, event } = page.cam_map_options || {};
	const parts = [];
	if (camera) parts.push(`${__("Camera")}: ${camera}`);
	if (vehicle) parts.push(`${__("Vehicle")}: ${vehicle}`);
	if (event) parts.push(`${__("Event")}: ${event}`);
	const summary = parts.length
		? `${__("Active filters")} — ${parts.join(" • ")}`
		: __("Showing all matching records (no camera, vehicle, or event filter active).");
	if (page.$filter_note) page.$filter_note.text(summary);
}

function tile_template(layer, variant, context) {
	const origin = context?.origin || pageOrigin();
	return `${origin}/api/method/camera_archive_management.api.tiles.tile?layer=${encodeURIComponent(layer)}&variant=${encodeURIComponent(variant)}&z={z}&x={x}&y={y}`;
}

function pageOrigin() {
	return window.location.origin || `${window.location.protocol}//${window.location.host}`;
}

function set_basemap(page) {
	const selected = page.main.find(".cam-map-layer").val() || "standard";
	const map = page.cam_map;
	Object.values(page.cam_base_layers).forEach((layer) => {
		if (map.hasLayer(layer)) map.removeLayer(layer);
	});
	if (page.cam_overlay && map.hasLayer(page.cam_overlay)) map.removeLayer(page.cam_overlay);
	const attributions = { standard: "© OpenStreetMap contributors", aerial: "© Esri", hybrid: "© Esri" };
	const base = page.cam_base_layers[selected] || L.tileLayer(tile_template(selected, "base", page.cam_map_context), {
		minZoom: 0, maxZoom: 19, attribution: attributions[selected], crossOrigin: false
	});
	page.cam_base_layers[selected] = base;
	base.addTo(map);
	if (selected === "hybrid") {
		page.cam_overlay = page.cam_overlay || L.tileLayer(tile_template("hybrid", "overlay", page.cam_map_context), {
			minZoom: 0, maxZoom: 19, attribution: "© Esri", opacity: 1
		});
		page.cam_overlay.addTo(map);
	}
}

function node(tag, class_name, text) {
	const element = document.createElement(tag);
	if (class_name) element.className = class_name;
	if (text !== undefined && text !== null) element.textContent = String(text);
	return element;
}

function image_node(url, alt, class_name) {
	if (!url || !/^\/(?:private\/)?files\//.test(url)) return null;
	const image = node("img", class_name);
	image.src = url;
	image.alt = alt || "";
	image.loading = "lazy";
	image.referrerPolicy = "same-origin";
	return image;
}

function camera_icon(camera) {
	const shell = node("div", "cam-pin cam-camera-pin");
	const primary = camera.photos.find((photo) => photo.primary) || camera.photos[0];
	const photo = primary && image_node(primary.url, camera.label, "cam-pin-image");
	if (photo) shell.append(photo);
	else shell.append(node("span", "cam-pin-fallback", "◉"));
	if (camera.photos.length > 1) shell.append(node("span", "cam-pin-count", camera.photos.length));
	return L.divIcon({ className: "cam-leaflet-icon", html: shell, iconSize: [48, 48], iconAnchor: [24, 24], popupAnchor: [0, -24] });
}

function vehicle_icon(movement) {
	const shell = node("div", "cam-pin cam-vehicle-pin");
	const image = image_node(movement.vehicle_image, movement.vehicle_name, "cam-pin-image");
	if (image) shell.append(image);
	else shell.append(node("span", "cam-pin-fallback", "🚘"));
	return L.divIcon({ className: "cam-leaflet-icon", html: shell, iconSize: [44, 44], iconAnchor: [22, 22], popupAnchor: [0, -22] });
}

function camera_popup(camera) {
	const root = node("div", "cam-map-popup");
	root.append(node("h4", "", camera.label));
	if (camera.address) root.append(node("p", "cam-popup-address", camera.address));
	root.append(node("p", "cam-popup-meta", [camera.camera_type, camera.area].filter(Boolean).join(" · ") || __("Camera")));
	if (camera.photos.length) {
		let index = Math.max(0, camera.photos.findIndex((photo) => photo.primary));
		const frame = node("div", "cam-gallery-frame");
		const photo = node("img", "cam-gallery-image");
		photo.alt = camera.label;
		const caption = node("div", "cam-gallery-caption");
		const count = node("span", "cam-gallery-count");
		const update = () => {
			const current = camera.photos[index];
			photo.src = current.url;
			caption.textContent = current.caption || current.description || "";
			count.textContent = `${index + 1} / ${camera.photos.length}`;
		};
		frame.append(photo);
		if (camera.photos.length > 1) {
			const controls = node("div", "cam-gallery-controls");
			const previous = node("button", "btn btn-xs btn-default", "‹");
			const next = node("button", "btn btn-xs btn-default", "›");
			previous.type = next.type = "button";
			previous.setAttribute("aria-label", __("Previous photo"));
			next.setAttribute("aria-label", __("Next photo"));
			previous.addEventListener("click", () => { index = (index - 1 + camera.photos.length) % camera.photos.length; update(); });
			next.addEventListener("click", () => { index = (index + 1) % camera.photos.length; update(); });
			controls.append(previous, count, next);
			root.append(frame, controls, caption);
		} else {
			root.append(frame, caption);
		}
		update();
	}
	const actions = node("div", "cam-popup-actions");
	const open = node("button", "btn btn-xs btn-primary", __("Open camera"));
	open.type = "button";
	open.addEventListener("click", () => frappe.set_route("Form", "Camera", camera.name));
	actions.append(open);
	root.append(actions);
	return root;
}

function movement_popup(movement) {
	const root = node("div", "cam-map-popup");
	root.append(node("h4", "", movement.vehicle_name || __("Unidentified vehicle")));
	root.append(node("p", "cam-popup-meta", `${movement.motion_type} · ${movement.detected_at}`));
	if (movement.vehicle_number) root.append(node("p", "", `${__("Vehicle number")}: ${movement.vehicle_number}`));
	if (movement.address) root.append(node("p", "cam-popup-address", movement.address));
	if (movement.notes) root.append(node("p", "", movement.notes));
	const open = node("button", "btn btn-xs btn-primary", __("Open motion event"));
	open.type = "button";
	open.addEventListener("click", () => frappe.set_route("Form", "Motion Event", movement.name));
	root.append(open);
	return root;
}

function add_movement_card(page, movement) {
	const card = node("button", "cam-movement-card");
	card.type = "button";
	const image = image_node(movement.vehicle_image, movement.vehicle_name, "cam-movement-image");
	card.append(image || node("span", "cam-movement-image cam-vehicle-preview-fallback", "🚘"));
	const text = node("span", "cam-movement-text");
	text.append(node("strong", "", movement.vehicle_name || __("Unidentified vehicle")));
	text.append(node("span", "", `${movement.motion_type} · ${movement.detected_at}`));
	if (movement.vehicle_number) text.append(node("span", "", movement.vehicle_number));
	card.append(text);
	card.addEventListener("click", () => {
		page.cam_map.setView([Number(movement.latitude), Number(movement.longitude)], Math.max(page.cam_map.getZoom(), 14));
		const marker = page.cam_markers.getLayers().find((item) => item.cam_record_name === movement.name);
		if (marker) marker.openPopup();
	});
	page.main.find(".cam-map-movement-list").append(card);
}

async function load_map(page) {
	const request_id = (page.cam_map_request_id || 0) + 1;
	page.cam_map_request_id = request_id;
	read_filter_controls(page);
	update_filter_note(page);
	set_basemap(page);
	page.cam_markers.clearLayers();
	page.cam_tracks.clearLayers();
	const host = page.main.get(0);
	const summary = host.querySelector(".cam-map-summary");
	const movementList = host.querySelector(".cam-map-movement-list");
	movementList.replaceChildren();
	summary.textContent = __("Loading cameras and movements…");
	const args = {
		camera: page.cam_map_options.camera || undefined,
		vehicle: page.cam_map_options.vehicle || undefined,
		event: page.cam_map_options.event || undefined,
		start: host.querySelector(".cam-map-from").value || undefined,
		end: host.querySelector(".cam-map-to").value || undefined
	};
	try {
		const response = await frappe.call({ method: "camera_archive_management.api.map.map_payload", args, type: "GET" });
		if (request_id !== page.cam_map_request_id) return;
		const data = response.message || { cameras: [], movements: [] };
		const positions = [];
		for (const camera of data.cameras || []) {
			const marker = L.marker([Number(camera.latitude), Number(camera.longitude)], { icon: camera_icon(camera) });
			marker.cam_record_name = camera.name;
			marker.bindPopup(camera_popup(camera), { maxWidth: 320, minWidth: 220 });
			page.cam_markers.addLayer(marker);
			positions.push([Number(camera.latitude), Number(camera.longitude)]);
		}
		const tracks = new Map();
		for (const movement of data.movements || []) {
			const point = [Number(movement.latitude), Number(movement.longitude)];
			const marker = L.marker(point, { icon: vehicle_icon(movement), zIndexOffset: 500 });
			marker.cam_record_name = movement.name;
			marker.bindPopup(movement_popup(movement), { maxWidth: 300 });
			page.cam_markers.addLayer(marker);
			positions.push(point);
			const key = movement.vehicle || `unassigned:${movement.camera}`;
			if (!tracks.has(key)) tracks.set(key, []);
			tracks.get(key).push(point);
			add_movement_card(page, movement);
		}
		for (const points of tracks.values()) {
			if (points.length > 1) L.polyline(points, { color: "#f97316", weight: 3, opacity: 0.65 }).addTo(page.cam_tracks);
		}
		summary.textContent = __("{0} cameras · {1} vehicle movements", [data.cameras.length, data.movements.length]);
		if (positions.length === 1) page.cam_map.setView(positions[0], 14);
		else if (positions.length > 1) page.cam_map.fitBounds(L.latLngBounds(positions).pad(0.12), { maxZoom: 14 });
		else page.cam_map.setView([52.37, 4.90], 5);
	} catch (error) {
		if (request_id !== page.cam_map_request_id) return;
		summary.textContent = __("Map data could not be loaded. Check Camera/Motion Event read permissions and the server logs.");
		frappe.msgprint({ title: __("Camera map"), message: error.message || __("Request failed"), indicator: "red" });
	}
}
