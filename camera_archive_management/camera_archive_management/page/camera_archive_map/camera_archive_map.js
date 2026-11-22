let cam_map_leaflet;
let cam_map_leaflet_promise;

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
			<span class="cam-map-tile-status text-muted" aria-live="polite"></span>
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
						<article class="cam-map-kpi cam-kpi-camera"><span>${__("Active cameras")}</span><strong data-kpi-cameras>—</strong><small>${__("in this view")}</small></article>
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
	page.cam_tile_status = host.querySelector(".cam-map-tile-status");
	page.cam_tile_errors = 0;
	set_tile_status(page, __("Map tiles use the shared Siraj server cache."));
	if (!page.cam_network_listener) {
		page.cam_network_listener = () => {
			set_tile_status(page, navigator.onLine
				? __("Browser is online; missing tiles use the configured server provider when enabled.")
				: __("Browser is offline; the Bench server must remain reachable to use cached tiles."));
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
	host.querySelector(".cam-map-layer").addEventListener("change", () => set_basemap(page));
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
	host.querySelector(".cam-map-show-countries").addEventListener("change", (event) => set_country_visibility(page, event.target.checked));
	host.querySelector(".cam-map-time").addEventListener("input", () => render_movement_slice(page));
	host.querySelector(".cam-map-play").addEventListener("click", () => toggle_movement_playback(page));
	page.cam_map.on("mousemove", (event) => update_coordinate_readout(page, event.latlng));
	page.cam_map.on("click", (event) => handle_map_click(page, event.latlng));
	page.cam_map.on("dblclick", () => {
		if (page.cam_tool_mode) finish_map_measurement(page);
	});
	load_tile_config(page);
	load_country_boundaries(page);
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

function set_tile_status(page, message) {
	if (page.cam_tile_status && page.cam_tile_status.textContent !== message) {
		page.cam_tile_status.textContent = message;
	}
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
			return;
		}
		page.cam_tile_config = Object.fromEntries(layers.map((layer) => [layer.id, layer]));
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
		set_tile_status(page, __("A tile is missing or unavailable; cached tiles remain usable and upstream retries are throttled."));
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
		{ minZoom: config.minZoom, maxZoom: config.maxZoom, attribution: config.attribution, crossOrigin: false }
	));
	page.cam_base_layers[selected] = base;
	base.addTo(map);
	if (selected === "hybrid" && config.overlay !== false) {
		page.cam_overlay = page.cam_overlay || bind_tile_status(page, leaflet.tileLayer(
			tile_template("hybrid", "overlay", page.cam_map_context),
			{ minZoom: config.minZoom, maxZoom: config.maxZoom, attribution: config.attribution, opacity: 1 }
		));
		page.cam_overlay.addTo(map);
	}
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
	page.main.get(0).querySelector(".cam-map-copy-coords").disabled = false;
	if (!page.cam_tool_mode) {
		set_tool_status(page, `${latlng.lat.toFixed(6)}, ${latlng.lng.toFixed(6)} · ${__("click to copy")}`);
	}
}

async function copy_map_coordinates(page) {
	if (!page.cam_last_coordinate) return;
	const value = `${page.cam_last_coordinate.lat.toFixed(6)}, ${page.cam_last_coordinate.lng.toFixed(6)}`;
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
	const endValue = host.querySelector(".cam-map-to").value || new Date().toISOString().slice(0, 10);
	const startValue = host.querySelector(".cam-map-from").value || endValue;
	const parseDay = (value) => {
		const parts = value.split("-").map(Number);
		return new Date(parts[0], parts[1] - 1, parts[2]);
	};
	const endDay = parseDay(endValue);
	const requestedStart = parseDay(startValue);
	const chartStart = new Date(endDay);
	chartStart.setDate(chartStart.getDate() - 13);
	const firstDay = requestedStart > chartStart ? requestedStart : chartStart;
	const days = Math.max(1, Math.min(14, Math.round((endDay - firstDay) / 86400000) + 1));
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
	const slider = page.main.get(0).querySelector(".cam-map-time");
	const count = Number(slider.value);
	const rows = page.cam_movement_data.slice(0, count);
	page.cam_event_markers.clearLayers();
	page.cam_tracks.clearLayers();
	page.main.get(0).querySelector(".cam-map-movement-list").replaceChildren();
	const tracks = new Map();
	for (const movement of rows) {
		const point = [Number(movement.latitude), Number(movement.longitude)];
		const marker = page.cam_leaflet.marker(point, { icon: vehicle_icon(movement, page.cam_leaflet), zIndexOffset: 500 });
		marker.cam_record_name = movement.name;
		marker.bindPopup(movement_popup(movement), { maxWidth: 300 });
		page.cam_event_markers.addLayer(marker);
		const key = movement.vehicle || `unassigned:${movement.camera}`;
		if (!tracks.has(key)) tracks.set(key, []);
		tracks.get(key).push(point);
		add_movement_card(page, movement);
	}
	for (const points of tracks.values()) {
		if (points.length > 1) page.cam_leaflet.polyline(points, { color: "#f97316", weight: 3, opacity: 0.65 }).addTo(page.cam_tracks);
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

function image_node(url, alt, class_name) {
	if (!url || !/^\/(?:private\/)?files\//.test(url)) return null;
	const image = node("img", class_name);
	image.src = url;
	image.alt = alt || "";
	image.loading = "lazy";
	image.referrerPolicy = "same-origin";
	return image;
}

function camera_icon(camera, leaflet) {
	const shell = node("div", `cam-pin cam-camera-pin${camera.is_demo_record ? " cam-pin-demo" : ""}`);
	const primary = camera.photos.find((photo) => photo.primary) || camera.photos[0];
	const photo = primary && image_node(primary.url, camera.label, "cam-pin-image");
	if (photo) shell.append(photo);
	else shell.append(node("span", "cam-pin-fallback", "◉"));
	if (camera.photos.length > 1) shell.append(node("span", "cam-pin-count", camera.photos.length));
	return leaflet.divIcon({ className: "cam-leaflet-icon", html: shell, iconSize: [48, 62], iconAnchor: [24, 62], popupAnchor: [0, -58] });
}

function vehicle_icon(movement, leaflet) {
	const shell = node("div", "cam-pin cam-vehicle-pin");
	const image = image_node(movement.vehicle_image, movement.vehicle_name, "cam-pin-image");
	if (image) shell.append(image);
	else shell.append(node("span", "cam-pin-fallback", "🚘"));
	return leaflet.divIcon({ className: "cam-leaflet-icon", html: shell, iconSize: [44, 44], iconAnchor: [22, 22], popupAnchor: [0, -22] });
}

function camera_popup(camera) {
	const root = node("div", "cam-map-popup");
	root.append(node("h4", "", camera.label));
	if (camera.is_demo_record) root.append(node("span", "cam-demo-badge", __("SYNTHETIC DEMO DATA")));
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
	if (movement.is_demo_record) root.append(node("span", "cam-demo-badge", __("SYNTHETIC DEMO DATA")));
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
		const marker = page.cam_event_markers.getLayers().find((item) => item.cam_record_name === movement.name);
		if (marker) marker.openPopup();
	});
	page.main.find(".cam-map-movement-list").append(card);
}

async function load_map(page) {
	const leaflet = page.cam_leaflet;
	const request_id = (page.cam_map_request_id || 0) + 1;
	page.cam_map_request_id = request_id;
	read_filter_controls(page);
	update_filter_note(page);
	set_basemap(page);
	page.cam_camera_markers.clearLayers();
	page.cam_event_markers.clearLayers();
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
		end: host.querySelector(".cam-map-to").value || undefined,
		include_demo: host.querySelector(".cam-map-include-demo").checked ? 1 : 0
	};
	try {
		const response = await frappe.call({ method: "camera_archive_management.api.map.map_payload", args, type: "GET" });
		if (request_id !== page.cam_map_request_id) return;
		const data = response.message || { cameras: [], movements: [] };
		const positions = [];
		for (const camera of data.cameras || []) {
			const marker = leaflet.marker([Number(camera.latitude), Number(camera.longitude)], { icon: camera_icon(camera, leaflet) });
			marker.cam_record_name = camera.name;
			marker.bindPopup(camera_popup(camera), { maxWidth: 320, minWidth: 220 });
			page.cam_camera_markers.addLayer(marker);
			positions.push([Number(camera.latitude), Number(camera.longitude)]);
		}
		page.cam_camera_count = (data.cameras || []).length;
		page.cam_movement_data = (data.movements || []).slice().sort((left, right) =>
			String(left.detected_at).localeCompare(String(right.detected_at)) || String(left.name).localeCompare(String(right.name))
		);
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
		for (const movement of page.cam_movement_data) positions.push([Number(movement.latitude), Number(movement.longitude)]);
		render_movement_slice(page);
		summary.textContent = __("{0} cameras · {1} vehicle movements", [data.cameras.length, page.cam_movement_data.length]);
		if (positions.length === 1) page.cam_map.setView(positions[0], 14);
		else if (positions.length > 1) page.cam_map.fitBounds(leaflet.latLngBounds(positions).pad(0.12), { maxZoom: 14 });
		else page.cam_map.setView([52.37, 4.90], 5);
	} catch (error) {
		if (request_id !== page.cam_map_request_id) return;
		summary.textContent = __("Map data could not be loaded. Check Camera/Motion Event read permissions and the server logs.");
		frappe.msgprint({ title: __("Camera map"), message: error.message || __("Request failed"), indicator: "red" });
	}
}
