let cam_map_leaflet;
let cam_map_leaflet_promise;
let cam_offline_db_promise;

function require_map_leaflet_css() {
	const href = new URL("/assets/camera_archive_management/vendor/leaflet/leaflet.css", window.location.origin).href;
	const existing = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).find(
		(link) => link.href === href
	);
	if (existing) return Promise.resolve();
	return new Promise((resolve, reject) => {
		const link = document.createElement("link");
		link.rel = "stylesheet";
		link.href = href;
		link.onload = resolve;
		link.onerror = () => reject(new Error("The local Camera Archive Leaflet stylesheet did not load."));
		document.head.appendChild(link);
	});
}

function require_map_leaflet() {
	if (cam_map_leaflet) return Promise.resolve(cam_map_leaflet);
	if (!cam_map_leaflet_promise) {
		const previous_leaflet = window.L;
		cam_map_leaflet_promise = Promise.all([
			require_map_leaflet_css(),
			frappe.require("/assets/camera_archive_management/vendor/leaflet/leaflet.js")
		]).then(() => {
			const leaflet = window.L;
			window.L = previous_leaflet;
			if (!leaflet || typeof leaflet.map !== "function") {
				throw new Error("The local Camera Archive Leaflet runtime did not load.");
			}
			cam_map_leaflet = leaflet;
			return leaflet;
		}).catch((error) => {
			window.L = previous_leaflet;
			cam_map_leaflet_promise = null;
			throw error;
		});
	}
	return cam_map_leaflet_promise;
}

frappe.pages["camera-archive-map"].on_page_load = function (wrapper) {
	require_map_leaflet().then((leaflet) => initialize_map_page(wrapper, leaflet)).catch((error) => {
		frappe.msgprint({ title: __("Camera map"), message: error.message, indicator: "red" });
	});
};

function initialize_map_page(wrapper, leaflet) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Camera Archive Map"), single_column: true });
	page.cam_leaflet = leaflet;
	page.set_primary_action(__("Refresh"), () => load_map(page, { force: true }), "refresh");
	page.cam_map_options = Object.assign(
		{ camera: null, vehicle: null, event: null, camera_status: null, area: null },
		page.cam_map_options || {}
	);
	page.cam_map_context = {
		host: window.location.host,
		origin: window.location.origin || `${window.location.protocol}//${window.location.host}`
	};
	page.cam_offline_enabled = read_offline_opt_in(page);
	const route_state = sync_route_filters_to_page(page, { force: true });
	const host = page.main.get(0);
	host.innerHTML = `
		<div class="cam-map-toolbar">
		<label>${__("Map view")} <select class="form-control cam-map-mode"><option value="movement">${__("Vehicle movements")}</option><option value="camera">${__("Camera locations")}</option></select></label>
		<label>${__("Start date/time")} <input class="form-control cam-map-from" type="datetime-local"></label>
		<label>${__("End date/time")} <input class="form-control cam-map-to" type="datetime-local"></label>
		<label>${__("Date range preset")} <select class="form-control cam-map-date-preset"><option value="custom">${__("Custom range")}</option><option value="24h">${__("Last 24 hours")}</option><option value="7d">${__("Last 7 days")}</option><option value="30d">${__("Last 30 days")}</option><option value="all">${__("All time")}</option></select></label>
		<div class="cam-map-link-filter" data-cam-link="camera"></div>
		<div class="cam-map-link-filter" data-cam-link="vehicle"></div>
		<div class="cam-map-link-filter" data-cam-link="event"></div>
		<label>${__("Camera status")} <select class="form-control cam-map-status">
				<option value="">${__("Active (default)")}</option>
				<option value="all">${__("All statuses")}</option>
				<option value="Active">${__("Active")}</option>
				<option value="Inactive">${__("Inactive")}</option>
				<option value="Maintenance">${__("Maintenance")}</option>
		</select></label>
		<div class="cam-map-link-filter" data-cam-link="area"></div>
		<label>${__("Basemap")} <select class="form-control cam-map-layer">
				<option value="standard">${__("Standard")}</option>
				<option value="aerial">${__("Aerial")}</option>
				<option value="hybrid">${__("Hybrid")}</option>
			</select></label>
			<button class="btn btn-primary cam-map-apply">${__("Apply filters")}</button>
			<span class="cam-map-filter-note"></span>
			<span class="cam-map-tile-status text-muted" aria-live="polite"></span>
			<span class="cam-map-tile-telemetry text-muted" data-tile-telemetry aria-live="polite"></span>
		</div>
		<div class="cam-map-toolbox" role="toolbar" aria-label="${__("Map tools and layers")}">
			<div class="cam-map-toolgroup">
				<button class="btn btn-default cam-map-tool" data-tool="distance" type="button">${__("Measure distance")}</button>
				<button class="btn btn-default cam-map-tool" data-tool="area" type="button">${__("Measure area")}</button>
				<button class="btn btn-default cam-map-finish" type="button" disabled>${__("Finish")}</button>
				<button class="btn btn-default cam-map-cancel-tool" type="button">${__("Clear tools")}</button>
				<button class="btn btn-default cam-map-locate" type="button">${__("Locate me")}</button>
				<button class="btn btn-default cam-map-copy-coords" type="button" disabled>${__("Copy coordinates")}</button>
			</div>
			<div class="cam-map-toolgroup cam-map-layer-toggles">
				<label><input type="checkbox" class="cam-map-show-cameras" checked> ${__("Cameras")}</label>
				<label><input type="checkbox" class="cam-map-show-events" checked> ${__("Events")}</label>
				<label><input type="checkbox" class="cam-map-show-tracks" checked> ${__("Movement tracks")}</label>
				<label><input type="checkbox" class="cam-map-show-countries" checked> ${__("Country borders")}</label>
				<label class="cam-map-demo-toggle"><input type="checkbox" class="cam-map-include-demo"> ${__("Include synthetic demo records")}</label>
			<label class="cam-map-offline-toggle" title="${__("Stores the current filtered map snapshot, popup details and viewed images in this browser profile until cleared.")}"><input type="checkbox" class="cam-map-save-offline"> ${__("Save map snapshot, details and images offline")}</label>
			<button class="btn btn-default btn-xs cam-map-show-saved" type="button" ${page.cam_offline_enabled ? "" : "disabled"}>${__("Show saved popup details")}</button>
			<button class="btn btn-default btn-xs cam-map-clear-offline" type="button">${__("Clear offline data")}</button>
			<span class="cam-map-offline-status text-muted" aria-live="polite"></span>
			</div>
			<span class="cam-map-tool-status" aria-live="polite">${__("Click the map to inspect coordinates, or choose a measurement tool.")}</span>
			<div class="cam-map-playback">
				<button class="btn btn-default cam-map-play" type="button" disabled aria-label="${__("Play movement timeline")}">▶</button>
				<input class="cam-map-time" type="range" min="0" max="0" value="0" disabled aria-label="${__("Movement timeline")}">
				<output class="cam-map-time-label">${__("No events")}</output>
			</div>
		</div>
		<div class="cam-map-shell">
			<div class="cam-map-canvas" role="application" aria-label="${__("Camera and vehicle movement map")}"></div>
			<aside class="cam-map-sidebar">
				<section class="cam-map-insights" aria-label="${__("Map activity insights")}">
					<div class="cam-map-insight-heading">
						<div><span class="cam-map-eyebrow">${__("CAMERA ARCHIVE · FIELD INTELLIGENCE")}</span><h3>${__("Field pulse")}</h3></div>
						<span class="cam-map-window" data-insight-window></span>
					</div>
					<div class="cam-map-kpis">
						<article class="cam-map-kpi cam-kpi-camera"><span>${__("Cameras in view")}</span><strong data-kpi-cameras>—</strong><small>${__("in this view")}</small></article>
						<article class="cam-map-kpi cam-kpi-movement"><span>${__("Movements")}</span><strong data-kpi-movements>—</strong><small>${__("in selected window")}</small></article>
						<article class="cam-map-kpi cam-kpi-vehicles"><span>${__("Vehicles tracked")}</span><strong data-kpi-vehicles>—</strong><small>${__("unique records")}</small></article>
					</div>
					<div class="cam-map-chart-heading"><strong>${__("Daily movement rhythm")}</strong><span>${__("latest 14 days")}</span></div>
					<svg class="cam-map-activity-chart" viewBox="0 0 288 112" role="img" aria-label="${__("Daily camera movement activity chart")}"></svg>
					<div class="cam-map-mix" aria-label="${__("Movement type breakdown")}">
						<div class="cam-map-mix-bar" role="img" aria-label="${__("Movement type breakdown")}"><span class="cam-mix-entry"></span><span class="cam-mix-exit"></span><span class="cam-mix-other"></span></div>
						<div class="cam-map-mix-legend"><span><i class="cam-dot-entry"></i>${__("Entry")}</span><span><i class="cam-dot-exit"></i>${__("Exit")}</span><span data-mix-counts></span></div>
					</div>
					<div class="cam-map-summary text-muted">${__("Loading cameras and movements…")}</div>
				</section>
				<div class="cam-map-movement-list"></div>
			</aside>
		</div>`;

	const now = new Date();
	const default_start_date = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
	page.cam_map_mode = route_state.controls.view || page.cam_map_mode || "movement";
	host.querySelector(".cam-map-mode").value = page.cam_map_mode;
	host.querySelector(".cam-map-from").value = route_datetime_value(route_state.controls.start, local_datetime_value(default_start_date));
	host.querySelector(".cam-map-to").value = route_datetime_value(route_state.controls.end, local_datetime_value(now), true);
	initialize_map_link_controls(page);
	set_map_link_value(page, "camera", page.cam_map_options.camera || "");
	set_map_link_value(page, "vehicle", page.cam_map_options.vehicle || "");
	set_map_link_value(page, "event", page.cam_map_options.event || "");
	set_map_link_value(page, "area", page.cam_map_options.area || "");
	host.querySelector(".cam-map-status").value = page.cam_map_options.camera_status || "";
	if (["standard", "aerial", "hybrid"].includes(route_state.controls.layer)) {
		host.querySelector(".cam-map-layer").value = route_state.controls.layer;
	}
	page.$filter_note = $(host.querySelector(".cam-map-filter-note"));
	page.cam_tile_status = host.querySelector(".cam-map-tile-status");
	page.cam_tile_errors = 0;
	page.cam_tile_telemetry = host.querySelector("[data-tile-telemetry]");
	const offlineToggle = host.querySelector(".cam-map-save-offline");
	offlineToggle.checked = page.cam_offline_enabled;
	if (!window.indexedDB) {
		page.cam_offline_enabled = false;
		offlineToggle.checked = false;
		offlineToggle.disabled = true;
		host.querySelector(".cam-map-show-saved").disabled = true;
		set_offline_status(page, __("This browser does not provide persistent offline storage."));
	} else {
		set_offline_status(page);
	}
	host.querySelector(".cam-map-save-offline").addEventListener("change", async (event) => {
		page.cam_offline_enabled = event.target.checked;
		host.querySelector(".cam-map-show-saved").disabled = !page.cam_offline_enabled;
		write_offline_opt_in(page, page.cam_offline_enabled);
		if (!page.cam_offline_enabled) {
			await clear_offline_namespace(page);
			page.cam_using_saved_details = false;
			if (page.cam_current_map_data) render_map_payload(page, page.cam_current_map_data, { fit: false });
			update_filter_note(page);
		} else if (navigator.onLine) {
			load_map(page, { force: true });
		}
		set_offline_status(page);
	});
	host.querySelector(".cam-map-show-saved").addEventListener("click", () => show_cached_popup_details(page));
	host.querySelector(".cam-map-clear-offline").addEventListener("click", async () => {
		page.cam_offline_enabled = false;
		host.querySelector(".cam-map-save-offline").checked = false;
		host.querySelector(".cam-map-show-saved").disabled = true;
		write_offline_opt_in(page, false);
		await clear_offline_namespace(page);
		page.cam_using_saved_details = false;
		if (page.cam_current_map_data) render_map_payload(page, page.cam_current_map_data, { fit: false });
		update_filter_note(page);
		set_offline_status(page, __("Offline images and details cleared from this browser profile."));
	});
	set_tile_status(page, __("Map tiles use the shared Siraj server cache."));
	if (!page.cam_network_listener) {
		page.cam_was_online = navigator.onLine;
		page.cam_network_listener = () => {
			const cameOnline = navigator.onLine && !page.cam_was_online;
			page.cam_was_online = navigator.onLine;
			set_tile_status(page, navigator.onLine
				? __("Browser is online; missing tiles use the configured server provider when enabled.")
				: __("Browser is offline; the Bench server must remain reachable to use cached tiles."));
			set_offline_status(page);
			update_tile_telemetry(page);
			if (cameOnline) load_map(page, { force: true });
		};
		window.addEventListener("online", page.cam_network_listener);
		window.addEventListener("offline", page.cam_network_listener);
	}
	update_filter_note(page);
	page.cam_map = leaflet.map(host.querySelector(".cam-map-canvas"), { zoomControl: true }).setView([52.37, 4.90], 5);
	if (!page.cam_map_route_listener && frappe.router?.on) {
		page.cam_map_route_listener = () => {
			const current_route = frappe.get_route() || [];
			if (current_route[0] !== "camera-archive-map") {
				page.cam_map_was_away = true;
				page.cam_route_push_signature = null;
				if (page.cam_playback_timer) toggle_movement_playback(page);
			}
		};
		frappe.router.on("change", page.cam_map_route_listener);
	}
	page.cam_base_layers = {};
	page.cam_overlay = null;
	page.cam_camera_markers = leaflet.featureGroup().addTo(page.cam_map);
	page.cam_event_markers = leaflet.featureGroup().addTo(page.cam_map);
	page.cam_tracks = leaflet.featureGroup().addTo(page.cam_map);
	page.cam_measurements = leaflet.featureGroup().addTo(page.cam_map);
	page.cam_location_layer = leaflet.featureGroup().addTo(page.cam_map);
	page.cam_country_layer = leaflet.geoJSON(null, {
		style: () => ({ color: "#0f766e", weight: 1.4, opacity: 0.72, fillColor: "#14b8a6", fillOpacity: 0.025, dashArray: "3 3" }),
		onEachFeature: (feature, layer) => {
			if (feature.properties?.label) layer.bindTooltip(feature.properties.label, { sticky: true, direction: "auto" });
		}
	}).addTo(page.cam_map);
	page.cam_tool_mode = null;
	page.cam_measure_points = [];
	page.cam_last_coordinate = null;
	page.cam_movement_data = [];
	host.querySelector(".cam-map-apply").addEventListener("click", () => {
		read_filter_controls(page);
		update_filter_note(page);
		load_map(page);
	});
	host.querySelector(".cam-map-layer").addEventListener("change", () => {
		set_basemap(page);
		sync_page_route_to_controls(page);
		update_filter_note(page);
	});
	host.querySelector(".cam-map-status").addEventListener("change", () => {
		read_filter_controls(page);
		update_filter_note(page);
		load_map(page);
	});
	host.querySelectorAll(".cam-map-tool").forEach((button) => {
		button.addEventListener("click", () => start_map_measurement(page, button.dataset.tool));
	});
	host.querySelector(".cam-map-finish").addEventListener("click", () => finish_map_measurement(page));
	host.querySelector(".cam-map-cancel-tool").addEventListener("click", () => clear_map_tools(page));
	host.querySelector(".cam-map-copy-coords").addEventListener("click", () => copy_map_coordinates(page));
	host.querySelector(".cam-map-locate").addEventListener("click", () => locate_map_user(page));
	host.querySelector(".cam-map-show-cameras").addEventListener("change", (event) => set_group_visibility(page, page.cam_camera_markers, event.target.checked));
	host.querySelector(".cam-map-show-events").addEventListener("change", (event) => set_group_visibility(page, page.cam_event_markers, event.target.checked));
	host.querySelector(".cam-map-show-tracks").addEventListener("change", (event) => set_group_visibility(page, page.cam_tracks, event.target.checked));
	host.querySelector(".cam-map-mode").addEventListener("change", () => {
		page.cam_map_mode = host.querySelector(".cam-map-mode").value;
		apply_map_mode(page, { fit: true });
		sync_page_route_to_controls(page);
		update_filter_note(page);
	});
	host.querySelector(".cam-map-date-preset").addEventListener("change", (event) => apply_date_preset(page, event.target.value));
	host.querySelector(".cam-map-show-countries").addEventListener("change", (event) => set_country_visibility(page, event.target.checked));
	host.querySelector(".cam-map-time").addEventListener("input", () => render_movement_slice(page));
	host.querySelector(".cam-map-play").addEventListener("click", () => toggle_movement_playback(page));
	page.cam_map.on("zoomend", () => update_tile_telemetry(page));
	page.cam_map.on("mousemove", (event) => update_coordinate_readout(page, event.latlng));
	page.cam_map.on("click", (event) => handle_map_click(page, event.latlng));
	page.cam_map.on("dblclick", () => {
		if (page.cam_tool_mode) finish_map_measurement(page);
	});
	load_tile_config(page);
	load_country_boundaries(page);
	for (const control of Object.values(page.cam_link_controls || {})) {
		control.$input.on("change awesomplete-selectcomplete", () => {
			read_filter_controls(page);
			update_filter_note(page);
			load_map(page);
		});
		control.$input.on("keydown", (event) => {
			if (event.key === "Enter") {
				window.setTimeout(() => {
					read_filter_controls(page);
					update_filter_note(page);
					load_map(page);
				}, 0);
			}
		});
	}
	for (const selector of [".cam-map-from", ".cam-map-to"]) {
		host.querySelector(selector).addEventListener("change", () => {
			host.querySelector(".cam-map-date-preset").value = "custom";
			load_map(page);
		});
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
	set_map_link_value(page, "camera", page.cam_map_options.camera || "");
	set_map_link_value(page, "vehicle", page.cam_map_options.vehicle || "");
	set_map_link_value(page, "event", page.cam_map_options.event || "");
	set_map_link_value(page, "area", page.cam_map_options.area || "");
	host.querySelector(".cam-map-status").value = page.cam_map_options.camera_status || "";
	page.cam_map_mode = route_state.controls.view || "movement";
	host.querySelector(".cam-map-mode").value = page.cam_map_mode;
	apply_map_mode(page);
	const now = new Date();
	host.querySelector(".cam-map-from").value = route_datetime_value(route_state.controls.start, local_datetime_value(new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)));
	host.querySelector(".cam-map-to").value = route_datetime_value(route_state.controls.end, local_datetime_value(now), true);
	host.querySelector(".cam-map-date-preset").value = !host.querySelector(".cam-map-from").value && !host.querySelector(".cam-map-to").value ? "all" : "custom";
	if (["standard", "aerial", "hybrid"].includes(route_state.controls.layer)) {
		host.querySelector(".cam-map-layer").value = route_state.controls.layer;
	}
	update_filter_note(page);
	load_map(page);
};

const CAM_MAP_FILTER_KEYS = ["camera", "vehicle", "event", "camera_status", "area"];
const CAM_MAP_ROUTE_KEYS = [...CAM_MAP_FILTER_KEYS, "start", "end", "layer", "view"];

function clean_route_value(value) {
	if (value === undefined || value === null) return null;
	const text = String(value).trim();
	return text || null;
}

function local_datetime_value(date) {
	const pad = (value) => String(value).padStart(2, "0");
	return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function route_datetime_value(value, fallback, end = false) {
	if (value === "all") return "";
	if (!value) return fallback;
	if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return `${value}T${end ? "23:59" : "00:00"}`;
	return value;
}

function map_datetime_arg(value) {
	if (!value) return undefined;
	const instant = new Date(value);
	return Number.isNaN(instant.getTime()) ? value : instant.toISOString();
}

function initialize_map_link_controls(page) {
	page.cam_link_controls = {};
	const definitions = [
		["camera", "Camera ID", "Camera"],
		["vehicle", "CAM Vehicle ID", "CAM Vehicle"],
		["event", "Motion Event ID", "Motion Event"],
		["area", "Camera Area ID", "Camera Area"],
	];
	for (const [key, label, doctype] of definitions) {
		const parent = page.main.get(0).querySelector(`[data-cam-link="${key}"]`);
		const control = frappe.ui.form.make_control({
			parent: $(parent),
			df: { fieldtype: "Link", fieldname: `cam_map_${key}`, label: __(label), options: doctype },
			render_input: true,
		});
		control.$input.addClass(`cam-map-${key}`);
		control.$input.attr("autocomplete", "off");
		page.cam_link_controls[key] = control;
	}
}

function get_map_link_value(page, key) {
	return page.cam_link_controls?.[key]?.get_value?.() || "";
}

function set_map_link_value(page, key, value) {
	const control = page.cam_link_controls?.[key];
	if (control) control.set_value(value || "");
}

function apply_date_preset(page, preset) {
	const host = page.main.get(0);
	const end = new Date();
	let start = null;
	if (preset === "24h") start = new Date(end.getTime() - 24 * 60 * 60 * 1000);
	else if (preset === "7d") start = new Date(end.getTime() - 7 * 24 * 60 * 60 * 1000);
	else if (preset === "30d") start = new Date(end.getTime() - 30 * 24 * 60 * 60 * 1000);
	if (preset === "all") {
		host.querySelector(".cam-map-from").value = "";
		host.querySelector(".cam-map-to").value = "";
	} else if (start) {
		host.querySelector(".cam-map-from").value = local_datetime_value(start);
		host.querySelector(".cam-map-to").value = local_datetime_value(end);
	} else {
		return;
	}
	load_map(page);
}

function apply_map_mode(page, { fit = false } = {}) {
	const host = page.main.get(0);
	const movementMode = (page.cam_map_mode || host.querySelector(".cam-map-mode")?.value) !== "camera";
	page.cam_map_mode = movementMode ? "movement" : "camera";
	const cameras = host.querySelector(".cam-map-show-cameras");
	const events = host.querySelector(".cam-map-show-events");
	const tracks = host.querySelector(".cam-map-show-tracks");
	cameras.disabled = movementMode;
	events.disabled = !movementMode;
	tracks.disabled = !movementMode;
	cameras.checked = !movementMode;
	events.checked = movementMode;
	tracks.checked = movementMode;
	host.querySelector(".cam-map-playback").hidden = !movementMode;
	set_group_visibility(page, page.cam_camera_markers, !movementMode);
	set_group_visibility(page, page.cam_event_markers, movementMode);
	set_group_visibility(page, page.cam_tracks, movementMode);
	if (page.cam_movement_data) render_movement_slice(page);
	if (fit && page.cam_current_map_data) {
		const rows = movementMode ? page.cam_movement_data : (page.cam_current_map_data.cameras || []);
		const positions = rows.map((row) => [Number(row.latitude), Number(row.longitude)])
			.filter((point) => point.every(Number.isFinite));
		if (positions.length === 1) page.cam_map.setView(positions[0], 14);
		else if (positions.length > 1) page.cam_map.fitBounds(page.cam_leaflet.latLngBounds(positions).pad(0.12), { maxZoom: 14 });
	}
}

function sync_route_filters_to_page(page, { force = false } = {}) {
	page.cam_map_options = Object.assign(
		{ camera: null, vehicle: null, event: null, camera_status: null, area: null },
		page.cam_map_options || {}
	);
	page.cam_map_route_values = Object.assign(
		{ start: null, end: null, layer: null, view: null },
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
	const has_route_controls = ["start", "end", "layer", "view"].some(
		(key) => Object.hasOwn(route_options, key) || Object.hasOwn(from_route, key)
	);
	const identity = JSON.stringify(route);
	const route_changed = identity !== page.cam_map_route_identity;
	const route_was_away = Boolean(page.cam_map_was_away);
	const has_page_route_options = CAM_MAP_ROUTE_KEYS.some((key) => Object.hasOwn(route_options, key));
	let changed = route_changed || route_was_away || has_page_route_options || force;

	if (has_route_filters || has_positional_filters) {
		for (const key of CAM_MAP_FILTER_KEYS) {
			const value = Object.hasOwn(route_options, key) ? route_options[key] : from_route[key];
			const normalized = clean_route_value(value);
			if (page.cam_map_options[key] !== normalized) changed = true;
			page.cam_map_options[key] = normalized;
		}
	} else if (route_changed || route_was_away || has_page_route_options || force) {
		for (const key of CAM_MAP_FILTER_KEYS) {
			if (page.cam_map_options[key] !== null) changed = true;
			page.cam_map_options[key] = null;
		}
	}

	if (has_route_controls || route_changed || route_was_away || has_page_route_options || force) {
		for (const key of ["start", "end", "layer", "view"]) {
			const value = Object.hasOwn(route_options, key) ? route_options[key] : from_route[key];
			const normalized = clean_route_value(value);
			if (page.cam_map_route_values[key] !== normalized) changed = true;
			page.cam_map_route_values[key] = normalized;
		}
	}
	page.cam_map_route_identity = identity;
	page.cam_map_was_away = false;
	if (has_page_route_options) {
		const remaining_options = { ...route_options };
		for (const key of CAM_MAP_ROUTE_KEYS) delete remaining_options[key];
		frappe.route_options = remaining_options;
	}
	return { changed, controls: page.cam_map_route_values };
}

function sync_page_route_to_controls(page) {
	const current = frappe.get_route() || [];
	if (current[0] !== "camera-archive-map") return;
	const host = page.main.get(0);
	const next = ["camera-archive-map"];
	const values = {
		camera: clean_route_value(page.cam_map_options.camera),
		vehicle: clean_route_value(page.cam_map_options.vehicle),
		event: clean_route_value(page.cam_map_options.event),
		camera_status: clean_route_value(page.cam_map_options.camera_status),
		area: clean_route_value(page.cam_map_options.area),
		start: clean_route_value(host.querySelector(".cam-map-from").value) || "all",
		end: clean_route_value(host.querySelector(".cam-map-to").value) || "all",
		layer: clean_route_value(host.querySelector(".cam-map-layer").value),
		view: clean_route_value(host.querySelector(".cam-map-mode").value),
	};
	for (const key of CAM_MAP_ROUTE_KEYS) {
		if (values[key] !== null) next.push(key, values[key]);
	}
	if (JSON.stringify(current) === JSON.stringify(next)) {
		page.cam_route_push_signature = null;
		return;
	}
	const signature = JSON.stringify(next);
	if (page.cam_route_push_signature === signature) return;
	page.cam_route_push_signature = signature;
	frappe.set_route(...next);
}

function read_filter_controls(page) {
	const host = page.main.get(0);
	page.cam_map_options = Object.assign(
		{ camera: null, vehicle: null, event: null, camera_status: null, area: null },
		page.cam_map_options || {}
	);
	page.cam_map_options.camera = clean_route_value(get_map_link_value(page, "camera"));
	page.cam_map_options.vehicle = clean_route_value(get_map_link_value(page, "vehicle"));
	page.cam_map_options.event = clean_route_value(get_map_link_value(page, "event"));
	page.cam_map_options.camera_status = clean_route_value(host.querySelector(".cam-map-status").value);
	page.cam_map_options.area = clean_route_value(get_map_link_value(page, "area"));
	page.cam_map_mode = host.querySelector(".cam-map-mode").value || "movement";
}

function queue_map_reload(page) {
	clearTimeout(page.cam_map_reload_timer);
	page.cam_map_reload_timer = window.setTimeout(() => load_map(page), 350);
}

function update_filter_note(page) {
	if (page.cam_using_saved_details) {
		if (page.$filter_note) page.$filter_note.text(__("Current filters are bypassed: showing only previously viewed saved records."));
		return;
	}
	const { camera, vehicle, event, camera_status, area } = page.cam_map_options || {};
	const parts = [];
	if (camera) parts.push(`${__("Camera")}: ${camera}`);
	if (vehicle) parts.push(`${__("Vehicle")}: ${vehicle}`);
	if (event) parts.push(`${__("Event")}: ${event}`);
	if (camera_status) parts.push(`${__("Status")}: ${camera_status === "all" ? __("All statuses") : __(camera_status)}`);
	else parts.push(`${__("Status")}: ${camera ? __("not restricted") : __("Active (default)")}`);
	if (area) parts.push(`${__("Area")}: ${area}`);
	const host = page.main?.get(0);
	const dateFrom = host?.querySelector(".cam-map-from")?.value;
	const dateTo = host?.querySelector(".cam-map-to")?.value;
	if (dateFrom || dateTo) parts.push(`${__("Date range")}: ${dateFrom || "…"} — ${dateTo || "…"}`);
	parts.push(`${__("View")}: ${__(page.cam_map_mode === "camera" ? "Camera locations" : "Vehicle movements")}`);
	const layer = host?.querySelector(".cam-map-layer")?.value;
	if (layer) parts.push(`${__("Basemap")}: ${layer}`);
	const summary = parts.length
		? `${__("Active filters")} — ${parts.join(" • ")}`
		: __("Showing active cameras by default; no exact camera, vehicle, event, or area filter is active.");
	if (page.$filter_note) page.$filter_note.text(summary);
}

const CAM_MAP_OFFLINE_DB = "camera_archive_map_offline_v1";
const CAM_MAP_OFFLINE_STORES = ["snapshots", "images", "details"];
const CAM_MAP_OFFLINE_SNAPSHOT_LIMIT = 8;
const CAM_MAP_OFFLINE_PAYLOAD_LIMIT = 4 * 1024 * 1024;
const CAM_MAP_OFFLINE_IMAGE_LIMIT = 8 * 1024 * 1024;

function offline_namespace(page) {
	const user = frappe.session?.user || "Guest";
	return `${page.cam_map_context?.origin || pageOrigin()}|${user}`;
}

function offline_preference_key(page) {
	return `cam-map-offline-opt-in:${offline_namespace(page)}`;
}

function read_offline_opt_in(page) {
	try {
		return window.localStorage.getItem(offline_preference_key(page)) === "1";
	} catch (_error) {
		return false;
	}
}

function write_offline_opt_in(page, enabled) {
	try {
		if (enabled) window.localStorage.setItem(offline_preference_key(page), "1");
		else window.localStorage.removeItem(offline_preference_key(page));
	} catch (_error) {
		set_tool_status(page, __("Browser storage settings are unavailable."));
	}
}

function offline_db() {
	if (!window.indexedDB) return Promise.reject(new Error("IndexedDB is unavailable"));
	if (!cam_offline_db_promise) {
		cam_offline_db_promise = new Promise((resolve, reject) => {
			const request = window.indexedDB.open(CAM_MAP_OFFLINE_DB, 1);
			request.onupgradeneeded = () => {
				for (const store of CAM_MAP_OFFLINE_STORES) {
					if (!request.result.objectStoreNames.contains(store)) request.result.createObjectStore(store, { keyPath: "key" });
				}
			};
			request.onsuccess = () => {
				const database = request.result;
				database.onversionchange = () => {
					database.close();
					cam_offline_db_promise = null;
				};
				resolve(database);
			};
			request.onerror = () => {
				cam_offline_db_promise = null;
				reject(request.error || new Error("Could not open offline storage"));
			};
			request.onblocked = () => {
				cam_offline_db_promise = null;
				reject(new Error("Offline storage upgrade is blocked by another open tab"));
			};
		});
	}
	return cam_offline_db_promise;
}

function offline_get(store_name, key) {
	return offline_db().then((db) => new Promise((resolve, reject) => {
		const request = db.transaction(store_name, "readonly").objectStore(store_name).get(key);
		request.onsuccess = () => resolve(request.result || null);
		request.onerror = () => reject(request.error || new Error("Offline read failed"));
	}));
}

function offline_put(store_name, record) {
	return offline_db().then((db) => new Promise((resolve, reject) => {
		const transaction = db.transaction(store_name, "readwrite");
		transaction.objectStore(store_name).put(record);
		transaction.oncomplete = () => resolve();
		transaction.onerror = () => reject(transaction.error || new Error("Offline write failed"));
		transaction.onabort = () => reject(transaction.error || new Error("Offline write aborted"));
	}));
}

function offline_prune(store_name, namespace, keep, limit) {
	return offline_db().then((db) => new Promise((resolve, reject) => {
		const transaction = db.transaction(store_name, "readwrite");
		const store = transaction.objectStore(store_name);
		const request = store.getAll();
		request.onsuccess = () => {
			const rows = request.result.filter((row) => row.namespace === namespace).sort((a, b) => b.savedAt - a.savedAt);
			let total = 0;
			rows.forEach((row, index) => {
				total += row.size || 0;
				if (index >= keep || total > limit) store.delete(row.key);
			});
		};
		request.onerror = () => reject(request.error || new Error("Offline cache cleanup failed"));
		transaction.oncomplete = resolve;
		transaction.onerror = () => reject(transaction.error || new Error("Offline cache cleanup failed"));
	}));
}

function offline_clear_namespace(page) {
	return offline_db().then((db) => new Promise((resolve, reject) => {
		const namespace = offline_namespace(page);
		const transaction = db.transaction(CAM_MAP_OFFLINE_STORES, "readwrite");
		for (const store_name of CAM_MAP_OFFLINE_STORES) {
			const store = transaction.objectStore(store_name);
			const request = store.getAll();
			request.onsuccess = () => request.result
				.filter((row) => row.namespace === namespace)
				.forEach((row) => store.delete(row.key));
		}
		transaction.oncomplete = resolve;
		transaction.onerror = () => reject(transaction.error || new Error("Offline cache cleanup failed"));
	}));
}

async function clear_offline_namespace(page) {
	try {
		await offline_clear_namespace(page);
		for (const url of page.cam_object_urls || []) URL.revokeObjectURL(url);
		page.cam_object_urls = [];
	} catch (_error) {
		set_tool_status(page, __("Could not clear browser offline storage."));
	}
}

function stable_cache_signature(value) {
	if (Array.isArray(value)) return `[${value.map(stable_cache_signature).join(",")}]`;
	if (value && typeof value === "object") {
		return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stable_cache_signature(value[key])}`).join(",")}}`;
	}
	return JSON.stringify(value);
}

function cache_map_snapshot(page, args, data) {
	if (!page.cam_offline_enabled) return;
	try {
		const serialized = JSON.stringify(data);
		if (serialized.length > CAM_MAP_OFFLINE_PAYLOAD_LIMIT) {
			set_offline_status(page, __("Current map snapshot is too large to save offline."));
			return;
		}
		const namespace = offline_namespace(page);
		const key = `${namespace}|snapshot|${stable_cache_signature(args)}`;
		offline_put("snapshots", { key, namespace, signature: stable_cache_signature(args), args, data, savedAt: Date.now(), size: serialized.length })
			.then(() => offline_prune("snapshots", namespace, CAM_MAP_OFFLINE_SNAPSHOT_LIMIT, CAM_MAP_OFFLINE_PAYLOAD_LIMIT * 2))
			.catch(() => set_offline_status(page, __("Offline snapshot could not be saved; check browser storage.")));
	} catch (_error) {
		set_offline_status(page, __("Offline snapshot could not be saved."));
	}
}

async function read_map_snapshot(page, args) {
	if (!page.cam_offline_enabled) return null;
	try {
		return await offline_get("snapshots", `${offline_namespace(page)}|snapshot|${stable_cache_signature(args)}`);
	} catch (_error) {
		return null;
	}
}

async function offline_get_details(page) {
	try {
		const db = await offline_db();
		return await new Promise((resolve, reject) => {
			const request = db.transaction("details", "readonly").objectStore("details").getAll();
			request.onsuccess = () => resolve(request.result
				.filter((row) => row.namespace === offline_namespace(page))
				.sort((left, right) => right.savedAt - left.savedAt));
			request.onerror = () => reject(request.error || new Error("Could not read saved popup details"));
		});
	} catch (_error) {
		return [];
	}
}

async function show_cached_popup_details(page) {
	if (!page.cam_offline_enabled) return;
	const saved = await offline_get_details(page);
	const cameras = saved.filter((row) => row.kind === "camera").map((row) => row.record);
	const movements = saved.filter((row) => row.kind === "event").map((row) => row.record);
	if (!cameras.length && !movements.length) {
		set_offline_status(page, __("No popup details have been saved on this browser profile."));
		return;
	}
	page.cam_using_saved_details = true;
	page.cam_map_request_id = (page.cam_map_request_id || 0) + 1;
	page.cam_inflight_signature = null;
	page.cam_last_request_signature = null;
	const data = { cameras, movements };
	render_map_payload(page, data, { offline: true, savedAt: saved[0]?.savedAt || null });
	update_filter_note(page);
	set_offline_status(page, __("Showing previously viewed popup details only; these records are saved and may be stale."));
}

function cache_viewed_detail(page, kind, record) {
	if (!page.cam_offline_enabled || !record) return;
	const namespace = offline_namespace(page);
	const key = `${namespace}|${kind}|${record.name}`;
	offline_put("details", { key, namespace, kind, record, savedAt: Date.now(), size: JSON.stringify(record).length })
		.then(() => offline_prune("details", namespace, 80, CAM_MAP_OFFLINE_PAYLOAD_LIMIT))
		.catch(() => set_offline_status(page, __("Viewed detail could not be saved for offline use.")));
}

function set_offline_status(page, override) {
	const status = page.main?.get(0)?.querySelector(".cam-map-offline-status");
	if (!status) return;
	status.textContent = override || (page.cam_offline_enabled
		? (navigator.onLine
			? __("Offline saving is enabled for this user on this browser profile.")
			: __("Offline: showing only previously saved map details and images."))
		: __("Offline saving is off; viewed imagery and details are not stored on this device."));
}

function show_image_unavailable(image, page) {
	const unavailable = node("span", image.classList.contains("cam-pin-image") || image.classList.contains("cam-movement-image")
		? `${image.className} cam-image-unavailable`
		: `${image.className} cam-image-unavailable`,
		navigator.onLine ? __("Image unavailable") : __("Not saved for offline use"));
	unavailable.setAttribute("role", "img");
	unavailable.setAttribute("aria-label", unavailable.textContent);
	unavailable.title = unavailable.textContent;
	image.replaceWith(unavailable);
	if (page) set_offline_status(page);
}

function enqueue_image_task(page, task) {
	page.cam_image_queue = page.cam_image_queue || [];
	page.cam_image_active = page.cam_image_active || 0;
	page.cam_image_queue.push(task);
	const drain = () => {
		while (page.cam_image_active < 6 && page.cam_image_queue.length) {
			const next = page.cam_image_queue.shift();
			page.cam_image_active += 1;
			Promise.resolve().then(next).catch(() => {}).finally(() => {
				page.cam_image_active -= 1;
				drain();
			});
		}
	};
	drain();
}

function set_image_source(image, url, page) {
	const token = (image.cam_load_token || 0) + 1;
	const generation = page.cam_image_generation || 0;
	image.cam_load_token = token;
	const applyBlob = (blob) => {
		if (image.cam_load_token !== token || page.cam_image_generation !== generation) return;
		const objectUrl = URL.createObjectURL(blob);
		page.cam_object_urls = page.cam_object_urls || [];
		page.cam_object_urls.push(objectUrl);
		image.src = objectUrl;
	};
	if (!page.cam_offline_enabled) {
		if (!navigator.onLine) return show_image_unavailable(image, page);
		image.onerror = () => show_image_unavailable(image, page);
		image.src = url;
		return;
	}
	const imageKey = `${offline_namespace(page)}|image|${url}`;
	const loadCached = async () => {
		try {
			const cached = await offline_get("images", imageKey);
			if (cached?.blob) {
				applyBlob(cached.blob);
				return true;
			}
		} catch (_error) {
			// Continue to the network path while online.
		}
		return false;
	};
	if (!navigator.onLine) {
		loadCached().then((found) => { if (!found) show_image_unavailable(image, page); });
		return;
	}
	enqueue_image_task(page, async () => {
		if (!page.cam_offline_enabled) {
			image.onerror = () => show_image_unavailable(image, page);
			image.src = url;
			return;
		}
		try {
			const response = await fetch(url, { credentials: "same-origin", cache: "default" });
			if (!response.ok || !(response.headers.get("content-type") || "").toLowerCase().startsWith("image/")) {
				throw new Error("Image request failed");
			}
			const blob = await response.blob();
			if (image.cam_load_token !== token || page.cam_image_generation !== generation) return;
			applyBlob(blob);
			if (blob.size <= CAM_MAP_OFFLINE_IMAGE_LIMIT) {
				const namespace = offline_namespace(page);
				offline_put("images", { key: imageKey, namespace, url, blob, savedAt: Date.now(), size: blob.size })
					.then(() => offline_prune("images", namespace, 80, CAM_MAP_OFFLINE_PAYLOAD_LIMIT * 3))
					.catch(() => {});
			}
		} catch (_error) {
			if (!(await loadCached())) show_image_unavailable(image, page);
		}
	});
}

function tile_template(layer, variant, context) {
	const origin = context?.origin || pageOrigin();
	return `${origin}/api/method/camera_archive_management.api.tiles.tile?layer=${encodeURIComponent(layer)}&variant=${encodeURIComponent(variant)}&z={z}&x={x}&y={y}`;
}

function pageOrigin() {
	return window.location.origin || `${window.location.protocol}//${window.location.host}`;
}

function set_tile_status(page, message) {
	if (page.cam_tile_status && page.cam_tile_status.textContent !== message) {
		page.cam_tile_status.textContent = message;
	}
}

function update_tile_telemetry(page) {
	if (!page.cam_tile_telemetry || !page.cam_map) return;
	const layerId = page.cam_selected_tile_layer || page.main.get(0).querySelector(".cam-map-layer")?.value || "—";
	const config = page.cam_tile_config?.[layerId];
	const zoom = page.cam_map.getZoom();
	const nativeZoom = config?.maxZoom;
	const minNativeZoom = config?.minZoom;
	const zoomCue = Number.isFinite(nativeZoom) && Number.isFinite(minNativeZoom)
		? (zoom > nativeZoom
			? __("upscaled beyond native zoom {0}", [nativeZoom])
			: __("native zoom range {0}–{1}", [minNativeZoom, nativeZoom]))
		: __("native zoom limits unavailable");
	const overlay = page.cam_overlay && page.cam_map.hasLayer(page.cam_overlay) ? __("overlay on") : __("overlay off");
	const sourceMode = page.cam_tile_fetch_enabled
		? __("shared cache plus configured provider")
		: __("shared server cache only");
	const layerName = config?.label || __("shared Siraj cache/provider");
	page.cam_tile_telemetry.textContent = `${layerName} · ${__("tile source")}: ${sourceMode} · z${zoom} · ${zoomCue} · ${overlay}`;
}

function set_country_visibility(page, visible) {
	set_group_visibility(page, page.cam_country_layer, visible);
	if (visible) load_country_boundaries(page);
}

async function load_country_boundaries(page) {
	if (page.cam_country_data) return;
	if (page.cam_country_request) return page.cam_country_request;
	page.cam_country_request = frappe.call({
		method: "camera_archive_management.api.map.get_core_country_boundaries",
		type: "GET"
	}).then((response) => {
		page.cam_country_data = response.message || { type: "FeatureCollection", features: [] };
		page.cam_country_layer.clearLayers();
		page.cam_country_layer.addData(page.cam_country_data);
		if (!page.cam_country_data.features.length) {
			set_tool_status(page, __("No bundled country boundary data is available."));
		}
	}).catch((error) => {
		page.cam_country_request = null;
		const checkbox = page.main.get(0).querySelector(".cam-map-show-countries");
		checkbox.checked = false;
		set_group_visibility(page, page.cam_country_layer, false);
		set_tool_status(page, error.message || __("Country boundaries could not be loaded."));
	});
	return page.cam_country_request;
}

async function load_tile_config(page) {
	try {
		const response = await frappe.call({ method: "camera_archive_management.api.tiles.config", type: "GET" });
		const config = response.message || {};
		const layers = Array.isArray(config.layers) ? config.layers : [];
		if (!layers.length) {
			set_tile_status(page, __("No enabled Siraj raster layers are available; cached camera markers remain visible."));
			update_tile_telemetry(page);
			return;
		}
		page.cam_tile_config = Object.fromEntries(layers.map((layer) => [layer.id, layer]));
		page.cam_tile_fetch_enabled = Boolean(config.fetch_enabled);
		const select = page.main.get(0).querySelector(".cam-map-layer");
		const current = select.value;
		select.replaceChildren(...layers.map((layer) => {
			const option = document.createElement("option");
			option.value = layer.id;
			option.textContent = layer.label;
			return option;
		}));
		select.value = page.cam_tile_config[current] ? current : layers[0].id;
		if (config.fetch_enabled) {
			set_tile_status(page, __("Siraj online tile fetch and shared-cache writes are enabled."));
		} else {
			set_tile_status(page, __("Using the shared tile cache only; external fetching is disabled by settings."));
		}
		set_basemap(page);
	} catch (error) {
		set_tile_status(page, __("Tile settings could not be loaded; cached map tiles may still be available."));
		update_tile_telemetry(page);
	}
}

function bind_tile_status(page, layer) {
	if (layer.cam_status_bound) return layer;
	layer.cam_status_bound = true;
	layer.on("tileload", () => {
		page.cam_tile_errors = Math.max(0, (page.cam_tile_errors || 0) - 1);
		if (!page.cam_tile_errors) set_tile_status(page, __("Map tiles loaded from the shared server cache/provider."));
	});
	layer.on("tileerror", () => {
		page.cam_tile_errors = (page.cam_tile_errors || 0) + 1;
		set_tile_status(page, page.cam_tile_fetch_enabled
			? __("A tile is missing or unavailable; cached tiles remain usable and upstream retries are throttled.")
			: __("This tile is not in the shared Siraj cache; online provider fetching is disabled. Camera and movement markers still work."));
	});
	return layer;
}

function set_basemap(page) {
	const leaflet = page.cam_leaflet;
	const select = page.main.find(".cam-map-layer");
	let selected = select.val() || "standard";
	const layers = page.cam_tile_config || {};
	if (Object.keys(layers).length && !layers[selected]) {
		selected = Object.keys(layers)[0];
		select.val(selected);
	}
	const config = layers[selected];
	if (!config) return; // Wait for Siraj's authorized catalog; never guess a provider/attribution.
	const map = page.cam_map;
	Object.values(page.cam_base_layers).forEach((layer) => {
		if (map.hasLayer(layer)) map.removeLayer(layer);
	});
	if (page.cam_overlay && map.hasLayer(page.cam_overlay)) map.removeLayer(page.cam_overlay);
	const base = page.cam_base_layers[selected] || bind_tile_status(page, leaflet.tileLayer(
		tile_template(selected, "base", page.cam_map_context),
		{ minZoom: config.minZoom, maxNativeZoom: config.maxZoom, maxZoom: 22, attribution: config.attribution, crossOrigin: false }
	));
	page.cam_base_layers[selected] = base;
	base.addTo(map);
	page.cam_selected_tile_layer = selected;
	if (selected === "hybrid" && config.overlay !== false) {
		page.cam_overlay = page.cam_overlay || bind_tile_status(page, leaflet.tileLayer(
			tile_template("hybrid", "overlay", page.cam_map_context),
			{ minZoom: config.minZoom, maxNativeZoom: config.maxZoom, maxZoom: 22, attribution: config.attribution, opacity: 1 }
		));
		page.cam_overlay.addTo(map);
	}
	update_tile_telemetry(page);
}

function set_tool_status(page, message) {
	const status = page.main.get(0).querySelector(".cam-map-tool-status");
	if (status) status.textContent = message;
}

function set_group_visibility(page, group, visible) {
	if (visible && !page.cam_map.hasLayer(group)) group.addTo(page.cam_map);
	if (!visible && page.cam_map.hasLayer(group)) page.cam_map.removeLayer(group);
}

function start_map_measurement(page, mode) {
	page.cam_tool_mode = mode;
	page.cam_measure_points = [];
	page.cam_measurements.clearLayers();
	page.cam_map.doubleClickZoom.disable();
	page.main.get(0).querySelector(".cam-map-finish").disabled = true;
	set_tool_status(page, mode === "distance"
		? __("Distance tool: click points along a route, then choose Finish.")
		: __("Area tool: click polygon corners, then choose Finish."));
}

function handle_map_click(page, latlng) {
	page.cam_last_coordinate = latlng;
	page.cam_last_coordinate_text = `${String(latlng.lat)}, ${String(latlng.lng)}`;
	page.main.get(0).querySelector(".cam-map-copy-coords").disabled = false;
	if (!page.cam_tool_mode) return;
	page.cam_measure_points.push(latlng);
	const leaflet = page.cam_leaflet;
	page.cam_measurements.clearLayers();
	if (page.cam_tool_mode === "distance") {
		if (page.cam_measure_points.length >= 2) {
			const distance = page.cam_measure_points.slice(1).reduce(
				(total, point, index) => total + point.distanceTo(page.cam_measure_points[index]), 0
			);
			leaflet.polyline(page.cam_measure_points, { color: "#0f766e", weight: 4, dashArray: "8 6" }).addTo(page.cam_measurements);
			set_tool_status(page, __("{0} points · {1}", [page.cam_measure_points.length, format_distance(distance)]));
		}
	} else if (page.cam_measure_points.length >= 2) {
		if (page.cam_measure_points.length >= 3) {
			leaflet.polygon(page.cam_measure_points, { color: "#7c3aed", fillColor: "#8b5cf6", fillOpacity: 0.14, weight: 3 }).addTo(page.cam_measurements);
			set_tool_status(page, __("{0} vertices · approximate area {1}", [page.cam_measure_points.length, format_area(spherical_polygon_area(page.cam_measure_points))]));
		} else {
			leaflet.polyline(page.cam_measure_points, { color: "#7c3aed", weight: 3, dashArray: "6 5" }).addTo(page.cam_measurements);
			set_tool_status(page, __("Add at least one more corner to measure area."));
		}
	}
	page.main.get(0).querySelector(".cam-map-finish").disabled = page.cam_measure_points.length < (page.cam_tool_mode === "distance" ? 2 : 3);
}

function spherical_polygon_area(points) {
	if (points.length < 3) return 0;
	const radius = 6371008.8;
	let total = 0;
	for (let index = 0; index < points.length; index++) {
		const current = points[index];
		const next = points[(index + 1) % points.length];
		const longitude_delta = (next.lng - current.lng) * Math.PI / 180;
		total += longitude_delta * (2 + Math.sin(current.lat * Math.PI / 180) + Math.sin(next.lat * Math.PI / 180));
	}
	return Math.abs(total * radius * radius / 2);
}

function format_distance(meters) {
	return meters >= 1000 ? `${(meters / 1000).toFixed(2)} km` : `${Math.round(meters)} m`;
}

function format_area(square_meters) {
	return square_meters >= 1_000_000
		? `${(square_meters / 1_000_000).toFixed(2)} km²`
		: `${Math.round(square_meters)} m²`;
}

function finish_map_measurement(page) {
	if (!page.cam_tool_mode) return;
	if (page.cam_tool_mode === "area" && page.cam_measure_points.length >= 3) {
		const leaflet = page.cam_leaflet;
		page.cam_measurements.clearLayers();
		leaflet.polygon(page.cam_measure_points, { color: "#7c3aed", fillColor: "#8b5cf6", fillOpacity: 0.14, weight: 3 }).addTo(page.cam_measurements);
		set_tool_status(page, __("Area measurement complete: {0}", [format_area(spherical_polygon_area(page.cam_measure_points))]));
	} else if (page.cam_tool_mode === "distance" && page.cam_measure_points.length >= 2) {
		let total = 0;
		for (let index = 1; index < page.cam_measure_points.length; index++) {
			total += page.cam_measure_points[index - 1].distanceTo(page.cam_measure_points[index]);
		}
		set_tool_status(page, __("Distance measurement complete: {0}", [format_distance(total)]));
	} else {
		set_tool_status(page, __("Add more points before finishing this measurement."));
		return;
	}
	page.cam_tool_mode = null;
	page.cam_map.doubleClickZoom.enable();
	page.main.get(0).querySelector(".cam-map-finish").disabled = true;
}

function clear_map_tools(page) {
	page.cam_tool_mode = null;
	page.cam_measure_points = [];
	page.cam_measurements.clearLayers();
	page.cam_location_layer.clearLayers();
	page.cam_map.doubleClickZoom.enable();
	page.main.get(0).querySelector(".cam-map-finish").disabled = true;
	set_tool_status(page, __("Map tools cleared. Click the map to inspect coordinates, or choose a tool."));
}

function update_coordinate_readout(page, latlng) {
	page.cam_last_coordinate = latlng;
	page.cam_last_coordinate_text = `${String(latlng.lat)}, ${String(latlng.lng)}`;
	page.main.get(0).querySelector(".cam-map-copy-coords").disabled = false;
	if (!page.cam_tool_mode) {
		set_tool_status(page, `${page.cam_last_coordinate_text} · ${__("click to copy")}`);
	}
}

async function copy_map_coordinates(page) {
	if (!page.cam_last_coordinate) return;
	const value = page.cam_last_coordinate_text || `${String(page.cam_last_coordinate.lat)}, ${String(page.cam_last_coordinate.lng)}`;
	try {
		await navigator.clipboard.writeText(value);
		set_tool_status(page, __("Copied coordinates: {0}", [value]));
	} catch (_error) {
		set_tool_status(page, __("Clipboard access is unavailable; coordinates: {0}", [value]));
	}
}

function locate_map_user(page) {
	if (!navigator.geolocation) {
		set_tool_status(page, __("This browser does not provide geolocation."));
		return;
	}
	set_tool_status(page, __("Waiting for browser location permission…"));
	navigator.geolocation.getCurrentPosition((position) => {
		const point = [position.coords.latitude, position.coords.longitude];
		page.cam_location_layer.clearLayers();
		page.cam_leaflet.circle(point, { radius: Math.max(5, position.coords.accuracy), color: "#2563eb", fillOpacity: 0.08 }).addTo(page.cam_location_layer);
		page.cam_leaflet.circleMarker(point, { radius: 7, color: "#fff", weight: 3, fillColor: "#2563eb", fillOpacity: 1 }).addTo(page.cam_location_layer);
		page.cam_map.setView(point, Math.max(page.cam_map.getZoom(), 15));
		set_tool_status(page, __("Your browser-reported location is shown locally; it was not sent to the server."));
	}, (error) => set_tool_status(page, error.message || __("Unable to access browser location.")), {
		enableHighAccuracy: true,
		timeout: 10000,
		maximumAge: 30000
	});
}

function render_map_insights(page, cameras, movements) {
	const host = page.main.get(0);
	const insight = host.querySelector(".cam-map-insights");
	if (!insight) return;
	const vehicles = new Set(movements.map((row) => row.vehicle).filter(Boolean));
	insight.querySelector("[data-kpi-cameras]").textContent = String(cameras.length);
	insight.querySelector("[data-kpi-movements]").textContent = String(movements.length);
	insight.querySelector("[data-kpi-vehicles]").textContent = String(vehicles.size);
	const endValue = host.querySelector(".cam-map-to").value || local_datetime_value(new Date());
	const startValue = host.querySelector(".cam-map-from").value;
	const parseDay = (value) => {
		const datePart = String(value || "").split("T", 1)[0];
		const parts = datePart.split("-").map(Number);
		const date = new Date(parts[0], parts[1] - 1, parts[2]);
		return Number.isNaN(date.getTime()) ? new Date() : date;
	};
	const endDay = parseDay(endValue);
	const chartStart = new Date(endDay);
	chartStart.setDate(chartStart.getDate() - 13);
	const requestedStart = startValue ? parseDay(startValue) : chartStart;
	const firstDay = requestedStart > chartStart ? requestedStart : chartStart;
	const daySpan = Math.round((endDay - firstDay) / 86400000);
	const days = Number.isFinite(daySpan) ? Math.max(1, Math.min(14, daySpan + 1)) : 1;
	const dateKey = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
	const daily = new Map();
	const series = [];
	for (let index = 0; index < days; index += 1) {
		const date = new Date(firstDay);
		date.setDate(firstDay.getDate() + index);
		const key = dateKey(date);
		series.push({ key, count: 0 });
		daily.set(key, series[series.length - 1]);
	}
	for (const movement of movements) {
		const day = String(movement.detected_at || "").slice(0, 10);
		if (daily.has(day)) daily.get(day).count += 1;
	}
	const svg = insight.querySelector(".cam-map-activity-chart");
	const svgNS = "http://www.w3.org/2000/svg";
	const makeSvg = (tag, attrs = {}) => {
		const element = document.createElementNS(svgNS, tag);
		for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, String(value));
		return element;
	};
	svg.replaceChildren();
	const maxCount = Math.max(1, ...series.map((item) => item.count));
	for (const fraction of [0, 0.5, 1]) {
		const y = 78 - fraction * 58;
		svg.append(makeSvg("line", { x1: 7, x2: 281, y1: y, y2: y, class: "cam-chart-gridline" }));
	}
	const slot = 274 / series.length;
	series.forEach((item, index) => {
		const width = Math.min(12, slot - 4);
		const height = item.count ? Math.max(3, (item.count / maxCount) * 56) : 2;
		const x = 7 + index * slot + (slot - width) / 2;
		const rect = makeSvg("rect", {
			x,
			y: 78 - height,
			width,
			height,
			rx: 4,
			class: index === series.length - 1 ? "cam-chart-bar cam-chart-bar-current" : "cam-chart-bar",
		});
		const title = makeSvg("title");
		title.textContent = `${item.key}: ${item.count} ${__("movements")}`;
		rect.append(title);
		svg.append(rect);
		if (index === 0 || index === series.length - 1 || index % 3 === 0) {
			const tick = makeSvg("text", { x: x + width / 2, y: 101, "text-anchor": "middle", class: "cam-chart-tick" });
			tick.textContent = item.key.slice(5);
			svg.append(tick);
		}
	});
	const totalChart = series.reduce((sum, item) => sum + item.count, 0);
	svg.setAttribute("aria-label", __("{0} movements in the chart window", [totalChart]));
	insight.querySelector("[data-insight-window]").textContent = host.querySelector(".cam-map-include-demo").checked
		? __("DEMO INCLUDED")
		: `${series[0].key.slice(5)} — ${series[series.length - 1].key.slice(5)}`;
	const counts = movements.reduce((result, row) => {
		const kind = String(row.motion_type || "").toLowerCase();
		if (kind === "entry") result.entry += 1;
		else if (kind === "exit") result.exit += 1;
		else result.other += 1;
		return result;
	}, { entry: 0, exit: 0, other: 0 });
	const total = movements.length || 1;
	insight.querySelector(".cam-mix-entry").style.width = `${(counts.entry / total) * 100}%`;
	insight.querySelector(".cam-mix-exit").style.width = `${(counts.exit / total) * 100}%`;
	insight.querySelector(".cam-mix-other").style.width = `${(counts.other / total) * 100}%`;
	insight.querySelector(".cam-map-mix-bar").setAttribute(
		"aria-label",
		__("Movement mix: {0} entries, {1} exits, {2} other", [counts.entry, counts.exit, counts.other])
	);
	insight.querySelector("[data-mix-counts]").textContent = `${__("Entry")}: ${counts.entry} · ${__("Exit")}: ${counts.exit} · ${__("Other")}: ${counts.other}`;
}

function render_movement_slice(page) {
	const host = page.main.get(0);
	if (page.cam_map_mode === "camera") {
		page.cam_event_markers.clearLayers();
		page.cam_tracks.clearLayers();
		host.querySelector(".cam-map-movement-list").replaceChildren();
		return;
	}
	const slider = host.querySelector(".cam-map-time");
	const count = Number(slider.value);
	const rows = page.cam_movement_data.slice(0, count);
	page.cam_event_markers.clearLayers();
	page.cam_tracks.clearLayers();
	page.main.get(0).querySelector(".cam-map-movement-list").replaceChildren();
	const tracks = new Map();
	for (const movement of rows) {
		const point = [Number(movement.latitude), Number(movement.longitude)];
		const marker = page.cam_leaflet.marker(point, { icon: vehicle_icon(movement, page.cam_leaflet, page), zIndexOffset: 500 });
		marker.cam_record_name = movement.name;
		marker.bindPopup(movement_popup(movement, page), { maxWidth: 300 });
		marker.on("popupopen", () => cache_viewed_detail(page, "event", movement));
		page.cam_event_markers.addLayer(marker);
		const key = movement.vehicle || `unassigned:${movement.camera}`;
		if (!tracks.has(key)) tracks.set(key, { points: [], latest: movement });
		tracks.get(key).points.push(point);
		tracks.get(key).latest = movement;
		add_movement_card(page, movement);
	}
	for (const track of tracks.values()) {
		if (track.points.length > 1) {
			page.cam_leaflet.polyline(track.points, { color: "#f97316", weight: 3, opacity: 0.65 }).addTo(page.cam_tracks);
		}
		const endpoint = page.cam_leaflet.marker(track.points[track.points.length - 1], {
			icon: vehicle_icon(track.latest, page.cam_leaflet, page),
			zIndexOffset: 450,
			interactive: false,
		}).addTo(page.cam_tracks);
		endpoint.getElement()?.setAttribute("aria-label", __("Latest position for {0}", [track.latest.vehicle_name || __("unidentified vehicle")]));
	}
	page.main.get(0).querySelector(".cam-map-time-label").textContent = rows.length
		? `${rows.length} / ${page.cam_movement_data.length} ${__("events")} · ${rows[rows.length - 1].detected_at}`
		: (page.cam_movement_data.length ? __("Timeline at start") : __("No events"));
	const summary = page.main.get(0).querySelector(".cam-map-summary");
	if (summary && page.cam_movement_data.length) {
		summary.textContent = __("{0} cameras · showing {1} of {2} movements", [page.cam_camera_count || 0, rows.length, page.cam_movement_data.length]);
	}
}

function toggle_movement_playback(page) {
	const button = page.main.get(0).querySelector(".cam-map-play");
	if (page.cam_playback_timer) {
		clearInterval(page.cam_playback_timer);
		page.cam_playback_timer = null;
		button.textContent = "▶";
		button.setAttribute("aria-label", __("Play movement timeline"));
		return;
	}
	const slider = page.main.get(0).querySelector(".cam-map-time");
	if (!page.cam_movement_data.length) return;
	if (Number(slider.value) >= page.cam_movement_data.length) slider.value = "0";
	button.textContent = "Ⅱ";
	button.setAttribute("aria-label", __("Pause movement timeline"));
	page.cam_playback_timer = window.setInterval(() => {
		const next = Math.min(Number(slider.value) + 1, page.cam_movement_data.length);
		slider.value = String(next);
		render_movement_slice(page);
		if (next >= page.cam_movement_data.length) toggle_movement_playback(page);
	}, 700);
}

function node(tag, class_name, text) {
	const element = document.createElement(tag);
	if (class_name) element.className = class_name;
	if (text !== undefined && text !== null) element.textContent = String(text);
	return element;
}

function image_node(url, alt, class_name, page) {
	if (!url || !/^\/(?:private\/)?files\//.test(url)) return null;
	const image = node("img", class_name);
	image.alt = alt || "";
	image.loading = "lazy";
	image.referrerPolicy = "same-origin";
	if (page) set_image_source(image, url, page);
	else image.src = url;
	return image;
}

function camera_icon(camera, leaflet, page, selected = false) {
	const status = ["Active", "Inactive", "Maintenance"].includes(camera.status) ? camera.status.toLowerCase() : "unknown";
	const shell = node("div", `cam-pin cam-camera-pin cam-camera-status-${status}${selected ? " cam-pin-selected" : ""}${camera.is_demo_record ? " cam-pin-demo" : ""}`);
	shell.setAttribute("aria-label", `${camera.label} · ${camera.status || __("Unknown status")}`);
	const primary = camera.photos.find((photo) => photo.primary && photo.url)
		|| camera.photos.find((photo) => photo.url)
		|| camera.photos.find((photo) => photo.primary)
		|| camera.photos[0];
	const photo = primary?.url && image_node(primary.url, camera.label, "cam-pin-image", page);
	if (photo) shell.append(photo);
	else {
		const fallback = node("span", "cam-pin-fallback", camera.photos.length ? "▧" : "◉");
		if (camera.photos.length) fallback.title = __("Camera images are unavailable");
		shell.append(fallback);
	}
	if (camera.photos.length > 1) shell.append(node("span", "cam-pin-count", camera.photos.length));
	return leaflet.divIcon({ className: "cam-leaflet-icon", html: shell, iconSize: [48, 62], iconAnchor: [24, 62], popupAnchor: [0, -58] });
}

function schedule_camera_popup_close(page, marker) {
	clearTimeout(page.cam_camera_popup_timer);
	page.cam_camera_popup_timer = window.setTimeout(() => {
		const popupElement = marker.getPopup()?.getElement();
		if (page.cam_pinned_camera_marker !== marker && !popupElement?.matches(":hover")) marker.closePopup();
	}, 220);
}

function select_camera_marker(page, marker) {
	const previous = page.cam_selected_camera_marker?.getElement()?.querySelector(".cam-camera-pin");
	if (previous) previous.classList.remove("cam-pin-selected");
	page.cam_selected_camera_marker = marker;
	const selected = marker.getElement()?.querySelector(".cam-camera-pin");
	if (selected) selected.classList.add("cam-pin-selected");
	const camera = page.cam_current_map_data?.cameras?.find((row) => row.name === marker.cam_record_name);
	if (camera) {
		page.cam_last_coordinate_text = `${camera.latitude}, ${camera.longitude}`;
		page.cam_last_coordinate = page.cam_leaflet.latLng(Number(camera.latitude), Number(camera.longitude));
		const copy = page.main.get(0).querySelector(".cam-map-copy-coords");
		if (copy) copy.disabled = false;
		set_tool_status(page, __("Selected camera coordinates: {0}, {1}", [camera.latitude, camera.longitude]));
	}
}

function vehicle_icon(movement, leaflet, page) {
	const kind = String(movement.motion_type || "").toLowerCase();
	const eventMark = kind === "entry" ? "E" : kind === "exit" ? "X" : "•";
	const shell = node("div", "cam-pin cam-vehicle-pin");
	shell.setAttribute("aria-label", `${movement.vehicle_name || __("Unidentified vehicle")} · ${movement.motion_type || __("Movement")}`);
	shell.title = `${movement.vehicle_name || __("Unidentified vehicle")} · ${movement.motion_type || __("Movement")}`;
	const image = image_node(movement.vehicle_image, movement.vehicle_name, "cam-pin-image", page);
	if (image) shell.append(image);
	else shell.append(node("span", "cam-pin-fallback", "🚘"));
	shell.append(node("span", `cam-vehicle-event-badge cam-vehicle-event-${kind || "other"}`, eventMark));
	return leaflet.divIcon({ className: "cam-leaflet-icon", html: shell, iconSize: [44, 44], iconAnchor: [22, 22], popupAnchor: [0, -22] });
}

function add_popup_detail(root, label, value) {
	if (value === undefined || value === null || value === "") return;
	const row = node("div", "cam-popup-detail");
	row.append(node("dt", "", __(label)), node("dd", "", value));
	root.append(row);
}

function add_record_link(container, label, doctype, name, primary = false) {
	if (!name) return;
	const button = node("button", `btn btn-xs ${primary ? "btn-primary" : "btn-default"}`, __(label));
	button.type = "button";
	button.addEventListener("click", () => frappe.set_route("Form", doctype, name));
	container.append(button);
}

function camera_detail_card(camera, page) {
	const card = node("section", "cam-camera-detail-card");
	const avatar = node("div", "cam-camera-card-avatar");
	const primaryPhoto = (camera.photos || []).find((photo) => photo.primary && photo.url)
		|| (camera.photos || []).find((photo) => photo.url);
	const avatarImage = primaryPhoto && image_node(primaryPhoto.url, camera.label, "cam-camera-card-image", page);
	avatar.append(avatarImage || node("span", "cam-camera-card-fallback", "◉"));
	const heading = node("div", "cam-camera-card-heading");
	heading.append(node("strong", "cam-camera-card-title", camera.label));
	heading.append(node("span", "cam-camera-card-subtitle", [camera.camera_type, camera.status].filter(Boolean).join(" · ") || __("Camera details")));
	card.append(avatar, heading);
	if (camera.is_demo_record) card.append(node("span", "cam-demo-badge", __("SYNTHETIC DEMO DATA")));
	card.append(node("hr", "cam-camera-card-divider"));
	const sections = node("div", "cam-camera-card-sections");
	for (const [label, value] of [
		["Exact coordinates", `${camera.latitude}, ${camera.longitude}`],
		["Area / category", [camera.area, camera.camera_type].filter(Boolean).join(" · ")],
		["Operational status", [camera.status, camera.importance].filter(Boolean).join(" · ")],
		["Coverage / activity", [camera.field_of_view, __("{0} photos", [camera.photos?.length || 0]), __("{0} recent events", [camera.movement_count || 0])].filter(Boolean).join(" · ")],
	]) {
		const section = node("div", "cam-camera-card-section");
		section.append(node("span", "cam-camera-card-label", __(label)));
		section.append(node("strong", "cam-camera-card-value", value || __("Not recorded")));
		sections.append(section);
	}
	card.append(sections);
	return card;
}

function camera_popup(camera, page, movements) {
	const root = node("div", "cam-map-popup cam-camera-detail-popup");
	root.append(camera_detail_card(camera, page));
	const status = node("span", `cam-camera-status-badge cam-camera-status-${String(camera.status || "unknown").toLowerCase()}`, __(camera.status || "Unknown status"));
	root.append(status);
	const details = node("dl", "cam-popup-details");
	for (const [label, value] of [
		["Serial number", camera.serial_number], ["Camera number", camera.camera_number],
		["Installation date", camera.installation_date], ["Address", camera.address],
		["Latitude (exact)", camera.latitude], ["Longitude (exact)", camera.longitude],
		["Geographic area", camera.geo_admin_area], ["Boundary", camera.geo_boundary],
		["Field of view", camera.field_of_view], ["Description", camera.description],
		["Lookup source", camera.lookup_source], ["Lookup confidence", camera.lookup_confidence],
		["Lookup ambiguous", camera.lookup_ambiguous ? __("Yes") : __("No")], ["Lookup resolved at", camera.lookup_resolved_at],
	]) add_popup_detail(details, label, value);
	root.append(details);
	const photos = camera.photos || [];
	if (photos.length) {
		let index = Math.max(0, photos.findIndex((photo) => photo.primary));
		const frame = node("div", "cam-gallery-frame");
		const caption = node("div", "cam-gallery-caption");
		const count = node("span", "cam-gallery-count");
		const update = () => {
			const current = photos[index];
			const image = current.url ? image_node(current.url, camera.label, "cam-gallery-image", page) : null;
			frame.replaceChildren(image || node("span", "cam-image-unavailable", __("Image unavailable")));
			caption.textContent = current.caption || current.description || "";
			count.textContent = `${index + 1} / ${photos.length}`;
		};
		if (photos.length > 1) {
			const controls = node("div", "cam-gallery-controls");
			const previous = node("button", "btn btn-xs btn-default", "‹");
			const next = node("button", "btn btn-xs btn-default", "›");
			previous.type = next.type = "button";
			previous.setAttribute("aria-label", __("Previous photo"));
			next.setAttribute("aria-label", __("Next photo"));
			previous.addEventListener("click", () => { index = (index - 1 + photos.length) % photos.length; update(); });
			next.addEventListener("click", () => { index = (index + 1) % photos.length; update(); });
			controls.append(previous, count, next);
			root.append(frame, controls, caption);
		} else {
			root.append(frame, caption);
		}
		update();
	}
	const actions = node("div", "cam-popup-actions");
	add_record_link(actions, "Open camera", "Camera", camera.name, true);
	add_record_link(actions, "Camera type", "Camera Type", camera.camera_type);
	add_record_link(actions, "Open area", "Camera Area", camera.area);
	add_record_link(actions, "Geographic area", "Geo Admin Area", camera.geo_admin_area);
	add_record_link(actions, "Boundary", "Geo Boundary", camera.geo_boundary);
	const relatedEvents = (movements || []).filter((row) => row.camera === camera.name).slice(-5).reverse();
	const events = node("div", "cam-popup-related");
	if (relatedEvents.length) {
		events.append(node("strong", "", __("Recent motion events")));
		for (const movement of relatedEvents) add_record_link(events, `${movement.motion_type} · ${movement.detected_at}`, "Motion Event", movement.name);
	}
	const allEvents = node("button", "btn btn-xs btn-default", __("View all camera events"));
	allEvents.type = "button";
	allEvents.addEventListener("click", () => {
		frappe.route_options = Object.assign({}, frappe.route_options || {}, { camera: camera.name });
		frappe.set_route("List", "Motion Event");
	});
	events.append(allEvents);
	actions.append(events);
	root.append(actions);
	page.cam_leaflet.DomEvent.disableClickPropagation(root);
	page.cam_leaflet.DomEvent.disableScrollPropagation(root);
	return root;
}

function movement_popup(movement, page) {
	const root = node("div", "cam-map-popup");
	const vehicleImage = image_node(movement.vehicle_image, movement.vehicle_name, "cam-vehicle-preview", page);
	root.append(vehicleImage || node("span", "cam-vehicle-preview-fallback cam-popup-vehicle-fallback", "🚘"));
	root.append(node("h4", "", movement.vehicle_name || __("Unidentified vehicle")));
	if (movement.is_demo_record) root.append(node("span", "cam-demo-badge", __("SYNTHETIC DEMO DATA")));
	const details = node("dl", "cam-popup-details");
	for (const [label, value] of [
		["Movement type", movement.motion_type], ["Detected at", movement.detected_at],
		["Vehicle number", movement.vehicle_number], ["Vehicle type", movement.vehicle_type], ["Vehicle status", movement.vehicle_status],
		["Camera", movement.camera_name || movement.camera], ["Camera category", movement.camera_type], ["Camera area", movement.camera_area],
		["Coordinate latitude snapshot", movement.latitude], ["Coordinate longitude snapshot", movement.longitude],
		["Address snapshot", movement.address], ["Nearby cameras", (movement.nearby_cameras || []).map((item) => [item.camera, item.distance_m && `${item.distance_m} m`, item.bearing, item.area, item.camera_status, item.note].filter(Boolean).join(" · ")).join(" | ")],
		["Location source", movement.location_source], ["Location confidence", movement.location_confidence],
		["Location ambiguous", movement.location_ambiguous ? __("Yes") : __("No")], ["Resolved at", movement.location_resolved_at],
		["Importance", movement.importance], ["Notes", movement.notes],
	]) add_popup_detail(details, label, value);
	root.append(details);
	const actions = node("div", "cam-popup-actions");
	add_record_link(actions, "Open motion event", "Motion Event", movement.name, true);
	add_record_link(actions, "Open camera", "Camera", movement.camera);
	add_record_link(actions, "Open vehicle", "CAM Vehicle", movement.vehicle);
	root.append(actions);
	return root;
}

function add_movement_card(page, movement) {
	const card = node("button", "cam-movement-card");
	card.type = "button";
	const image = image_node(movement.vehicle_image, movement.vehicle_name, "cam-movement-image", page);
	card.append(image || node("span", "cam-movement-image cam-vehicle-preview-fallback", "🚘"));
	const text = node("span", "cam-movement-text");
	text.append(node("strong", "", movement.vehicle_name || __("Unidentified vehicle")));
	text.append(node("span", "", `${movement.motion_type} · ${movement.detected_at}`));
	if (movement.vehicle_number) text.append(node("span", "", movement.vehicle_number));
	card.append(text);
	card.addEventListener("click", () => {
		page.cam_map.setView([Number(movement.latitude), Number(movement.longitude)], Math.max(page.cam_map.getZoom(), 14));
		const marker = page.cam_event_markers.getLayers().find((item) => item.cam_record_name === movement.name);
		if (marker) marker.openPopup();
	});
	page.main.find(".cam-map-movement-list").append(card);
}

function render_map_payload(page, data, { offline = false, savedAt = null, fit = true } = {}) {
	page.cam_image_generation = (page.cam_image_generation || 0) + 1;
	for (const url of page.cam_object_urls || []) URL.revokeObjectURL(url);
	page.cam_object_urls = [];
	const leaflet = page.cam_leaflet;
	const host = page.main.get(0);
	const summary = host.querySelector(".cam-map-summary");
	page.cam_camera_markers.clearLayers();
	page.cam_event_markers.clearLayers();
	page.cam_tracks.clearLayers();
	host.querySelector(".cam-map-movement-list").replaceChildren();
	page.cam_current_map_data = data;
	page.cam_movement_data = (data.movements || []).slice().sort((left, right) =>
		String(left.detected_at).localeCompare(String(right.detected_at)) || String(left.name).localeCompare(String(right.name))
	);
	const positions = [];
	for (const camera of data.cameras || []) {
		camera.movement_count = page.cam_movement_data.filter((movement) => movement.camera === camera.name).length;
		const marker = leaflet.marker([Number(camera.latitude), Number(camera.longitude)], { icon: camera_icon(camera, leaflet, page) });
		marker.cam_record_name = camera.name;
		marker.on("click", (event) => {
			page.cam_pinned_camera_marker = marker;
			select_camera_marker(page, marker);
			event.originalEvent?.stopPropagation();
			marker.openPopup();
		});
		marker.on("mouseover", () => {
			clearTimeout(page.cam_camera_popup_timer);
			if (!page.cam_pinned_camera_marker) marker.openPopup();
		});
		marker.on("mouseout", () => schedule_camera_popup_close(page, marker));
		marker.bindPopup(camera_popup(camera, page, page.cam_movement_data), {
			maxWidth: 340, minWidth: 240, autoClose: true, closeOnClick: true,
		});
		marker.on("popupopen", (event) => {
			select_camera_marker(page, marker);
			cache_viewed_detail(page, "camera", camera);
			const popupElement = event.popup.getElement();
			popupElement?.addEventListener("mouseenter", () => clearTimeout(page.cam_camera_popup_timer));
			popupElement?.addEventListener("mouseleave", () => schedule_camera_popup_close(page, marker));
		});
		marker.on("popupclose", () => {
			if (page.cam_pinned_camera_marker === marker) page.cam_pinned_camera_marker = null;
		});
		page.cam_camera_markers.addLayer(marker);
		if (page.cam_map_mode === "camera") positions.push([Number(camera.latitude), Number(camera.longitude)]);
	}
	page.cam_camera_count = (data.cameras || []).length;
	render_map_insights(page, data.cameras || [], page.cam_movement_data);
	const slider = host.querySelector(".cam-map-time");
	const play = host.querySelector(".cam-map-play");
	slider.min = "0";
	slider.max = String(page.cam_movement_data.length);
	slider.value = String(page.cam_movement_data.length);
	slider.disabled = !page.cam_movement_data.length;
	play.disabled = !page.cam_movement_data.length;
	if (page.cam_playback_timer) {
		clearInterval(page.cam_playback_timer);
		page.cam_playback_timer = null;
		play.textContent = "▶";
		play.setAttribute("aria-label", __("Play movement timeline"));
	}
	if (page.cam_map_mode !== "camera") {
		for (const movement of page.cam_movement_data) positions.push([Number(movement.latitude), Number(movement.longitude)]);
	}
	render_movement_slice(page);
	apply_map_mode(page);
	const baseSummary = __("{0} cameras · {1} vehicle movements", [(data.cameras || []).length, page.cam_movement_data.length]);
	summary.textContent = offline
		? `${navigator.onLine ? __("SAVED SNAPSHOT (not live)") : __("OFFLINE CACHED SNAPSHOT")} · ${savedAt ? new Date(savedAt).toLocaleString() : ""} · ${baseSummary}`
		: baseSummary;
	set_offline_status(page, offline
		? (navigator.onLine
			? __("Map service unavailable; showing saved data from {0}.", [savedAt ? new Date(savedAt).toLocaleString() : "—"])
			: __("Offline: this saved snapshot is shown; imagery not saved in this browser is marked unavailable."))
		: null);
	if (fit) {
		if (positions.length === 1) page.cam_map.setView(positions[0], 14);
		else if (positions.length > 1) page.cam_map.fitBounds(leaflet.latLngBounds(positions).pad(0.12), { maxZoom: 14 });
		else page.cam_map.setView([52.37, 4.90], 5);
	}
}

async function load_map(page, { force = false } = {}) {
	read_filter_controls(page);
	page.cam_using_saved_details = false;
	sync_page_route_to_controls(page);
	update_filter_note(page);
	set_basemap(page);
	const host = page.main.get(0);
	const args = {
		camera: page.cam_map_options.camera || undefined,
		vehicle: page.cam_map_options.vehicle || undefined,
		event: page.cam_map_options.event || undefined,
		camera_status: page.cam_map_options.camera_status || undefined,
		area: page.cam_map_options.area || undefined,
		start: map_datetime_arg(host.querySelector(".cam-map-from").value),
		end: map_datetime_arg(host.querySelector(".cam-map-to").value),
		include_demo: host.querySelector(".cam-map-include-demo").checked ? 1 : 0
	};
	const signature = stable_cache_signature(args);
	if (!force && signature === page.cam_last_request_signature && page.cam_current_map_data) return;
	if (signature === page.cam_inflight_signature) return;
	const request_id = (page.cam_map_request_id || 0) + 1;
	page.cam_map_request_id = request_id;
	page.cam_inflight_signature = signature;
	host.querySelector(".cam-map-summary").textContent = __("Loading cameras and movements…");
	try {
		const response = await frappe.call({ method: "camera_archive_management.api.map.map_payload", args, type: "GET" });
		if (request_id !== page.cam_map_request_id) return;
		const data = response.message || { cameras: [], movements: [] };
		page.cam_last_request_signature = signature;
		render_map_payload(page, data);
		cache_map_snapshot(page, args, data);
	} catch (error) {
		if (request_id !== page.cam_map_request_id) return;
		const snapshot = await read_map_snapshot(page, args);
		if (snapshot) {
			if (!navigator.onLine) page.cam_last_request_signature = signature;
			render_map_payload(page, snapshot.data, { offline: true, savedAt: snapshot.savedAt });
		} else {
			page.cam_camera_markers.clearLayers();
			page.cam_event_markers.clearLayers();
			page.cam_tracks.clearLayers();
			host.querySelector(".cam-map-movement-list").replaceChildren();
			page.cam_current_map_data = null;
			page.cam_camera_count = 0;
			page.cam_movement_data = [];
			const slider = host.querySelector(".cam-map-time");
			slider.max = "0";
			slider.value = "0";
			slider.disabled = true;
			host.querySelector(".cam-map-play").disabled = true;
			render_map_insights(page, [], []);
			host.querySelector(".cam-map-summary").textContent = __("No exact matching offline snapshot is available; uncached cameras and events are not shown.");
			set_offline_status(page, navigator.onLine
				? __("Map request failed; no matching saved snapshot is available.")
				: __("Offline: no matching saved snapshot. Uncached map records are unavailable."));
			if (navigator.onLine) frappe.msgprint({ title: __("Camera map"), message: error.message || __("Request failed"), indicator: "red" });
		}
	} finally {
		if (request_id === page.cam_map_request_id) page.cam_inflight_signature = null;
	}
}
