from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

MOTION_SCRIPT = Path(__file__).parent / "camera_archive_management" / "doctype" / "motion_event" / "motion_event_list.js"

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

	def test_maps_use_configured_vehicle_images_and_neutral_saved_points(self):
		motion_list = MOTION_SCRIPT.read_text(encoding="utf-8")
		archive_map = (MOTION_SCRIPT.parents[2] / "page" / "camera_archive_map" / "camera_archive_map.js").read_text(encoding="utf-8")
		self.assertIn("vehicle_image", motion_list)
		self.assertIn("cam-motion-user-point", motion_list)
		self.assertIn("vehicle_image", archive_map)
		self.assertIn("cam-map-user-location-point", archive_map)
		for source in (motion_list, archive_map):
			self.assertNotIn("🚘", source)
			self.assertNotIn("🚐", source)
			self.assertNotIn("🚚", source)
			self.assertNotIn("🚌", source)
		self.assertNotIn("🏍️", source)
		self.assertNotIn("motion_vehicle_color", source)


if __name__ == "__main__":
	unittest.main()
