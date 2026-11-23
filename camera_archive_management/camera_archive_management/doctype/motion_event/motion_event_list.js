frappe.listview_settings["Motion Event"] = {
	get_coords_method: "camera_archive_management.api.map.get_custom_map_coords",
	onload(listview) {
		install_motion_event_map_override();
		listview.page.add_inner_button(__("Open vehicle movement map"), () => {
			frappe.route_options = { view: "movement" };
			frappe.set_route("camera-archive-map");
		});
	},
};

if (frappe.router?.on && !frappe.__camMotionMapPatchListener) {
	frappe.__camMotionMapPatchListener = true;
	frappe.router.on("change", () => window.setTimeout(install_motion_event_map_override, 0));
}

function install_motion_event_map_override() {
	const prototype = frappe.views?.MapView?.prototype;
	if (!prototype || prototype.__cam_motion_cluster_override) return;
	const original = prototype.render_map_data;
	if (typeof original !== "function") return;
	prototype.render_map_data = function () {
		if (this.doctype !== "Motion Event" || !this.map || !window.L?.marker || !window.L?.divIcon) {
			return original.apply(this, arguments);
		}
		const map = this.map;
		const previous = this.__camMotionMapState;
		if (previous) {
			map.off("moveend zoomend", previous.onMapChange);
			if (map.hasLayer(previous.layer)) map.removeLayer(previous.layer);
		}
		if (this.markerLayer && map.hasLayer(this.markerLayer)) map.removeLayer(this.markerLayer);
		const features = (this.coords?.features || []).filter((feature) => {
			const coordinates = feature.geometry?.coordinates;
			return feature.geometry?.type === "Point" && Array.isArray(coordinates) && coordinates.length >= 2
				&& Number.isFinite(Number(coordinates[0])) && Number.isFinite(Number(coordinates[1]));
		});
		const state = {
			map,
			view: this,
			features,
			expanded: new Set(),
			layer: window.L.layerGroup().addTo(map),
		};
		state.render = () => render_motion_event_clusters(state);
		state.onMapChange = () => {
			state.expanded.clear();
			state.render();
		};
		map.on("moveend zoomend", state.onMapChange);
		this.__camMotionMapState = state;
		this.markerLayer = state.layer;
		state.render();
		if (!this.__camMotionHasFit && features.length) {
			const bounds = window.L.latLngBounds(features.map((feature) => {
				const [longitude, latitude] = feature.geometry.coordinates;
				return [Number(latitude), Number(longitude)];
			}));
			if (bounds.isValid()) map.fitBounds(bounds.pad(0.12), { maxZoom: 15 });
			this.__camMotionHasFit = true;
		}
	};
	prototype.__cam_motion_cluster_override = true;
}

function render_motion_event_clusters(state) {
	const { map, features, expanded, layer } = state;
	layer.clearLayers();
	if (!features.length) return;
	const vehicleTotals = count_motion_events_by_vehicle(features);
	const clusters = cluster_motion_event_features(features, map, 58);
	for (const cluster of clusters) {
		const rows = cluster.rows;
		if (rows.length === 1) {
			layer.addLayer(make_motion_vehicle_marker(rows, cluster.center, vehicleTotals, state));
			continue;
		}
		const clusterKey = rows.map((feature) => feature.properties?.name || "").sort().join("|");
		if (expanded.has(clusterKey)) {
			const vehicleGroups = group_motion_events_by_vehicle_and_camera(rows);
			const originPoint = map.project(cluster.center, map.getZoom());
			vehicleGroups.forEach((group, index) => {
				const angle = (Math.PI * 2 * index) / vehicleGroups.length - Math.PI / 2;
				const radius = 50 + Math.floor(index / 10) * 16;
				const position = map.unproject(window.L.point(
					originPoint.x + Math.cos(angle) * radius,
					originPoint.y + Math.sin(angle) * radius
				), map.getZoom());
				const leg = window.L.polyline([cluster.center, position], { className: "cam-motion-spider-leg", color: "#64748b", weight: 1.5, opacity: 0.7, interactive: false });
				layer.addLayer(leg);
				layer.addLayer(make_motion_vehicle_marker(group.rows, position, vehicleTotals, state));
			});
			continue;
		}
		const vehicleGroups = group_motion_events_by_vehicle_and_camera(rows);
		const marker = window.L.marker(cluster.center, {
			icon: motion_cluster_icon(rows, vehicleGroups),
			title: __("{0} vehicle groups · {1} movements. Click to expand.", [vehicleGroups.length, rows.length]),
			keyboard: true,
			camMotionClusterKey: clusterKey,
		});
		marker.options.camMotionClusterKey = clusterKey;
		marker.on("click", () => {
			expanded.add(clusterKey);
			state.render();
		});
		layer.addLayer(marker);
	}
}

function cluster_motion_event_features(features, map, radius) {
	const zoom = map.getZoom();
	const points = features.map((feature, index) => {
		const [longitude, latitude] = feature.geometry.coordinates;
		return { feature, index, point: map.project(window.L.latLng(Number(latitude), Number(longitude)), zoom) };
	});
	const parents = points.map((point) => point.index);
	const root = (index) => {
		while (parents[index] !== index) {
			parents[index] = parents[parents[index]];
			index = parents[index];
		}
		return index;
	};
	const buckets = new Map();
	for (const item of points) {
		const cellX = Math.floor(item.point.x / radius);
		const cellY = Math.floor(item.point.y / radius);
		for (let dx = -1; dx <= 1; dx += 1) {
			for (let dy = -1; dy <= 1; dy += 1) {
				for (const other of buckets.get(`${cellX + dx}:${cellY + dy}`) || []) {
					const deltaX = item.point.x - other.point.x;
					const deltaY = item.point.y - other.point.y;
					if (deltaX * deltaX + deltaY * deltaY <= radius * radius) {
						const left = root(item.index);
						const right = root(other.index);
						if (left !== right) parents[right] = left;
					}
				}
			}
		}
		const key = `${cellX}:${cellY}`;
		if (!buckets.has(key)) buckets.set(key, []);
		buckets.get(key).push(item);
	}
	const groups = new Map();
	for (const item of points) {
		const key = root(item.index);
		if (!groups.has(key)) groups.set(key, []);
		groups.get(key).push(item);
	}
	return Array.from(groups.values(), (items) => {
		const centerPoint = items.reduce((sum, item) => ({ x: sum.x + item.point.x, y: sum.y + item.point.y }), { x: 0, y: 0 });
		centerPoint.x /= items.length;
		centerPoint.y /= items.length;
		return {
			rows: items.map((item) => item.feature),
			center: map.unproject(window.L.point(centerPoint.x, centerPoint.y), zoom),
		};
	});
}

function count_motion_events_by_vehicle(features) {
	const totals = new Map();
	for (const feature of features) {
		const props = feature.properties || {};
		const vehicle = safe_motion_text(props.vehicle);
		if (!vehicle) continue;
		const reportedTotal = Number(props.vehicle_movement_count);
		if (Number.isSafeInteger(reportedTotal) && reportedTotal >= 0) {
			totals.set(vehicle, Math.max(totals.get(vehicle) || 0, reportedTotal));
		} else {
			totals.set(vehicle, (totals.get(vehicle) || 0) + 1);
		}
	}
	return totals;
}

function group_motion_events_by_vehicle_and_camera(features) {
	const groups = new Map();
	for (const feature of features) {
		const props = feature.properties || {};
		const vehicle = safe_motion_text(props.vehicle);
		const camera = safe_motion_text(props.camera || props.camera_name) || __("Unknown camera");
		const key = `${camera}\u001f${vehicle || `event:${safe_motion_text(props.name)}`}`;
		if (!groups.has(key)) groups.set(key, { rows: [], camera, vehicle });
		groups.get(key).rows.push(feature);
	}
	return Array.from(groups.values());
}

function make_motion_vehicle_marker(features, position, totals, state) {
	const props = features[0]?.properties || {};
	const vehicleId = safe_motion_text(props.vehicle);
	const group = {
		rows: features,
		camera: safe_motion_text(props.camera_name || props.camera) || __("Unknown camera"),
		vehicle: vehicleId,
	};
	const marker = window.L.marker(position, {
		icon: motion_vehicle_icon(props, features.length),
		title: `${safe_motion_text(props.vehicle_name) || __("Unidentified vehicle")} · ${features.length} ${__("at this camera")}`,
		keyboard: true,
	});
	marker.bindPopup(motion_vehicle_popup(group, totals.get(vehicleId) || features.length), { maxWidth: 320, minWidth: 240 });
	marker.on("click", (event) => event.originalEvent?.stopPropagation());
	return marker;
}

function motion_cluster_icon(features, vehicleGroups) {
	const host = document.createElement("div");
	host.className = "cam-motion-cluster";
	const ring = document.createElement("span");
	ring.className = "cam-motion-cluster-logos";
	const shown = new Set();
	for (const feature of features) {
		const props = feature.properties || {};
		const key = safe_motion_text(props.vehicle) || safe_motion_text(props.name);
		if (!key || !safe_motion_image_url(props.vehicle_image) || shown.has(key) || shown.size >= 3) continue;
		shown.add(key);
		const logo = motion_vehicle_logo(props, "cam-motion-cluster-logo");
		ring.append(logo);
	}
	const total = document.createElement("strong");
	total.textContent = String(vehicleGroups.length);
	const caption = document.createElement("small");
	caption.textContent = `${features.length} ${__("moves")}`;
	host.append(ring, total, caption);
	return window.L.divIcon({ className: "cam-motion-cluster-leaflet", html: host.outerHTML, iconSize: [76, 76], iconAnchor: [38, 38] });
}

function motion_vehicle_icon(props, countAtCamera) {
	const host = document.createElement("div");
	host.className = "cam-motion-vehicle-marker";
	host.setAttribute("aria-label", safe_motion_text(props.vehicle_name) || __("Unidentified vehicle"));
	host.append(motion_vehicle_logo(props, "cam-motion-vehicle-logo"));
	if (countAtCamera > 1) {
		const count = document.createElement("span");
		count.className = "cam-motion-vehicle-count";
		count.textContent = String(countAtCamera);
		host.append(count);
	}
	return window.L.divIcon({ className: "cam-motion-vehicle-leaflet", html: host.outerHTML, iconSize: [48, 48], iconAnchor: [24, 24], popupAnchor: [0, -22] });
}

function motion_vehicle_logo(props, className) {
	const host = document.createElement("span");
	host.className = className;
	const image = safe_motion_image_url(props.vehicle_image);
	if (image) {
		const photo = document.createElement("img");
		photo.src = image;
		photo.alt = safe_motion_text(props.vehicle_name) || __("Vehicle");
		photo.loading = "lazy";
		photo.referrerPolicy = "same-origin";
		host.append(photo);
	} else {
		host.classList.add("cam-motion-user-point");
		host.setAttribute("aria-label", __("No user-configured vehicle image; showing the saved movement point"));
	}
	return host;
}

function motion_vehicle_popup(group, totalMoves) {
	const props = group.rows[0]?.properties || {};
	const root = document.createElement("section");
	root.className = "cam-motion-vehicle-popup";
	const title = document.createElement("h4");
	title.textContent = safe_motion_text(props.vehicle_name) || __("Unidentified vehicle");
	const camera = document.createElement("p");
	camera.textContent = group.camera;
	const total = document.createElement("strong");
	total.className = "cam-motion-total-count";
	total.textContent = __("{0} total movements", [totalMoves]);
	const local = document.createElement("span");
	local.className = "cam-motion-camera-count";
	local.textContent = __("{0} movements at this camera", [group.rows.length]);
	root.append(title, camera, total, local);
	const actions = document.createElement("div");
	actions.className = "cam-motion-popup-actions";
	if (group.vehicle) {
		const open = document.createElement("button");
		open.type = "button";
		open.className = "btn btn-xs btn-primary";
		open.textContent = __("Open vehicle");
		open.addEventListener("click", () => frappe.set_route("Form", "CAM Vehicle", group.vehicle));
		actions.append(open);
		const events = document.createElement("button");
		events.type = "button";
		events.className = "btn btn-xs btn-default";
		events.textContent = __("All vehicle movements");
		events.addEventListener("click", () => {
			frappe.route_options = { vehicle: group.vehicle };
			frappe.set_route("List", "Motion Event");
		});
		actions.append(events);
	}
	root.append(actions);
	window.L.DomEvent?.disableClickPropagation?.(root);
	return root;
}

function safe_motion_image_url(value) {
	return typeof value === "string" && /^\/(?:private\/)?files\/[A-Za-z0-9_./% -]+$/.test(value) ? value : "";
}

function safe_motion_text(value) {
	if (typeof value !== "string") return "";
	return /\[object (?:Object|[A-Za-z0-9_]*Element)\]/i.test(value) ? "" : value;
}
