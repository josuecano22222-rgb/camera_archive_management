/* Restore Frappe's Leaflet.Draw dependency only for Camera's native Geolocation field.
 *
 * Siraj's GeoPoint control deliberately suppresses Frappe's stock map only for
 * fields named `geo_point`. Camera's field is named `location`, so it continues
 * through Frappe's native control. If another app has replaced `window.L` with
 * its Leaflet build, `L.Control.Draw` may be missing even after Frappe's bundle
 * resolves. Load Frappe's own plugin onto the active Leaflet instance before
 * the Camera map is constructed; do not replace Leaflet or alter other forms.
 */
(() => {
	"use strict";

	const DRAW_JS = "/assets/frappe/js/lib/leaflet_draw/leaflet.draw.js";
	const DRAW_CSS = "/assets/frappe/js/lib/leaflet_draw/leaflet.draw.css";
	let drawAssetsPromise;

	function isCameraLocation(control) {
		return control?.frm?.doctype === "Camera" && control?.df?.fieldname === "location";
	}

	function loadDrawAssets() {
		if (window.L?.Control?.Draw) return Promise.resolve();
		if (!drawAssetsPromise) {
			const cssUrl = new URL(DRAW_CSS, window.location.origin).href;
			const existing = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).find(
				(link) => link.href === cssUrl
				);
			const cssPromise = existing ? Promise.resolve() : new Promise((resolve, reject) => {
				const link = document.createElement("link");
				link.rel = "stylesheet";
				link.href = DRAW_CSS;
				link.onload = resolve;
				link.onerror = () => reject(new Error("Frappe's Leaflet.Draw stylesheet failed to load."));
				document.head.appendChild(link);
			});
			drawAssetsPromise = Promise.all([frappe.require(DRAW_JS), cssPromise]).then(() => {
				if (!window.L?.Control?.Draw) {
					throw new Error("Frappe's Leaflet.Draw plugin did not attach to the active Leaflet instance.");
				}
			});
		}
		return drawAssetsPromise;
	}

	function install() {
		const Control = frappe.ui?.form?.ControlGeolocation;
		if (!Control || Control.prototype.__camDrawCompatibilityInstalled) return Boolean(Control);
		const originalLoadLib = Control.prototype.load_lib;
		if (typeof originalLoadLib !== "function") return false;

		Control.prototype.load_lib = function (...args) {
			const loaded = originalLoadLib.apply(this, args);
			if (!isCameraLocation(this)) return loaded;
			return Promise.resolve(loaded).then(() => loadDrawAssets());
		};
		Control.prototype.__camDrawCompatibilityInstalled = true;
		return true;
	}

	// The app include normally runs after form controls load. Retry briefly for
	// builds where the form bundle is lazy-loaded, and on later Desk route changes.
	function installWithRetry(attempt = 0) {
		if (install() || attempt >= 40) return;
		window.setTimeout(() => installWithRetry(attempt + 1), 25);
	}

	installWithRetry();
	if (frappe.router?.on) {
		frappe.router.on("change", () => installWithRetry());
	}
})();
