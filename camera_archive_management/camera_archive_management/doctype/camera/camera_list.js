frappe.listview_settings["Camera"] = {
	get_coords_method: "camera_archive_management.api.map.get_custom_map_coords",
	onload(listview) {
		install_camera_map_view_override();
		listview.page.add_inner_button(__("Open camera image map"), () => {
			frappe.route_options = { view: "camera" };
			frappe.set_route("camera-archive-map");
		});
	},
};

if (frappe.router?.on && !frappe.__camMapViewPatchListener) {
	frappe.__camMapViewPatchListener = true;
	frappe.router.on("change", () => window.setTimeout(install_camera_map_view_override, 0));
}

function install_camera_map_view_override() {
	const MapView = frappe.views?.MapView;
	const prototype = MapView?.prototype;
	if (!prototype || prototype.__cam_camera_detail_override) return;
	const original = prototype.render_map_data;
	if (typeof original !== "function") return;
	const originalSetup = prototype.setup_view;
	if (typeof originalSetup === "function") {
		prototype.setup_view = function () {
			const result = originalSetup.apply(this, arguments);
			if (this.doctype === "Camera") load_camera_map_tiles(this);
			return result;
		};
	}

	prototype.render_map_data = function () {
		if (this.doctype !== "Camera") return original.apply(this, arguments);
		if (this.markerLayer) this.map.removeLayer(this.markerLayer);
		this.markerLayer = L.featureGroup();
		const points = this.coords?.features || [];
		for (const feature of points) {
			const geometry = feature.geometry;
			if (geometry?.type !== "Point" || !Array.isArray(geometry.coordinates) || geometry.coordinates.length < 2) continue;
			const [longitude, latitude] = geometry.coordinates;
			if (!Number.isFinite(Number(latitude)) || !Number.isFinite(Number(longitude))) continue;
			const marker = L.marker([Number(latitude), Number(longitude)], { icon: camera_map_icon(feature.properties || {}) });
			const popup = camera_map_popup(feature.properties || {});
			marker.bindPopup(popup, { maxWidth: 360, minWidth: 280, autoClose: true, closeOnClick: true, autoPan: true });
			marker.on("click", (event) => {
				this.__camPinnedCamera = marker;
				event.originalEvent?.stopPropagation();
				marker.openPopup();
			});
			marker.on("mouseover", () => {
				clearTimeout(this.__camCameraPopupTimer);
				if (!this.__camPinnedCamera) marker.openPopup();
			});
			marker.on("mouseout", () => schedule_native_camera_popup_close(this, marker));
			marker.on("popupopen", (event) => {
				const element = event.popup.getElement();
				element?.addEventListener("mouseenter", () => clearTimeout(this.__camCameraPopupTimer));
				element?.addEventListener("mouseleave", () => schedule_native_camera_popup_close(this, marker));
			});
			marker.on("popupclose", () => {
				if (this.__camPinnedCamera === marker) this.__camPinnedCamera = null;
			});
			this.markerLayer.addLayer(marker);
		}
		this.markerLayer.addTo(this.map);
		const bounds = this.markerLayer.getBounds();
		if (bounds.isValid()) this.map.fitBounds(bounds.pad(0.12), { maxZoom: 15 });
	};
	prototype.__cam_camera_detail_override = true;
}

async function load_camera_map_tiles(mapView) {
	const map = mapView.map;
	if (!map) return;
	const container = document.getElementById(mapView.map_id);
	if (!container) return;
	let status = container.querySelector(".cam-native-map-status");
	if (!status) {
		status = document.createElement("div");
		status.className = "cam-native-map-status";
		status.setAttribute("role", "status");
		status.setAttribute("aria-live", "polite");
		container.append(status);
	}
	status.textContent = __("Loading shared Siraj map tiles…");
	try {
		const response = await frappe.call({ method: "camera_archive_management.api.tiles.config", type: "GET" });
		if (mapView.map !== map || !map.getContainer().isConnected) return;
		const config = response.message || {};
		const layers = Array.isArray(config.layers) ? config.layers : [];
		const layer = layers.find((item) => item.id === "standard") || layers[0];
		if (!layer) {
			status.textContent = __("No Siraj raster layer is enabled; camera points remain available.");
			return;
		}
		const existingTileLayers = [];
		map.eachLayer((existing) => {
			if (existing instanceof L.TileLayer) existingTileLayers.push(existing);
		});
		existingTileLayers.forEach((existing) => map.removeLayer(existing));
		const layerUrl = `${window.location.origin}/api/method/camera_archive_management.api.tiles.tile?layer=${encodeURIComponent(layer.id)}&variant=base&z={z}&x={x}&y={y}`;
		const tileLayer = L.tileLayer(layerUrl, {
			minZoom: layer.minZoom,
			maxNativeZoom: layer.maxZoom,
			maxZoom: 22,
			attribution: layer.attribution,
			crossOrigin: false,
		}).addTo(map);
		mapView.__camTileLayer = tileLayer;
		tileLayer.on("tileload", () => {
			status.textContent = __("Shared Siraj map tiles loaded.");
		});
		tileLayer.on("tileerror", () => {
			status.textContent = config.fetch_enabled
				? __("A shared map tile is unavailable; camera points remain available.")
				: __("Tile missing from shared cache; provider fetching is disabled. Camera points remain available.");
		});
		status.textContent = config.fetch_enabled
			? __("Using shared Siraj cache and the configured provider.")
			: __("Using shared Siraj cache only; provider fetching is disabled.");
	} catch (_error) {
		status.textContent = __("Shared map tiles unavailable; camera points remain available.");
	}
}

function schedule_native_camera_popup_close(mapView, marker) {
	clearTimeout(mapView.__camCameraPopupTimer);
	mapView.__camCameraPopupTimer = window.setTimeout(() => {
		const element = marker.getPopup()?.getElement();
		if (mapView.__camPinnedCamera !== marker && !element?.matches(":hover")) marker.closePopup();
	}, 220);
}

function camera_map_icon(camera) {
	const shell = document.createElement("div");
	shell.className = `cam-pin cam-camera-pin cam-camera-status-${String(camera.status || "unknown").toLowerCase()}${camera.is_demo_record ? " cam-pin-demo" : ""}`;
	shell.setAttribute("aria-label", `${camera.label || camera.name} · ${camera.status || __("Unknown status")}`);
	const photos = Array.isArray(camera.photos) ? camera.photos : [];
	const primary = photos.find((photo) => photo.primary && safe_camera_image_url(photo.url))
		|| photos.find((photo) => safe_camera_image_url(photo.url));
	if (primary) {
		const image = document.createElement("img");
		image.className = "cam-pin-image";
		image.alt = camera.label || camera.name || __("Camera image");
		image.loading = "lazy";
		image.referrerPolicy = "same-origin";
		image.src = primary.url;
		image.addEventListener("error", () => {
			image.replaceWith(camera_pin_fallback());
		}, { once: true });
		shell.append(image);
	} else {
		shell.append(camera_pin_fallback());
	}
	if (photos.length > 1) {
		const count = document.createElement("span");
		count.className = "cam-pin-count";
		count.textContent = String(photos.length);
		shell.append(count);
	}
	return L.divIcon({ className: "cam-leaflet-icon", html: shell, iconSize: [48, 62], iconAnchor: [24, 62], popupAnchor: [0, -58] });
}

function camera_pin_fallback() {
	const fallback = document.createElement("span");
	fallback.className = "cam-pin-fallback";
	fallback.textContent = "◉";
	return fallback;
}

function camera_image_unavailable() {
	const unavailable = document.createElement("span");
	unavailable.className = "cam-image-unavailable";
	unavailable.textContent = __("Camera image unavailable offline");
	return unavailable;
}

function safe_camera_image_url(value) {
	return typeof value === "string" && /^\/(?:private\/)?files\//.test(value);
}

function camera_map_popup(camera) {
	const root = document.createElement("div");
	root.className = "cam-map-popup cam-camera-detail-popup";
	root.append(camera_map_detail_card(camera));
	const status = document.createElement("span");
	status.className = `cam-camera-status-badge cam-camera-status-${String(camera.status || "unknown").toLowerCase()}`;
	status.textContent = __(camera.status || "Unknown status");
	root.append(status);

	const details = document.createElement("dl");
	details.className = "cam-popup-details";
	for (const [label, value] of [
		["Serial number", camera.serial_number], ["Camera number", camera.camera_number],
		["Installation date", camera.installation_date], ["Address", camera.address],
		["Geographic area", camera.geo_admin_area], ["Boundary", camera.geo_boundary],
		["Field of view", camera.field_of_view], ["Description", camera.description],
		["Lookup source", camera.lookup_source], ["Lookup confidence", camera.lookup_confidence],
		["Lookup ambiguous", camera.lookup_ambiguous ? __("Yes") : __("No")], ["Lookup resolved at", camera.lookup_resolved_at],
	]) {
		if (value === undefined || value === null || value === "") continue;
		const row = document.createElement("div");
		row.className = "cam-popup-detail";
		const title = document.createElement("dt");
		title.textContent = __(label);
		const valueNode = document.createElement("dd");
		valueNode.textContent = String(value);
		row.append(title, valueNode);
		details.append(row);
	}
	root.append(details);
	append_camera_gallery(root, camera);

	const actions = document.createElement("div");
	actions.className = "cam-popup-actions";
	const open = document.createElement("button");
	open.type = "button";
	open.className = "btn btn-xs btn-primary";
	open.textContent = __("Open camera");
	open.addEventListener("click", () => frappe.set_route("Form", "Camera", camera.name));
	actions.append(open);
	root.append(actions);
	L.DomEvent.disableClickPropagation(root);
	L.DomEvent.disableScrollPropagation(root);
	return root;
}

function camera_map_detail_card(camera) {
	const card = document.createElement("section");
	card.className = "cam-camera-detail-card";
	const avatar = document.createElement("div");
	avatar.className = "cam-camera-card-avatar";
	const photos = Array.isArray(camera.photos) ? camera.photos : [];
	const primary = photos.find((photo) => photo.primary && safe_camera_image_url(photo.url))
		|| photos.find((photo) => safe_camera_image_url(photo.url));
	if (primary) {
		const image = document.createElement("img");
		image.className = "cam-camera-card-image";
		image.alt = camera.label || camera.name || __("Camera image");
		image.loading = "lazy";
		image.referrerPolicy = "same-origin";
		image.src = primary.url;
		image.addEventListener("error", () => image.replaceWith(camera_pin_fallback()), { once: true });
		avatar.append(image);
	} else {
		avatar.append(camera_pin_fallback());
	}
	const heading = document.createElement("div");
	heading.className = "cam-camera-card-heading";
	const title = document.createElement("strong");
	title.className = "cam-camera-card-title";
	title.textContent = camera.label || camera.name || __("Camera details");
	const subtitle = document.createElement("span");
	subtitle.className = "cam-camera-card-subtitle";
	subtitle.textContent = [camera.camera_type, camera.status].filter(Boolean).join(" · ") || __("Camera details");
	heading.append(title, subtitle);
	card.append(avatar, heading);
	if (camera.is_demo_record) {
		const badge = document.createElement("span");
		badge.className = "cam-demo-badge";
		badge.textContent = __("SYNTHETIC DEMO DATA");
		card.append(badge);
	}
	const divider = document.createElement("hr");
	divider.className = "cam-camera-card-divider";
	card.append(divider);
	const sections = document.createElement("div");
	sections.className = "cam-camera-card-sections";
	const rows = [
		["Exact coordinates", `${camera.latitude || ""}, ${camera.longitude || ""}`],
		["Area / category", [camera.area, camera.camera_type].filter(Boolean).join(" · ")],
		["Operational status", [camera.status, camera.importance].filter(Boolean).join(" · ")],
		["Coverage / activity", [camera.field_of_view, __("{0} photos", [photos.length])].filter(Boolean).join(" · ")],
	];
	for (const [label, value] of rows) {
		const section = document.createElement("div");
		section.className = "cam-camera-card-section";
		const caption = document.createElement("span");
		caption.className = "cam-camera-card-label";
		caption.textContent = __(label);
		const detail = document.createElement("strong");
		detail.className = "cam-camera-card-value";
		detail.textContent = value || __("Not recorded");
		section.append(caption, detail);
		sections.append(section);
	}
	card.append(sections);
	return card;
}

function append_camera_gallery(root, camera) {
	const photos = Array.isArray(camera.photos) ? camera.photos : [];
	if (!photos.length) return;
	let index = Math.max(0, photos.findIndex((photo) => photo.primary));
	const frame = document.createElement("div");
	frame.className = "cam-gallery-frame";
	const caption = document.createElement("div");
	caption.className = "cam-gallery-caption";
	const count = document.createElement("span");
	count.className = "cam-gallery-count";
	const update = () => {
		const photo = photos[index];
		if (safe_camera_image_url(photo.url)) {
			const image = document.createElement("img");
			image.className = "cam-gallery-image";
			image.alt = camera.label || __("Camera image");
			image.loading = "lazy";
			image.referrerPolicy = "same-origin";
			image.src = photo.url;
			image.addEventListener("error", () => image.replaceWith(camera_image_unavailable()), { once: true });
			frame.replaceChildren(image);
		} else {
			frame.replaceChildren(camera_image_unavailable());
		}
		caption.textContent = photo.caption || photo.description || "";
		count.textContent = `${index + 1} / ${photos.length}`;
	};
	if (photos.length > 1) {
		const controls = document.createElement("div");
		controls.className = "cam-gallery-controls";
		for (const [text, delta, label] of [["‹", -1, "Previous photo"], ["›", 1, "Next photo"]]) {
			const button = document.createElement("button");
			button.type = "button";
			button.className = "btn btn-xs btn-default";
			button.textContent = text;
			button.setAttribute("aria-label", __(label));
			button.addEventListener("click", () => {
				index = (index + delta + photos.length) % photos.length;
				update();
			});
			controls.append(button);
		}
		controls.append(count);
		root.append(frame, controls, caption);
	} else {
		root.append(frame, caption);
	}
	update();
}
