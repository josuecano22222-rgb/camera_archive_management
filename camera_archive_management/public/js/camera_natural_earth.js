// Natural Earth vector geography for the Camera Archive map.
// Self-hosted reference layers (cultural + physical, points/lines/polygons at
// 1:110m, 1:50m and 1:10m), click-to-inspect country intelligence, and choropleth
// theming. All data comes from the Bench server's committed public-domain pack;
// no external map or statistics API is contacted.
(function () {
	"use strict";

	const API = "camera_archive_management.api.natural_earth.";
	const COUNTRY_IDS = { "110m": "countries_110m", "50m": "countries_50m" };
	const DETAIL_ZOOM = 5; // at/above this zoom, auto mode prefers 1:50m detail
	const RAMP = ["#ffffb2", "#fed976", "#feb24c", "#fd8d3c", "#f03b20", "#bd0026"];
	const NO_DATA_STYLE = { color: "#94a3b8", weight: 0.6, opacity: 0.7, fillColor: "#e2e8f0", fillOpacity: 0.08, dashArray: "2 3" };
	const HIGHLIGHT = { color: "#f59e0b", weight: 3, opacity: 1, fillOpacity: 0.25 };
	// Keys only; labels are translated at render time so this app-include bundle
	// never depends on the translation helper being ready when it is evaluated.
	const PROFILE_FIELDS = [
		"name", "name_long", "capital", "continent", "region", "subregion",
		"population_estimate", "gdp_million_usd", "area_km2", "economy", "income_group",
		"type", "sovereign",
	];
	const PROFILE_LABELS = {
		name: "Country", name_long: "Official name", capital: "Capital", continent: "Continent",
		region: "Region", subregion: "Subregion", population_estimate: "Population (estimate)",
		gdp_million_usd: "GDP, million USD (estimate)", area_km2: "Area, km² (approx.)",
		economy: "Economy group", income_group: "Income group", type: "Entity type", sovereign: "Sovereign",
	};
	const SKIP_VALUES = new Set(["", "-99", -99, "null", "None", null, undefined]);

	function esc(value) {
		return String(value ?? "").replace(/[&<>"']/g, (char) => ({
			"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
		})[char]);
	}

	function number(value) {
		if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) return "—";
		return new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(Number(value));
	}

	function call(method, args) {
		return frappe.call({ method: API + method, type: "GET", args: args || {} }).then((response) => response.message);
	}

	function state(page) {
		return page.cam_ne;
	}

	function iso_code(properties) {
		const iso = properties?.ISO_A3;
		if (typeof iso === "string" && /^[A-Za-z]{3}$/.test(iso)) return iso.toUpperCase();
		const adm = properties?.ADM0_A3;
		if (typeof adm === "string" && /^[A-Za-z]{3}$/.test(adm)) return adm.toUpperCase();
		return "";
	}

	function feature_label(spec, feature) {
		const properties = feature.properties || {};
		const value = properties[spec.name_field] || properties.NAME || properties.name || properties.ADMIN || properties.featurecla;
		return SKIP_VALUES.has(value) ? "" : String(value);
	}

	// ------------------------------------------------------------------ panel

	function build_panel(page) {
		const ne = state(page);
		const panel = document.createElement("div");
		panel.className = "cam-ne-panel";
		panel.hidden = true;
		panel.setAttribute("role", "dialog");
		panel.setAttribute("aria-label", __("Natural Earth geography layers"));
		panel.innerHTML = `
			<div class="cam-ne-head">
				<strong>${__("Geography · Natural Earth")}</strong>
				<button class="btn btn-default btn-xs cam-ne-close" type="button" aria-label="${__("Close geography panel")}">✕</button>
			</div>
			<div class="cam-ne-body">
				<section class="cam-ne-section">
					<h4>${__("Reference layers")}</h4>
					<div class="cam-ne-country-row">
						<label><input type="checkbox" class="cam-ne-countries"> ${__("Countries")}</label>
						<select class="form-control input-xs cam-ne-country-scale" aria-label="${__("Country detail scale")}">
							<option value="auto">${__("Auto detail by zoom")}</option>
							<option value="110m">${__("1:110m overview")}</option>
							<option value="50m">${__("1:50m detail")}</option>
						</select>
					</div>
					<div class="cam-ne-groups"><p class="text-muted">${__("Loading layer catalog…")}</p></div>
				</section>
				<section class="cam-ne-section">
					<h4>${__("Thematic map (choropleth)")}</h4>
					<div class="cam-ne-choropleth-controls">
						<label>${__("Metric")} <select class="form-control input-xs cam-ne-metric">
							<option value="cameras">${__("Cameras per country")}</option>
							<option value="movements">${__("Movements per country")}</option>
							<option value="population">${__("Population (NE estimate)")}</option>
							<option value="gdp">${__("GDP (NE estimate)")}</option>
							<option value="custom">${__("Custom data (ISO → number)")}</option>
						</select></label>
						<label>${__("Classes")} <select class="form-control input-xs cam-ne-classes">
							<option>3</option><option>4</option><option selected>5</option><option>6</option>
						</select></label>
						<label>${__("Method")} <select class="form-control input-xs cam-ne-method">
							<option value="quantile">${__("Quantile")}</option>
							<option value="equal_interval">${__("Equal interval")}</option>
						</select></label>
					</div>
					<textarea class="form-control cam-ne-custom-values" rows="3" hidden
						placeholder='{"NLD": 42, "FRA": 17.5}' aria-label="${__("Custom ISO country values as JSON")}"></textarea>
					<div class="cam-ne-choropleth-actions">
						<button class="btn btn-primary btn-xs cam-ne-choropleth-apply" type="button">${__("Apply theme")}</button>
						<button class="btn btn-default btn-xs cam-ne-choropleth-clear" type="button">${__("Clear theme")}</button>
					</div>
					<div class="cam-ne-legend" aria-live="polite"></div>
					<p class="cam-ne-choropleth-note text-muted"></p>
				</section>
				<section class="cam-ne-section">
					<h4>${__("Inspector")}</h4>
					<div class="cam-ne-inspector">
						<p class="text-muted">${__("Click a country, city, river, airport or any bundled feature — or click the map — to inspect it.")}</p>
					</div>
				</section>
			</div>
			<div class="cam-ne-foot"></div>`;
		const shell = page.main.get(0).querySelector(".cam-map-shell");
		shell.appendChild(panel);
		ne.panel = panel;
		const leaflet = page.cam_leaflet;
		if (leaflet?.DomEvent) {
			leaflet.DomEvent.disableClickPropagation(panel);
			leaflet.DomEvent.disableScrollPropagation(panel);
		}
		panel.querySelector(".cam-ne-close").addEventListener("click", () => toggle_panel(page, false));
		panel.querySelector(".cam-ne-countries").addEventListener("change", (event) => {
			ne.country_enabled = event.target.checked;
			sync_country_layer(page);
		});
		panel.querySelector(".cam-ne-country-scale").addEventListener("change", (event) => {
			ne.country_scale = event.target.value;
			sync_country_layer(page);
		});
		panel.querySelector(".cam-ne-metric").addEventListener("change", (event) => {
			panel.querySelector(".cam-ne-custom-values").hidden = event.target.value !== "custom";
		});
		panel.querySelector(".cam-ne-choropleth-apply").addEventListener("click", () => apply_choropleth(page));
		panel.querySelector(".cam-ne-choropleth-clear").addEventListener("click", () => clear_choropleth(page));
	}

	function toggle_panel(page, open) {
		const ne = state(page);
		ne.open = open === undefined ? !ne.open : Boolean(open);
		ne.panel.hidden = !ne.open;
		const button = page.main.get(0).querySelector(".cam-ne-open");
		if (button) button.classList.toggle("active", ne.open);
		if (ne.open && !ne.catalog) load_catalog(page);
	}

	async function load_catalog(page) {
		const ne = state(page);
		try {
			const catalog = await call("get_catalog");
			ne.catalog = catalog;
			ne.specs = Object.fromEntries(catalog.layers.map((layer) => [layer.id, layer]));
			render_layer_rows(page);
			const foot = ne.panel.querySelector(".cam-ne-foot");
			foot.textContent = `${catalog.license} · ${__("revision")} ${String(catalog.revision).slice(0, 12)} · ${catalog.limitations}`;
		} catch (error) {
			ne.panel.querySelector(".cam-ne-groups").innerHTML = `<p class="text-danger">${esc(error.message || __("Layer catalog could not be loaded."))}</p>`;
		}
	}

	function render_layer_rows(page) {
		const ne = state(page);
		const groups = ne.panel.querySelector(".cam-ne-groups");
		groups.replaceChildren();
		for (const category of ["cultural", "physical"]) {
			const layers = ne.catalog.layers.filter((layer) => layer.category === category && layer.theme !== "countries");
			if (!layers.length) continue;
			const group = document.createElement("div");
			group.className = "cam-ne-group";
			const heading = document.createElement("h5");
			heading.textContent = category === "cultural" ? __("Cultural") : __("Physical");
			group.appendChild(heading);
			for (const spec of layers) {
				const row = document.createElement("label");
				row.className = "cam-ne-row";
				row.title = spec.description || "";
				const checkbox = document.createElement("input");
				checkbox.type = "checkbox";
				checkbox.dataset.layer = spec.id;
				checkbox.checked = ne.enabled.has(spec.id);
				checkbox.addEventListener("change", (event) => set_layer_enabled(page, spec.id, event.target.checked));
				const label = document.createElement("span");
				label.className = "cam-ne-row-label";
				label.textContent = spec.label;
				const badge = document.createElement("span");
				badge.className = "cam-ne-badge";
				badge.textContent = spec.scale;
				const count = document.createElement("span");
				count.className = "cam-ne-count";
				count.textContent = number(spec.feature_count);
				row.append(checkbox, label, badge, count);
				group.appendChild(row);
			}
			groups.appendChild(group);
		}
	}

	// ----------------------------------------------------------------- layers

	async function ensure_layer(page, id) {
		const ne = state(page);
		if (ne.geojson[id]) return ne.geojson[id];
		if (ne.pending[id]) return ne.pending[id];
		ne.pending[id] = call("get_layer", { layer_id: id }).then((response) => {
			const spec = response.layer;
			const leaflet = page.cam_leaflet;
			const layer = leaflet.geoJSON(response.geojson, {
				style: (feature) => base_style(page, spec, feature),
				pointToLayer: (feature, latlng) => leaflet.circleMarker(latlng, { ...spec.style }),
				onEachFeature: (feature, child) => {
					const label = feature_label(spec, feature);
					if (label) child.bindTooltip(label, { sticky: true, direction: "auto" });
					child.on("click", (event) => {
						if (page.cam_tool_mode) return;
						leaflet.DomEvent.stopPropagation(event);
						inspect_feature(page, spec, feature, child);
					});
				},
			});
			ne.geojson[id] = layer;
			delete ne.pending[id];
			return layer;
		}).catch((error) => {
			delete ne.pending[id];
			throw error;
		});
		return ne.pending[id];
	}

	function base_style(page, spec, feature) {
		if (spec.theme === "countries") return country_style(page, feature);
		return { ...spec.style };
	}

	function country_style(page, feature) {
		const ne = state(page);
		const spec = ne.specs?.countries_110m || { style: { color: "#0f766e", weight: 1.2, fillColor: "#14b8a6", fillOpacity: 0.04 } };
		if (!ne.choropleth) return { ...spec.style };
		const code = iso_code(feature.properties);
		const value = ne.choropleth.values[code];
		if (value === undefined || value === null) return { ...NO_DATA_STYLE };
		const breaks = ne.choropleth.classification.breaks;
		let index = breaks.length - 1;
		for (let position = 0; position < breaks.length; position++) {
			if (value <= breaks[position]) { index = position; break; }
		}
		const color = RAMP[Math.min(index, RAMP.length - 1)];
		return { color: "#78716c", weight: 0.7, opacity: 0.8, fillColor: color, fillOpacity: 0.6 };
	}

	async function set_layer_enabled(page, id, enabled) {
		const ne = state(page);
		if (enabled) {
			ne.enabled.add(id);
			try {
				const layer = await ensure_layer(page, id);
				if (ne.enabled.has(id) && !page.cam_map.hasLayer(layer)) layer.addTo(page.cam_map);
				add_attribution(page);
			} catch (error) {
				ne.enabled.delete(id);
				const checkbox = ne.panel.querySelector(`input[data-layer="${id}"]`);
				if (checkbox) checkbox.checked = false;
				frappe.msgprint({ title: __("Natural Earth"), message: error.message || __("Layer could not be loaded."), indicator: "red" });
			}
		} else {
			ne.enabled.delete(id);
			const layer = ne.geojson[id];
			if (layer && page.cam_map.hasLayer(layer)) page.cam_map.removeLayer(layer);
		}
	}

	function active_country_id(page) {
		const ne = state(page);
		if (!ne.country_enabled) return null;
		if (ne.country_scale === "110m") return COUNTRY_IDS["110m"];
		if (ne.country_scale === "50m") return COUNTRY_IDS["50m"];
		return page.cam_map.getZoom() >= DETAIL_ZOOM ? COUNTRY_IDS["50m"] : COUNTRY_IDS["110m"];
	}

	function sync_country_layer(page) {
		const ne = state(page);
		const active = active_country_id(page);
		for (const id of Object.values(COUNTRY_IDS)) {
			const should_show = id === active;
			const checkbox = ne.panel.querySelector(`input[data-layer="${id}"]`);
			if (checkbox) checkbox.checked = should_show;
			if (should_show !== ne.enabled.has(id)) set_layer_enabled(page, id, should_show);
		}
		if (active && ne.choropleth) restyle_countries(page);
	}

	function on_zoom(page) {
		const ne = state(page);
		if (ne?.country_enabled && ne.country_scale === "auto") sync_country_layer(page);
	}

	function restyle_countries(page) {
		const ne = state(page);
		for (const id of Object.values(COUNTRY_IDS)) {
			const layer = ne.geojson[id];
			if (layer) layer.setStyle((feature) => country_style(page, feature));
		}
	}

	function add_attribution(page) {
		const ne = state(page);
		if (ne.attribution_added || !page.cam_map.attributionControl) return;
		page.cam_map.attributionControl.addAttribution("Natural Earth · public domain");
		ne.attribution_added = true;
	}

	// -------------------------------------------------------------- inspector

	function reset_highlight(page) {
		const ne = state(page);
		const previous = ne.highlight;
		if (!previous) return;
		const { child, spec, feature } = previous;
		if (child.setStyle) {
			child.setStyle(base_style(page, spec, feature));
			if (spec.geometry === "point" && child.setRadius) child.setRadius(spec.style.radius || 3.5);
		}
		ne.highlight = null;
	}

	function highlight(page, spec, feature, child) {
		reset_highlight(page);
		if (!child.setStyle) return;
		child.setStyle({ ...HIGHLIGHT });
		if (spec.geometry === "point" && child.setRadius) child.setRadius((spec.style.radius || 3.5) + 2.5);
		if (child.bringToFront) child.bringToFront();
		state(page).highlight = { child, spec, feature };
	}

	function properties_table(feature) {
		const properties = feature.properties || {};
		const rows = [];
		for (const [key, value] of Object.entries(properties)) {
			if (SKIP_VALUES.has(value) || typeof value === "object") continue;
			if (/^(ADM0_A3_|FCLASS_|NAME_[A-Z]{2}$|MAPCOLOR|.*_LEN$|MIN_|MAX_|.*RANK|NE_ID|WOE_|WIKIDATA|GEONAMES|UN_|WB_|FIPS|ISO_N3|.*_EH$|BRK_|SU_|GU_|SUBUNIT|HOMEPART|TINY|TLC|POSTAL|LABEL|featurecla|scalerank)/.test(key)) continue;
			rows.push(`<tr><th>${esc(key)}</th><td>${esc(value)}</td></tr>`);
			if (rows.length >= 16) break;
		}
		return rows.length ? `<table class="cam-ne-props">${rows.join("")}</table>` : "";
	}

	function inspect_feature(page, spec, feature, child) {
		const ne = state(page);
		highlight(page, spec, feature, child);
		const inspector = ne.panel.querySelector(".cam-ne-inspector");
		const label = feature_label(spec, feature) || spec.label;
		if (spec.theme === "countries") {
			const code = iso_code(feature.properties);
			inspector.innerHTML = `<p class="text-muted">${__("Loading country profile…")}</p>`;
			call("get_country_profile", code ? { code } : {}).then((response) => {
				render_country_card(page, response.profile, label, child);
			}).catch(() => {
				inspector.innerHTML = `<strong>${esc(label)}</strong>${properties_table(feature)}`;
			});
			return;
		}
		inspector.innerHTML = `
			<div class="cam-ne-card-head"><strong>${esc(label)}</strong><span class="cam-ne-badge">${esc(spec.scale)} · ${esc(spec.geometry)}</span></div>
			<p class="text-muted cam-ne-card-sub">${esc(spec.label)}</p>
			${properties_table(feature)}
			<button class="btn btn-default btn-xs cam-ne-zoom" type="button">${__("Zoom to feature")}</button>`;
		bind_zoom(page, inspector, child);
	}

	function render_country_card(page, profile, fallback_label, child) {
		const inspector = state(page).panel.querySelector(".cam-ne-inspector");
		if (!profile) {
			inspector.innerHTML = `<strong>${esc(fallback_label)}</strong><p class="text-muted">${__("No bundled profile is available for this feature.")}</p>`;
			return;
		}
		const rows = PROFILE_FIELDS.map((key) => {
			const label = __(PROFILE_LABELS[key]);
			let value = profile[key];
			if (key === "capital") value = profile.capital ? `${profile.capital.name}${profile.capital.admin1 ? " · " + profile.capital.admin1 : ""}` : null;
			if (SKIP_VALUES.has(value)) return "";
			if (["population_estimate", "gdp_million_usd", "area_km2"].includes(key)) value = number(value);
			return `<tr><th>${esc(label)}</th><td>${esc(value)}</td></tr>`;
		}).join("");
		const estimates = [profile.population_year, profile.gdp_year].filter(Boolean);
		inspector.innerHTML = `
			<div class="cam-ne-card-head"><strong>${esc(profile.name)}</strong><span class="cam-ne-badge">${esc(profile.code)}</span></div>
			<table class="cam-ne-props">${rows}</table>
			<p class="text-muted cam-ne-card-sub">${__("Bundled Natural Earth estimates")}${estimates.length ? " · " + esc([...new Set(estimates)].join("/")) : ""} · ${__("generalized boundaries, not legal or cadastral.")}</p>
			<button class="btn btn-default btn-xs cam-ne-zoom" type="button">${__("Zoom to country")}</button>`;
		bind_zoom(page, inspector, child, profile);
	}

	function bind_zoom(page, inspector, child, profile) {
		const button = inspector.querySelector(".cam-ne-zoom");
		if (!button) return;
		const label_point = profile && profile.label_latitude !== null && profile.label_longitude !== null
			? [profile.label_latitude, profile.label_longitude] : null;
		if (!child && !label_point) { button.remove(); return; }
		button.addEventListener("click", () => {
			if (child && child.getBounds) {
				page.cam_map.fitBounds(child.getBounds(), { maxZoom: 7, padding: [20, 20] });
			} else if (child && child.getLatLng) {
				page.cam_map.setView(child.getLatLng(), Math.max(page.cam_map.getZoom(), 6));
			} else if (label_point) {
				page.cam_map.setView(label_point, 5);
			}
		});
	}

	function inspect_point(page, latlng) {
		const ne = state(page);
		if (!ne?.open || !ne.catalog) return;
		const inspector = ne.panel.querySelector(".cam-ne-inspector");
		call("get_country_profile", { latitude: latlng.lat, longitude: latlng.lng }).then((response) => {
			if (response.profile) {
				render_country_card(page, response.profile, response.profile.name, null);
			} else {
				inspector.innerHTML = `<p class="text-muted">${__("No country at this point — open ocean or outside the bundled coverage.")}</p>`;
			}
		}).catch(() => { /* keep previous inspector content */ });
	}

	// ------------------------------------------------------------- choropleth

	async function apply_choropleth(page) {
		const ne = state(page);
		const panel = ne.panel;
		const metric = panel.querySelector(".cam-ne-metric").value;
		const method = panel.querySelector(".cam-ne-method").value;
		const classes = panel.querySelector(".cam-ne-classes").value;
		const args = { metric, method, classes };
		if (metric === "custom") args.values = panel.querySelector(".cam-ne-custom-values").value;
		const note = panel.querySelector(".cam-ne-choropleth-note");
		note.textContent = __("Computing thematic classes…");
		try {
			const result = await call("get_country_choropleth", args);
			ne.choropleth = result;
			if (!ne.country_enabled) {
				ne.country_enabled = true;
				panel.querySelector(".cam-ne-countries").checked = true;
			}
			sync_country_layer(page);
			restyle_countries(page);
			render_legend(page, result);
			const parts = [__("Metric: {0}", [metric]), __("method: {0}", [method])];
			if (result.meta.located_cameras !== undefined) parts.push(__("{0} located cameras", [number(result.meta.located_cameras)]));
			if (result.meta.truncated) parts.push(__("camera scan truncated at the safe limit"));
			if (result.meta.note) parts.push(result.meta.note);
			note.textContent = parts.join(" · ");
		} catch (error) {
			note.textContent = error.message || __("The thematic map could not be computed.");
		}
	}

	function clear_choropleth(page) {
		const ne = state(page);
		ne.choropleth = null;
		restyle_countries(page);
		ne.panel.querySelector(".cam-ne-legend").replaceChildren();
		ne.panel.querySelector(".cam-ne-choropleth-note").textContent = "";
	}

	function render_legend(page, result) {
		const legend = state(page).panel.querySelector(".cam-ne-legend");
		legend.replaceChildren();
		const breaks = result.classification.breaks || [];
		if (!breaks.length) {
			legend.textContent = __("No values are available for this metric.");
			return;
		}
		let lower = result.classification.min;
		breaks.forEach((upper, index) => {
			const row = document.createElement("div");
			row.className = "cam-ne-legend-row";
			const swatch = document.createElement("i");
			swatch.style.background = RAMP[Math.min(index, RAMP.length - 1)];
			const text = document.createElement("span");
			text.textContent = `${number(lower)} – ${number(upper)}`;
			row.append(swatch, text);
			legend.appendChild(row);
			lower = upper;
		});
		const no_data = document.createElement("div");
		no_data.className = "cam-ne-legend-row";
		const swatch = document.createElement("i");
		swatch.style.background = NO_DATA_STYLE.fillColor;
		swatch.style.border = "1px dashed #94a3b8";
		const text = document.createElement("span");
		text.textContent = __("No data");
		no_data.append(swatch, text);
		legend.appendChild(no_data);
	}

	// ------------------------------------------------------------- entrypoint

	function initialize(page, leaflet) {
		if (page.cam_ne) return;
		page.cam_ne = {
			leaflet,
			open: false,
			catalog: null,
			specs: {},
			geojson: {},
			pending: {},
			enabled: new Set(),
			country_enabled: false,
			country_scale: "auto",
			choropleth: null,
			highlight: null,
			attribution_added: false,
		};
		build_panel(page);
		const button = page.main.get(0).querySelector(".cam-ne-open");
		if (button) button.addEventListener("click", () => toggle_panel(page));
	}

	window.cam_natural_earth = { initialize, on_zoom, inspect_point, toggle_panel };
})();
