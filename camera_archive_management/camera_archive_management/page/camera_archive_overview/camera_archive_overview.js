frappe.pages["camera-archive-overview"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Camera Archive Overview"), single_column: true });
	page.main.addClass("cam-overview-page");
	page.set_primary_action(__("Refresh statistics"), () => load_workspace_summary(page), "refresh");
	page.set_secondary_action(__("Open map"), () => frappe.set_route("camera-archive-map"), "map");
	page.main.html(`
		<div class="cam-overview-shell">
			<div class="cam-overview-intro">
				<div><span class="cam-overview-eyebrow">${__("OPERATIONS CENTRE")}</span><h2>${__("Camera Archive Overview")}</h2><p>${__("Live, permission-aware snapshots of cameras, movement activity, vehicles, archives, and geographic data.")}</p></div>
				<div class="cam-overview-updated" data-updated>${__("Loading latest statistics…")}</div>
			</div>
			<div class="cam-overview-kpis" data-kpis></div>
			<div class="cam-overview-charts">
				<section class="cam-overview-chart-card cam-overview-chart-wide"><h3>${__("Daily movement activity")}</h3><p>${__("Visible Motion Events from the last 14 days")}</p><div data-chart="daily_movements"></div></section>
				<section class="cam-overview-chart-card"><h3>${__("Camera status")}</h3><p>${__("Cameras grouped by current status")}</p><div data-chart="camera_status"></div></section>
				<section class="cam-overview-chart-card"><h3>${__("Movement types")}</h3><p>${__("Visible entry and exit events")}</p><div data-chart="movement_types"></div></section>
				<section class="cam-overview-chart-card cam-overview-chart-wide"><h3>${__("Most-travelled vehicles")}</h3><p>${__("Top vehicles by visible movement records")}</p><div data-chart="top_vehicles"></div></section>
			</div>
			<div class="cam-overview-directory-heading"><div><span class="cam-overview-eyebrow">${__("QUICK ACCESS")}</span><h2>${__("Browse workspace")}</h2></div><span>${__("Choose a section to open its records, reports, or map.")}</span></div>
			<div class="cam-overview-directory" data-directory></div>
			<p class="cam-overview-footnote">${__("Statistics follow your Frappe permissions. Sensitive credential records remain protected by their DocType permissions.")}</p>
		</div>
	`);
	render_workspace_directory(page);
	load_workspace_summary(page);
};

const CAM_OVERVIEW_GROUPS = [
	{
		label: "Maps & Analysis",
		icon: "⌖",
		links: [
			["Camera Archive Map", "Page", "camera-archive-map"],
			["Camera Coverage", "Report", "Camera Coverage"],
			["Vehicle Movement Timeline", "Report", "Vehicle Movement Timeline"],
			["Geo Location Quality", "Report", "Geo Location Quality"],
		],
	},
	{
		label: "Camera Registry",
		icon: "◉",
		links: [["Camera", "DocType"], ["Camera Area", "DocType"], ["Camera Type", "DocType"], ["Camera Credential", "DocType"]],
	},
	{
		label: "Movements & Vehicles",
		icon: "⇢",
		links: [["Motion Event", "DocType"], ["CAM Vehicle", "DocType"], ["Vehicle Type", "DocType"]],
	},
	{
		label: "Geographic Reference",
		icon: "◎",
		links: [["Geo Dataset", "DocType"], ["Geo Admin Area", "DocType"], ["Geo Boundary", "DocType"], ["Geo Gazetteer Place", "DocType"], ["CAM Geo Settings", "DocType"]],
	},
	{
		label: "Archive & Configuration",
		icon: "▤",
		links: [["Archive Asset", "DocType"], ["Archive Ingest Batch", "DocType"], ["Archive Integrity", "Report"], ["Archive Settings", "DocType"]],
	},
];

function render_workspace_directory(page) {
	const directory = page.main.get(0).querySelector("[data-directory]");
	for (const group of CAM_OVERVIEW_GROUPS) {
		const section = document.createElement("section");
		section.className = "cam-overview-directory-card";
		const heading = document.createElement("h3");
		const icon = document.createElement("span");
		icon.setAttribute("aria-hidden", "true");
		icon.textContent = group.icon;
		heading.append(icon, document.createTextNode(` ${__(group.label)}`));
		const links = document.createElement("div");
		links.className = "cam-overview-directory-links";
		for (const [label, type, target] of group.links) {
			const button = document.createElement("button");
			button.type = "button";
			button.className = "cam-overview-link";
			button.textContent = __(label);
			button.addEventListener("click", () => {
				if (type === "Page") frappe.set_route(target);
				else if (type === "Report") frappe.set_route("query-report", target);
				else frappe.set_route("List", target, "List");
			});
			links.append(button);
		}
		section.append(heading, links);
		directory.append(section);
	}
}

async function load_workspace_summary(page) {
	const host = page.main.get(0);
	host.querySelector("[data-updated]").textContent = __("Loading latest statistics…");
	try {
		const response = await frappe.call({ method: "camera_archive_management.api.workspace.get_workspace_summary" });
		const data = response.message || {};
		render_workspace_kpis(host, data.counts || {});
		for (const series of ["daily_movements", "camera_status", "movement_types", "top_vehicles"]) {
			render_workspace_chart(host.querySelector(`[data-chart="${series}"]`), data[series] || [], series);
		}
		host.querySelector("[data-updated]").textContent = __("Updated {0}", [data.generated_on || __("just now")]);
	} catch (_error) {
		host.querySelector("[data-updated]").textContent = __("Statistics are unavailable. Your shortcuts are still ready.");
		for (const container of host.querySelectorAll("[data-chart]")) {
			container.textContent = __("Chart data unavailable");
		}
	}
}

function render_workspace_kpis(host, counts) {
	const cards = [
		["Cameras", counts.cameras, "◉", "#0f766e"],
		["Motion Events", counts.movements, "⇢", "#f97316"],
		["Vehicles", counts.vehicles, "🚘", "#4f46e5"],
		["Archive Assets", counts.archive_assets, "▤", "#0891b2"],
		["Ingest Batches", counts.ingest_batches, "⇧", "#7c3aed"],
	];
	const kpis = host.querySelector("[data-kpis]");
	kpis.replaceChildren();
	for (const [label, value, icon, color] of cards) {
		if (value === undefined) continue;
		const card = document.createElement("article");
		card.className = "cam-overview-kpi";
		card.style.setProperty("--cam-kpi-color", color);
		const glyph = document.createElement("span");
		glyph.className = "cam-overview-kpi-icon";
		glyph.setAttribute("aria-hidden", "true");
		glyph.textContent = icon;
		const caption = document.createElement("span");
		caption.textContent = __(label);
		const total = document.createElement("strong");
		total.textContent = new Intl.NumberFormat().format(Number(value) || 0);
		card.append(glyph, caption, total);
		kpis.append(card);
	}
}

function render_workspace_chart(container, rows, series) {
	container.replaceChildren();
	if (!Array.isArray(rows) || !rows.length) {
		const empty = document.createElement("p");
		empty.className = "cam-overview-chart-empty";
		empty.textContent = __("No visible data for this chart yet.");
		container.append(empty);
		return;
	}
	const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
	svg.setAttribute("viewBox", "0 0 640 210");
	svg.setAttribute("role", "img");
	const chartLabels = {
		daily_movements: __("Daily movement activity"), camera_status: __("Camera status"),
		movement_types: __("Movement types"), top_vehicles: __("Most-travelled vehicles"),
	};
	svg.setAttribute("aria-label", chartLabels[series] || __("Statistics chart"));
	const max = Math.max(1, ...rows.map((row) => Number(row.value) || 0));
	const slot = 620 / rows.length;
	rows.forEach((row, index) => {
		const value = Math.max(0, Number(row.value) || 0);
		const height = Math.max(value > 0 ? 2 : 0, (value / max) * 142);
		const x = 12 + index * slot + slot * 0.13;
		const width = Math.max(4, slot * 0.68);
		const bar = document.createElementNS("http://www.w3.org/2000/svg", "rect");
		bar.setAttribute("x", String(x));
		bar.setAttribute("y", String(158 - height));
		bar.setAttribute("width", String(width));
		bar.setAttribute("height", String(height));
		bar.setAttribute("rx", "5");
		bar.setAttribute("class", index === rows.length - 1 ? "cam-overview-bar is-current" : "cam-overview-bar");
		const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
		title.textContent = `${safe_overview_text(row.label)}: ${value}`;
		bar.append(title);
		svg.append(bar);
		if (rows.length <= 14 || index % Math.ceil(rows.length / 8) === 0 || index === rows.length - 1) {
			const caption = document.createElementNS("http://www.w3.org/2000/svg", "text");
			caption.setAttribute("x", String(x + width / 2));
			caption.setAttribute("y", "184");
			caption.setAttribute("text-anchor", "middle");
			caption.setAttribute("class", "cam-overview-chart-label");
			const label = safe_overview_text(row.label);
			caption.textContent = series === "daily_movements" ? label.slice(5) : label.slice(0, 12);
			svg.append(caption);
		}
		const number = document.createElementNS("http://www.w3.org/2000/svg", "text");
		number.setAttribute("x", String(x + width / 2));
		number.setAttribute("y", String(Math.max(12, 151 - height)));
		number.setAttribute("text-anchor", "middle");
		number.setAttribute("class", "cam-overview-chart-value");
		number.textContent = String(value);
		svg.append(number);
	});
	container.append(svg);
}

function safe_overview_text(value) {
	return typeof value === "string" && !/\[object (?:Object|[A-Za-z0-9_]*Element)\]/i.test(value) ? value : "";
}
