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
			marker.bindPopup(popup, { maxWidth: 360, minWidth: 280, maxHeight: Math.max(120, Math.min(720, Math.floor(this.map.getContainer().clientHeight * 0.76))), autoClose: true, closeOnClick: true, autoPan: true, autoPanPaddingTopLeft: [16, 72], autoPanPaddingBottomRight: [16, 20], keepInView: true });
			marker.on("click", (event) => {
				this.__camPinnedCamera = marker;
				const pin = marker.getElement()?.querySelector(".cam-camera-pin");
				pin?.classList.add("is-selected");
				if (pin && !pin.classList.contains("siraj-pin")) pin.classList.add("cam-pin-selected");
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
				const pin = marker.getElement()?.querySelector(".cam-camera-pin");
				pin?.classList.remove("is-selected", "cam-pin-selected");
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

function cam_native_is_object_string(value) {
	return typeof value === "string" && /\[object (?:Object|[A-Za-z0-9_]*Element)\]/i.test(value);
}

function cam_native_dom_node(value) {
	if (!value || typeof value !== "object") return null;
	if ([1, 3, 11].includes(value.nodeType)) return value;
	const wrapped = value.jquery || typeof value.length === "number" ? value[0] : null;
	return wrapped && [1, 3, 11].includes(wrapped.nodeType) ? wrapped : null;
}

function cam_native_mount_icon_content(container, content) {
	if (typeof content === "string") {
		if (!content.trim() || cam_native_is_object_string(content)) return false;
		container.innerHTML = content;
		return true;
	}
	const element = cam_native_dom_node(content);
	if (!element || cam_native_is_object_string(element.textContent || "")) return false;
	if (element.nodeType === 1 && cam_native_is_object_string(element.outerHTML || "")) return false;
	container.append(element.cloneNode(true));
	return true;
}

function cam_native_icon_html(content) {
	if (typeof content === "string") return content.trim() && !cam_native_is_object_string(content) ? content : "";
	const element = cam_native_dom_node(content);
	if (!element) return "";
	if (element.nodeType === 1 && typeof element.outerHTML === "string") {
		return cam_native_is_object_string(element.outerHTML) ? "" : element.outerHTML;
	}
	const template = document.createElement("template");
	template.content.append(element.cloneNode(true));
	return cam_native_is_object_string(template.innerHTML) ? "" : template.innerHTML;
}

function cam_native_safe_text(value) {
	if (typeof value === "string") return cam_native_is_object_string(value) ? "" : value;
	if (["number", "boolean", "bigint"].includes(typeof value)) return String(value);
	const element = cam_native_dom_node(value);
	if (!element) return "";
	const text = element.textContent || "";
	return cam_native_is_object_string(text) ? "" : text;
}

function camera_map_icon(camera) {
	return siraj_camera_pin_icon(camera, L) || camera_map_icon_fallback(camera);
}

function siraj_camera_pin_icon(camera, leaflet, selected = false) {
	if (!window.sirajIcons?.pin || !leaflet?.divIcon) return null;
	const size = 32;
	const status = cam_native_safe_text(camera.status).toLowerCase();
	const label = cam_native_safe_text(camera.label || camera.name) || __("Camera");
	const color = window.sirajColours?.Camera || "#3577c0";
	const ring = status === "active" ? "#16a34a" : status === "inactive" ? "#64748b" : status === "maintenance" ? "#f59e0b" : color;
	const host = document.createElement("div");
	let pinMarkup;
	try {
		pinMarkup = window.sirajIcons.pin("Camera", color, size, {
			state: selected ? "selected" : status === "active" ? "active" : status === "inactive" ? "inactive" : undefined,
			ring,
			dot: false,
		});
	} catch (_error) {
		return null;
	}
	if (!cam_native_mount_icon_content(host, pinMarkup)) return null;
	const pin = host.querySelector(".siraj-pin");
	const body = pin?.querySelector(".siraj-pin-body");
	if (!pin || !body) return null;
	pin.classList.add("cam-camera-pin");
	pin.setAttribute("aria-label", `${label} · ${status || __("Unknown status")}`);
	if (camera.is_demo_record) pin.classList.add("cam-pin-demo");
	body.replaceChildren(camera_pin_glyph());
	const photos = Array.isArray(camera.photos) ? camera.photos : [];
	const primary = photos.find((photo) => photo?.primary && safe_camera_image_url(photo.url))
		|| photos.find((photo) => safe_camera_image_url(photo?.url));
	if (primary) {
		const image = document.createElement("img");
		image.className = "cam-siraj-pin-photo";
		image.alt = cam_native_safe_text(camera.label || camera.name) || __("Camera image");
		image.loading = "lazy";
		image.referrerPolicy = "same-origin";
		image.src = primary.url;
		image.addEventListener("error", () => image.replaceWith(camera_pin_glyph()), { once: true });
		body.replaceChildren(image);
	}
	if (photos.length > 1) {
		const count = document.createElement("span");
		count.className = "cam-siraj-photo-count";
		count.textContent = String(photos.length);
		count.setAttribute("aria-label", __("{0} photos", [photos.length]));
		pin.append(count);
	}
	return leaflet.divIcon({
		className: "sx-pin-wrapper cam-leaflet-icon",
		iconSize: [size, Math.round(size * 1.15)],
		iconAnchor: [size / 2, Math.round(size * 1.15)],
		popupAnchor: [0, -Math.round(size * 0.8)],
		tooltipAnchor: [0, -Math.round(size * 0.5)],
		html: host.innerHTML,
	});
}

function camera_pin_glyph() {
	const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
	svg.setAttribute("viewBox", "0 0 24 24");
	svg.setAttribute("aria-hidden", "true");
	svg.innerHTML = '<path d="M4 8h3l1.5-2h7L17 8h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1Z"/><circle cx="12" cy="13" r="3.5"/><path d="M18 10h.01"/>';
	return svg;
}

function camera_map_icon_fallback(camera = {}) {
	const shell = document.createElement("div");
	const status = cam_native_safe_text(camera.status).toLowerCase() || "unknown";
	const label = cam_native_safe_text(camera.label || camera.name) || __("Camera");
	shell.className = `cam-pin cam-camera-pin cam-camera-status-${status}${camera.is_demo_record ? " cam-pin-demo" : ""}`;
	shell.setAttribute("aria-label", `${label} · ${status === "unknown" ? __("Unknown status") : status}`);
	const photos = Array.isArray(camera.photos) ? camera.photos : [];
	const primary = photos.find((photo) => photo?.primary && safe_camera_image_url(photo.url))
		|| photos.find((photo) => safe_camera_image_url(photo?.url));
	if (primary) {
		const image = document.createElement("img");
		image.className = "cam-pin-image";
		image.alt = cam_native_safe_text(camera.label || camera.name) || __("Camera image");
		image.loading = "lazy";
		image.referrerPolicy = "same-origin";
		image.src = primary.url;
		image.addEventListener("error", () => {
			image.replaceWith(camera_pin_fallback(camera));
		}, { once: true });
		shell.append(image);
	} else {
		shell.append(camera_pin_fallback(camera));
	}
	if (photos.length > 1) {
		const count = document.createElement("span");
		count.className = "cam-pin-count";
		count.textContent = String(photos.length);
		shell.append(count);
	}
	return L.divIcon({ className: "cam-leaflet-icon", html: cam_native_icon_html(shell), iconSize: [48, 62], iconAnchor: [24, 62], popupAnchor: [0, -58] });
}

function camera_pin_fallback(camera = {}) {
	const fallback = document.createElement("span");
	fallback.className = "cam-pin-fallback";
	fallback.textContent = cam_native_safe_text(camera.label || camera.name || "◉").trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "◉";
	return fallback;
}

function camera_card_fallback(camera = {}) {
	const fallback = document.createElement("span");
	fallback.className = "cam-camera-card-fallback";
	fallback.textContent = cam_native_safe_text(camera.label || camera.name || "◉").trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "◉";
	return fallback;
}

function camera_image_unavailable() {
	const unavailable = document.createElement("span");
	unavailable.className = "cam-image-unavailable";
	unavailable.textContent = navigator.onLine ? __("Image unavailable") : __("Not saved for offline use");
	return unavailable;
}

function safe_camera_image_url(value) {
	return typeof value === "string" && /^\/(?:private\/)?files\//.test(value);
}

function camera_map_popup(camera = {}) {
	const root = document.createElement("div");
	root.className = "cam-map-popup cam-camera-detail-popup";
	const gallery = append_camera_gallery(camera);
	const openEvents = () => {
		const name = cam_native_safe_text(camera.name);
		if (!name) return;
		frappe.route_options = Object.assign({}, frappe.route_options || {}, { camera: name });
		frappe.set_route("List", "Motion Event");
	};
	const card = camera_map_detail_card(camera, gallery, openEvents);
	if (gallery) card.append(gallery);

	const more = document.createElement("details");
	more.className = "cam-popup-more-details";
	const moreSummary = document.createElement("summary");
	moreSummary.textContent = __("More camera details");
	more.append(moreSummary);
	append_camera_info_group(more, "Camera identity", [
		["Serial number", camera.serial_number], ["Camera number", camera.camera_number],
		["Installation date", camera.installation_date], ["Field of view", camera.field_of_view],
	]);
	append_camera_info_group(more, "Geographic context", [
		["Geographic area", camera.geo_admin_area], ["Boundary", camera.geo_boundary],
	]);
	append_camera_info_group(more, "Coordinate quality", [
		["Lookup source", camera.lookup_source], ["Lookup confidence", camera.lookup_confidence],
		["Lookup ambiguous", camera.lookup_ambiguous ? __("Yes") : __("No")],
		["Lookup resolved at", camera.lookup_resolved_at],
	]);
	const descriptionText = cam_native_safe_text(camera.description);
	if (descriptionText) {
		const description = document.createElement("p");
		description.className = "cam-camera-card-description";
		description.textContent = descriptionText;
		more.append(description);
	}
	const relatedActions = document.createElement("div");
	relatedActions.className = "cam-camera-card-actions cam-camera-related-actions";
	for (const [label, doctype, value] of [
		["Camera type", "Camera Type", camera.camera_type], ["Open area", "Camera Area", camera.area],
		["Geographic area", "Geo Admin Area", camera.geo_admin_area], ["Boundary", "Geo Boundary", camera.geo_boundary],
	]) {
		const name = cam_native_safe_text(value);
		if (!name) continue;
		const related = document.createElement("button");
		related.type = "button";
		related.className = "btn btn-xs btn-default";
		related.textContent = __(label);
		related.addEventListener("click", () => frappe.set_route("Form", doctype, name));
		relatedActions.append(related);
	}
	if (relatedActions.childElementCount) more.append(relatedActions);
	if (more.querySelector(".cam-card-info-group, .cam-camera-card-description, .cam-camera-related-actions button")) card.append(more);

	root.append(card);
	L.DomEvent.disableClickPropagation(root);
	L.DomEvent.disableScrollPropagation(root);
	return root;
}

function append_camera_info_group(parent, label, fields) {
	const available = fields.map(([fieldLabel, value]) => [fieldLabel, cam_native_safe_text(value)])
		.filter(([, value]) => value !== "");
	if (!available.length) return;
	const group = document.createElement("section");
	group.className = "cam-card-info-group";
	const title = document.createElement("h5");
	title.textContent = __(label);
	group.append(title);
	const details = document.createElement("dl");
	details.className = "cam-popup-details";
	for (const [fieldLabel, value] of available) {
		const row = document.createElement("div");
		row.className = "cam-popup-detail";
		const key = document.createElement("dt");
		key.textContent = __(fieldLabel);
		const detail = document.createElement("dd");
		detail.textContent = value;
		row.append(key, detail);
		details.append(row);
	}
	group.append(details);
	parent.append(group);
}

function camera_map_detail_card(camera = {}, gallery, openEvents = () => {}) {
	const card = document.createElement("section");
	card.className = "cam-camera-detail-card";
	const photos = Array.isArray(camera.photos) ? camera.photos : [];
	const primary = photos.find((photo) => photo?.primary && safe_camera_image_url(photo.url))
		|| photos.find((photo) => safe_camera_image_url(photo?.url));
	const avatar = document.createElement("div");
	avatar.className = "cam-camera-card-avatar";
	avatar.setAttribute("aria-label", photos.length ? __("View camera photo gallery") : __("Camera image unavailable"));
	if (gallery && photos.length) {
		avatar.setAttribute("role", "button");
		avatar.tabIndex = 0;
		const showGallery = () => {
			gallery.open = true;
			window.requestAnimationFrame(() => gallery.querySelector(".cam-gallery-frame")?.scrollIntoView({ block: "nearest", behavior: "smooth" }));
		};
		avatar.addEventListener("click", showGallery);
		avatar.addEventListener("keydown", (event) => {
			if (event.key === "Enter" || event.key === " ") { event.preventDefault(); showGallery(); }
		});
	}
	if (primary) {
		const image = document.createElement("img");
		image.className = "cam-camera-card-image";
		image.alt = cam_native_safe_text(camera.label || camera.name) || __("Camera image");
		image.loading = "lazy";
		image.referrerPolicy = "same-origin";
		image.src = primary.url;
		image.addEventListener("error", () => image.replaceWith(camera_card_fallback(camera)), { once: true });
		avatar.append(image);
	} else {
		avatar.append(camera_card_fallback(camera));
	}

	const heading = document.createElement("header");
	heading.className = "cam-camera-card-heading";
	const title = document.createElement("strong");
	title.className = "cam-camera-card-title";
	title.textContent = cam_native_safe_text(camera.label || camera.name) || __("Camera details");
	const meta = document.createElement("div");
	meta.className = "cam-camera-card-meta";
	const subtitle = document.createElement("span");
	subtitle.className = "cam-camera-card-subtitle";
	subtitle.textContent = [camera.name, camera.camera_type].map(cam_native_safe_text).filter(Boolean).join(" · ") || __("Camera details");
	const status = cam_native_safe_text(camera.status);
	const statusBadge = document.createElement("span");
	statusBadge.className = `cam-camera-status-badge cam-camera-status-${(status || "unknown").toLowerCase()}`;
	statusBadge.textContent = status ? __(status) : __("Unknown status");
	meta.append(subtitle, statusBadge);
	heading.append(title, meta);
	if (camera.is_demo_record) {
		const badge = document.createElement("span");
		badge.className = "cam-demo-badge";
		badge.textContent = __("SYNTHETIC DEMO DATA");
		heading.append(badge);
	}
	card.append(avatar, heading);
	const divider = document.createElement("hr");
	divider.className = "cam-camera-card-divider";
	card.append(divider);

	const endpoint = cam_native_safe_text(camera.ip_address)
		? `${cam_native_safe_text(camera.ip_address)}${cam_native_safe_text(camera.port) ? `:${cam_native_safe_text(camera.port)}` : ""}`
		: cam_native_safe_text(camera.port) ? __("Port {0}", [cam_native_safe_text(camera.port)]) : "";
	const rows = [
		["Coordinates", `${cam_native_safe_text(camera.latitude)}, ${cam_native_safe_text(camera.longitude)}`, "cam-camera-card-coordinate"],
		["Camera Area", [camera.area, camera.address, camera.geo_admin_area].map(cam_native_safe_text).filter(Boolean).join(" · "), ""],
		["Type & Status", [camera.camera_type, camera.importance, status, endpoint].map(cam_native_safe_text).filter(Boolean).join(" · "), ""],
		["Gallery & Actions", [__("{0} photos", [photos.length]), cam_native_safe_text(camera.latest_activity) || __("No recent activity")].join(" · "), ""],
	];
	const sections = document.createElement("div");
	sections.className = "cam-camera-card-sections";
	for (const [label, value, extraClass] of rows) {
		const section = document.createElement("section");
		section.className = "cam-camera-card-section";
		const caption = document.createElement("span");
		caption.className = "cam-camera-card-label";
		caption.textContent = __(label);
		const detail = document.createElement("strong");
		detail.className = `cam-camera-card-value ${extraClass}`.trim();
		detail.textContent = value || __("Not recorded");
		section.append(caption, detail);
		if (label === "Gallery & Actions") {
			const actions = document.createElement("div");
			actions.className = "cam-camera-card-actions";
			const open = document.createElement("button");
			open.type = "button";
			open.className = "btn btn-xs btn-primary";
			open.textContent = __("Open camera");
			open.addEventListener("click", () => {
				const name = cam_native_safe_text(camera.name);
				if (name) frappe.set_route("Form", "Camera", name);
			});
			actions.append(open);
			if (gallery) {
				const galleryButton = document.createElement("button");
				galleryButton.type = "button";
				galleryButton.className = "btn btn-xs btn-default";
				galleryButton.textContent = __("Gallery");
				galleryButton.addEventListener("click", () => {
					gallery.open = true;
					window.requestAnimationFrame(() => gallery.querySelector(".cam-gallery-frame")?.scrollIntoView({ block: "nearest", behavior: "smooth" }));
				});
				actions.append(galleryButton);
			}
			const events = document.createElement("button");
			events.type = "button";
			events.className = "btn btn-xs btn-default";
			events.textContent = __("Events");
			events.addEventListener("click", openEvents);
			actions.append(events);
			section.append(actions);
		}
		sections.append(section);
	}
	card.append(sections);
	return card;
}

function append_camera_gallery(camera = {}) {
	const photos = Array.isArray(camera.photos) ? camera.photos : [];
	if (!photos.length) return null;
	let index = Math.max(0, photos.findIndex((photo) => photo?.primary));
	const gallery = document.createElement("details");
	gallery.className = "cam-camera-gallery";
	const heading = document.createElement("summary");
	heading.className = "cam-camera-gallery-heading";
	const title = document.createElement("span");
	title.className = "cam-camera-gallery-title";
	title.textContent = __("Photo gallery");
	const total = document.createElement("span");
	total.className = "cam-gallery-total";
	total.textContent = __("{0} photos", [photos.length]);
	heading.append(title, total);
	gallery.append(heading);
	const frame = document.createElement("div");
	frame.className = "cam-gallery-frame";
	frame.tabIndex = -1;
	frame.setAttribute("role", "group");
	frame.setAttribute("aria-label", __("Camera photo"));
	const caption = document.createElement("div");
	caption.className = "cam-gallery-caption";
	const controls = document.createElement("div");
	controls.className = "cam-gallery-controls";
	const count = document.createElement("span");
	count.className = "cam-gallery-count";
	const update = () => {
		const photo = photos[index] || {};
		if (safe_camera_image_url(photo.url)) {
			const image = document.createElement("img");
			image.className = "cam-gallery-image";
			image.alt = cam_native_safe_text(photo.caption || camera.label) || __("Camera image");
			image.loading = "lazy";
			image.referrerPolicy = "same-origin";
			image.src = photo.url;
			image.addEventListener("error", () => image.replaceWith(camera_image_unavailable()), { once: true });
			frame.replaceChildren(image);
		} else {
			frame.replaceChildren(camera_image_unavailable());
		}
		caption.textContent = cam_native_safe_text(photo.caption || photo.description);
		count.textContent = `${index + 1} / ${photos.length}`;
	};
	if (photos.length > 1) {
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
	}
	controls.append(count);
	gallery.append(frame, controls, caption);
	update();
	return gallery;
}
