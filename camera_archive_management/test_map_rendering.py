from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).parent / "camera_archive_management"
MAP_SCRIPT = APP_ROOT / "page" / "camera_archive_map" / "camera_archive_map.js"
CAMERA_LIST_SCRIPT = APP_ROOT / "doctype" / "camera" / "camera_list.js"

NODE_REGRESSION_TEST = r"""
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");

class FakeElement {
  constructor(tag = "div", markup = "", text = "") {
    this.nodeType = 1;
    this.tagName = tag.toUpperCase();
    this._markup = markup;
    this._text = text;
    this.children = [];
    this.className = "";
  }
  get outerHTML() {
    return this._markup || `<${this.tagName.toLowerCase()}>${this._text}</${this.tagName.toLowerCase()}>`;
  }
  get textContent() { return this._text + this.children.map((child) => child?.textContent || "").join(""); }
  set textContent(value) { this._text = value; this.children = []; }
  get innerHTML() { return this._markup; }
  set innerHTML(value) { this._markup = value; this.children = []; }
  get childElementCount() { return this.children.length; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this[name] = value; }
  addEventListener() {}
  querySelector() { return null; }
  cloneNode() { return new FakeElement(this.tagName.toLowerCase(), this._markup, this._text); }
}

function declaration(source, name) {
  const expression = new RegExp(`^function ${name}\\b[\\s\\S]*?^}`, "m");
  const match = source.match(expression);
  assert.ok(match, `Missing helper function: ${name}`);
  return match[0];
}

const configurations = [
  {
    path: process.argv[1],
    names: ["cam_archive_is_object_string", "cam_archive_dom_node", "cam_archive_mount_icon_content", "cam_archive_icon_html", "cam_archive_safe_text", "node"],
    api: "cam_archive",
    renderNames: ["camera_detail_card", "camera_popup", "append_archive_camera_info_group", "add_popup_detail", "movement_popup", "add_movement_card", "add_record_link"],
    calls: ["cam_archive_mount_icon_content(host, pinMarkup)", "html: host.innerHTML", "html: cam_archive_icon_html(shell)"],
  },
  {
    path: process.argv[2],
    names: ["cam_native_is_object_string", "cam_native_dom_node", "cam_native_mount_icon_content", "cam_native_icon_html", "cam_native_safe_text"],
    api: "cam_native",
    renderNames: ["camera_map_detail_card", "camera_map_popup", "append_camera_info_group", "append_camera_gallery"],
    calls: ["cam_native_mount_icon_content(host, pinMarkup)", "html: host.innerHTML", "html: cam_native_icon_html(shell)"],
  },
];

for (const configuration of configurations) {
  const source = fs.readFileSync(configuration.path, "utf8");
  for (const call of configuration.calls) assert.ok(source.includes(call), `${configuration.path} must use ${call}`);
  assert.ok(!source.includes("host.innerHTML = window.sirajIcons.pin"), `${configuration.path} must not coerce Siraj icon results`);

  const context = vm.createContext({ FakeElement, document: { createElement: (tag) => new FakeElement(tag) } });
  const declarations = configuration.names.map((name) => declaration(source, name)).join("\n");
  const apiNames = configuration.names.slice(0, 5);
  vm.runInContext(`${declarations}\nthis.testApi = { ${apiNames.join(", ")} };`, context);
  const api = context.testApi;
  const pinNode = new FakeElement("div", '<div class="siraj-pin"><span class="siraj-pin-body">camera</span></div>', "camera");
  const markup = '<div class="siraj-pin"><span class="siraj-pin-body"></span></div>';
  const wrapper = { jquery: "3.7.1", 0: pinNode, length: 1 };
  const host = new FakeElement();

  assert.equal(api[`${configuration.api}_mount_icon_content`](host, pinNode), true);
  assert.equal(host.children.length, 1, "DOM icons must be appended as nodes");
  assert.equal(api[`${configuration.api}_mount_icon_content`](new FakeElement(), wrapper), true, "jQuery-wrapped DOM icons must be unwrapped");
  assert.equal(api[`${configuration.api}_mount_icon_content`](new FakeElement(), markup), true, "HTML strings remain supported");
  assert.equal(api[`${configuration.api}_mount_icon_content`](new FakeElement(), "[object HTMLDivElement]"), false);
  assert.equal(api[`${configuration.api}_icon_html`](pinNode), pinNode.outerHTML);
  assert.equal(api[`${configuration.api}_icon_html`](wrapper), pinNode.outerHTML);
  assert.equal(api[`${configuration.api}_icon_html`](markup), markup);
  assert.equal(api[`${configuration.api}_icon_html`]({}), "", "unknown objects must become an empty icon, never text");
  assert.equal(api[`${configuration.api}_icon_html`]("[object Object]"), "");
  assert.equal(api[`${configuration.api}_safe_text`](pinNode), "camera");
  assert.equal(api[`${configuration.api}_safe_text`]({}), "");
  assert.equal(api[`${configuration.api}_safe_text`]("[object HTMLDivElement]"), "");
  if (api.node) {
    const card = api.node("div", "test-card", pinNode);
    assert.equal(card.children.length, 1, "popup/card DOM content must be mounted as a node");
    assert.equal(card.textContent, "");
    assert.equal(api.node("div", "test-card", {}).textContent, "", "plain objects must never stringify into a card");
  }
  const renderedIconHtml = api[`${configuration.api}_icon_html`](pinNode);
  assert.ok(!/\[object (?:HTMLDivElement|Object)\]/.test(renderedIconHtml));

  const renderDeclarations = configuration.renderNames.map((name) => declaration(source, name)).join("\n");
  const runtime = `
    function __(text, values) { return values ? values.reduce((result, value, index) => result.replace("{" + index + "}", value), text) : text; }
    function image_node() { return null; }
    function safe_camera_image_url() { return false; }
    function camera_card_fallback() { return new FakeElement("span", "", "image unavailable"); }
    function camera_image_unavailable() { return new FakeElement("span", "", "image unavailable"); }
    const L = { DomEvent: { disableClickPropagation() {}, disableScrollPropagation() {} } };
    const frappe = { route_options: {}, set_route() {} };
    const window = { requestAnimationFrame(callback) { callback(); } };
    const navigator = { onLine: false };
    ${renderDeclarations}
    this.renderTargets = configuration.api === "cam_archive"
      ? { camera_detail_card, camera_popup, movement_popup, add_movement_card }
      : { camera_map_detail_card, camera_map_popup };
  `;
  context.configuration = configuration;
  vm.runInContext(runtime, context);
  const rendered = context.renderTargets;
  const poisonedCamera = {
    name: {}, label: new FakeElement("div", "", "[object Object]"), status: {}, latitude: {}, longitude: {},
    camera_type: {}, area: {}, description: {}, latest_activity: {}, photos: [null, { primary: true, url: {} }],
  };
  const card = configuration.api === "cam_archive"
    ? rendered.camera_detail_card(poisonedCamera, {}, null, () => {})
    : rendered.camera_map_detail_card(poisonedCamera, null, () => {});
  assert.ok(!/\\[object (?:HTMLDivElement|Object)\\]/.test(card.textContent), "camera card output must not contain object coercions");
  if (configuration.api === "cam_archive") {
    const popup = rendered.camera_popup(poisonedCamera, { cam_leaflet: { DomEvent: { disableClickPropagation() {}, disableScrollPropagation() {} } } }, [{ camera: {}, motion_type: {}, detected_at: {}, name: {} }]);
    const movement = rendered.movement_popup({
      name: {}, vehicle: {}, vehicle_name: {}, motion_type: {}, detected_at: {}, vehicle_image: {},
      nearby_cameras: [{ camera: {}, distance_m: {}, bearing: {}, area: {}, note: {} }],
    }, {});
    let movementCard;
    rendered.add_movement_card({ main: { find() { return { append(value) { movementCard = value; } }; } } }, {
      name: {}, latitude: {}, longitude: {}, vehicle_name: {}, motion_type: {}, detected_at: {}, vehicle_number: {}, vehicle_image: {},
    });
    for (const output of [popup, movement, movementCard]) {
      assert.ok(!/\\[object (?:HTMLDivElement|Object)\\]/.test(output?.textContent || ""), "archive popup and movement outputs must be clean");
    }
  } else {
    const popup = rendered.camera_map_popup(poisonedCamera);
    assert.ok(!/\\[object (?:HTMLDivElement|Object)\\]/.test(popup.textContent), "native camera popup output must be clean");
  }
}
"""


class TestMapRenderingSerialization(unittest.TestCase):
	@unittest.skipUnless(shutil.which("node"), "Node.js is needed to run the map DOM regression checks")
	def test_map_icons_and_dom_text_never_stringify_objects(self):
		subprocess.run(
			["node", "-e", NODE_REGRESSION_TEST, str(MAP_SCRIPT), str(CAMERA_LIST_SCRIPT)],
			check=True,
			capture_output=True,
			text=True,
		)

	def test_map_views_use_safe_icon_markup_for_camera_and_vehicle_symbols(self):
		page_script = MAP_SCRIPT.read_text(encoding="utf-8")
		camera_script = CAMERA_LIST_SCRIPT.read_text(encoding="utf-8")
		self.assertIn("function vehicle_icon", page_script)
		self.assertIn("cam_archive_icon_html(shell)", page_script)
		self.assertIn("cam_native_icon_html(shell)", camera_script)
		self.assertIn("function camera_map_popup", camera_script)
		self.assertIn("function camera_map_detail_card", camera_script)
		self.assertIn("function camera_popup", page_script)
		self.assertIn("function camera_detail_card", page_script)
		self.assertIn("function movement_popup", page_script)
		self.assertIn("function add_movement_card", page_script)
		self.assertIn("cam_archive_safe_text(movement.detected_at)", page_script)
		self.assertIn("cam_native_safe_text(photo.caption || photo.description)", camera_script)
		self.assertIn("camera_image_unavailable()", camera_script)
		self.assertIn("safe_camera_image_url(photo.url)", camera_script)
		self.assertIn("Not saved for offline use", camera_script)
		self.assertIn("cam-image-unavailable", page_script)
		for script in (page_script, camera_script):
			self.assertNotIn("innerHTML = window.sirajIcons.pin", script)
			self.assertNotIn("html: shell", script)
			self.assertNotIn("html: host,", script)


if __name__ == "__main__":
	unittest.main()
