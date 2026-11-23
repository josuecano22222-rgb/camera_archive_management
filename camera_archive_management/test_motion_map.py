from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

MOTION_SCRIPT = Path(__file__).parent / "camera_archive_management" / "doctype" / "motion_event" / "motion_event_list.js"

MOTION_FORM_SCRIPT = Path(__file__).parent / "camera_archive_management" / "doctype" / "motion_event" / "motion_event.js"

NODE_NEARBY_ALERT_TEST = r"""
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const source = fs.readFileSync(process.argv[1], "utf8");
const methods = {};
const messages = [];
const frappe = {
  ui: { form: { on(doctype, handlers) { methods[doctype] = handlers; } } },
  utils: { escape_html(value) {
    return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;").replaceAll("'", "&#39;");
  } },
  msgprint(message) { messages.push(message); },
};
function __(text, args) {
  return (args || []).reduce((value, arg, index) => value.replace(`{${index}}`, arg), text);
}
vm.runInNewContext(source, { frappe, __ });
const frm = { doc: {
  name: "MOT-1", docstatus: 0,
  nearby_cameras: [{
    camera: "CAM-NEAR-1", note: "Configured connection: Shared intersection",
    distance_m: 234.5, bearing_compass: "NW", area: "West",
  }],
} };
methods["Motion Event"].after_save(frm);
assert.equal(messages.length, 1, "saving with linked cameras shows an alert");
assert.match(messages[0].message, /saved/);
assert.match(messages[0].message, /configured camera connection/);
assert.match(messages[0].message, /234\.5 m/);
frm.doc.docstatus = 1;
methods["Motion Event"].on_submit(frm);
assert.equal(messages.length, 2, "submission shows the alert for the approval transition too");
assert.match(messages[1].message, /submitted/);
methods["Motion Event"].on_submit(frm);
assert.equal(messages.length, 2, "the same submit transition is not announced twice");
const empty = { doc: { name: "MOT-2", docstatus: 0, nearby_cameras: [] } };
methods["Motion Event"].after_save(empty);
assert.equal(messages.length, 2, "no nearby cameras produces no alert");
"""

NODE_CLUSTER_TEST = r"""
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const source = fs.readFileSync(process.argv[1], "utf8");
function declaration(name) {
  const match = source.match(new RegExp(`^function ${name}\\b[\\s\\S]*?^}`, "m"));
  assert.ok(match, `Missing ${name}`);
  return match[0];
}
const code = [
  "safe_motion_text", "count_motion_events_by_vehicle", "group_motion_events_by_vehicle_and_camera",
  "cluster_motion_event_features",
].map(declaration).join("\n");
const leaflet = {
  latLng(lat, lng) { return { lat, lng }; },
  point(x, y) { return { x, y }; },
};
const context = vm.createContext({ L: leaflet, window: { L: leaflet } });
vm.runInContext(`${code}\nthis.api = { count_motion_events_by_vehicle, group_motion_events_by_vehicle_and_camera, cluster_motion_event_features };`, context);
const f = (name, vehicle, camera, x, y) => ({
  properties: { name, vehicle, camera, camera_name: camera, vehicle_name: vehicle, vehicle_type: "Van" },
  geometry: { type: "Point", coordinates: [x, y] },
});
const features = [
  f("MOT-1", "VEH-1", "CAM-1", 4.8, 52.3),
  f("MOT-2", "VEH-1", "CAM-1", 4.80001, 52.30001),
  f("MOT-3", "VEH-2", "CAM-1", 4.80002, 52.30002),
  f("MOT-4", "VEH-1", "CAM-2", 5.2, 52.8),
];
const map = {
  getZoom() { return 8; },
  project(latlng) { return { x: latlng.lng * 1000, y: latlng.lat * 1000 }; },
  unproject(point) { return { lng: point.x / 1000, lat: point.y / 1000 }; },
};
const clusters = context.api.cluster_motion_event_features(features, map, 58);
assert.equal(clusters.length, 2, "nearby movement points should cluster while distant camera points stay separate");
assert.equal(clusters.find((cluster) => cluster.rows.length === 3).rows.length, 3);
const counts = context.api.count_motion_events_by_vehicle(features);
assert.equal(counts.get("VEH-1"), 3, "the vehicle total counts all visible movement records");
const vehicleGroups = context.api.group_motion_events_by_vehicle_and_camera(clusters.find((cluster) => cluster.rows.length === 3).rows);
assert.equal(vehicleGroups.length, 2, "expanded camera clusters group repeated records per vehicle");
assert.equal(vehicleGroups.find((group) => group.vehicle === "VEH-1").rows.length, 2);
assert.equal(context.api.group_motion_events_by_vehicle_and_camera(features).length, 3, "one vehicle at different cameras remains a distinct location group");
assert.equal(context.api.count_motion_events_by_vehicle([{ properties: { vehicle: {} } }]).size, 0, "invalid object keys are ignored");
"""


class TestMotionMapClustering(unittest.TestCase):
	@unittest.skipUnless(shutil.which("node"), "Node.js is needed to run motion clustering regression checks")
	def test_map_clustering_expansion_groups_and_vehicle_totals(self):
		subprocess.run(["node", "-e", NODE_CLUSTER_TEST, str(MOTION_SCRIPT)], check=True, capture_output=True, text=True)

	@unittest.skipUnless(shutil.which("node"), "Node.js is needed to run nearby-camera alert checks")
	def test_nearby_camera_alert_appears_after_save_and_submit(self):
		subprocess.run(
			["node", "-e", NODE_NEARBY_ALERT_TEST, str(MOTION_FORM_SCRIPT)],
			check=True,
			capture_output=True,
			text=True,
		)

	def test_motion_event_doctype_uses_siraj_pin_template_and_user_icons(self):
		motion_list = MOTION_SCRIPT.read_text(encoding="utf-8")
		self.assertIn("vehicle_image", motion_list)
		self.assertIn('sirajIcons.pin("CAM Vehicle"', motion_list)
		self.assertIn('className: "sx-pin-wrapper cam-leaflet-icon"', motion_list)
		self.assertIn("motion_unconfigured_location_icon", motion_list)
		self.assertNotIn("🚘", motion_list)
		self.assertNotIn("🚐", motion_list)
		self.assertNotIn("🚚", motion_list)
		self.assertNotIn("🚌", motion_list)
		self.assertNotIn("🏍️", motion_list)
		self.assertNotIn("motion_vehicle_color", motion_list)


if __name__ == "__main__":
	unittest.main()
