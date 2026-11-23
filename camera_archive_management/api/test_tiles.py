from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from camera_archive_management.api import tiles
from camera_archive_management.geo import tile_cache

_PNG = b"\x89PNG\r\n\x1a\n" + b"test-tile-payload"


class _SirajCatalog:
	_ENABLE_FLAG: ClassVar[dict[str, str]] = {
		"standard": "enable_standard", "aerial": "enable_aerial", "hybrid": "enable_hybrid"
	}
	LAYERS: ClassVar[dict[str, dict[str, object]]] = {
		"standard": {
			"label": "Standard test map",
			"attribution": "Test provider attribution",
			"url": "https://tiles.example.invalid/{z}/{x}/{y}.png",
			"content_type": "image/png",
			"user_agent": "Siraj-Test/1.0",
			"min_zoom": 0,
			"max_zoom": 18,
		}
	}

	@staticmethod
	def _settings():
		return SimpleNamespace(allow_fetch=True, enable_standard=True, cache_days=90)


class TestTileEndpoints(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.original_user = frappe.session.user
		frappe.set_user("Administrator")
		self.temp_dir = tempfile.TemporaryDirectory(prefix="cam-tile-api-test-")
		self.private_path = Path(self.temp_dir.name)
		self.addCleanup(self.temp_dir.cleanup)
		self.addCleanup(frappe.set_user, self.original_user)

	def _call_cache_only(self, z, x, y):
		with (
			patch.object(frappe, "get_site_path", return_value=str(self.private_path)),
			patch.object(tiles, "_siraj_module", return_value=None),
		):
			return tiles.tile("standard", "base", z, x, y)

	def test_valid_xyz_misses_are_clean_404s_not_417s(self):
		for z, x, y in (("9", "305", "208"), ("10", "607", "418")):
			with self.subTest(z=z, x=x, y=y):
				response = self._call_cache_only(z, x, y)
				self.assertEqual(response.status_code, 404)
				self.assertEqual(response.mimetype, "application/json")
				self.assertEqual(json.loads(response.get_data(as_text=True))["error"], "tile_missing")

	def test_canonical_cache_hit_needs_no_siraj_or_provider(self):
		tile_cache.write_cached_tile(self.private_path, "standard", "base", 9, 305, 208, "png", _PNG)
		response = self._call_cache_only("9", "305", "208")
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.headers["X-CAM-Tile-Cache"], "HIT")
		self.assertEqual(response.mimetype, "image/png")
		self.assertEqual(response.get_data(), _PNG)

	def test_out_of_range_coordinate_returns_400_json(self):
		response = self._call_cache_only("9", "512", "0")
		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.mimetype, "application/json")
		self.assertEqual(json.loads(response.get_data(as_text=True))["error"], "invalid_tile")

	def test_permission_boundary_is_camera_read_not_place_read(self):
		frappe.set_user("tile-api-no-camera-access@example.invalid")
		with patch.object(frappe, "has_permission", return_value=False) as has_permission:
			with self.assertRaises(frappe.PermissionError):
				tiles.config()
		has_permission.assert_called_once_with("Camera", "read")

	def test_config_uses_enabled_siraj_catalog_and_attribution(self):
		cam_settings = SimpleNamespace(
			enable_online_tile_fetch=False,
			allow_tile_cache_write=False,
		)
		with (
			patch.object(tiles, "_siraj_module", return_value=_SirajCatalog),
			patch.object(tiles, "_siraj_settings", return_value=_SirajCatalog._settings()),
			patch.object(tiles, "_cam_settings", return_value=cam_settings),
		):
			result = tiles.config()
		self.assertEqual([layer["id"] for layer in result["layers"]], ["standard"])
		self.assertEqual(result["layers"][0]["attribution"], "Test provider attribution")
		self.assertEqual(result["layers"][0]["maxZoom"], 18)
		self.assertFalse(result["fetch_enabled"])
		self.assertFalse(result["browser_offline"])

	def test_failure_diagnostics_are_throttled(self):
		previous = dict(tiles._LAST_FAILURE_LOG)

		def restore_log_state():
			tiles._LAST_FAILURE_LOG.clear()
			tiles._LAST_FAILURE_LOG.update(previous)

		self.addCleanup(restore_log_state)
		tiles._LAST_FAILURE_LOG.clear()
		logger = Mock()
		with (
			patch.object(tiles.time, "monotonic", side_effect=(100.0, 101.0, 161.0)),
			patch.object(tiles.frappe, "logger", return_value=logger),
		):
			tiles._log_throttled("test-provider", 60, "warning", "simulated provider failure")
			tiles._log_throttled("test-provider", 60, "warning", "simulated provider failure")
			tiles._log_throttled("test-provider", 60, "warning", "simulated provider failure")
		self.assertEqual(logger.warning.call_count, 2)

	def test_upstream_failure_is_bounded_json_with_retry_after(self):
		cam_settings = SimpleNamespace(
			enable_online_tile_fetch=True,
			allow_tile_cache_write=True,
			tile_connect_timeout_seconds=1,
			tile_read_timeout_seconds=1,
		)
		with (
			patch.object(frappe, "get_site_path", return_value=str(self.private_path)),
			patch.object(tiles, "_siraj_module", return_value=_SirajCatalog),
			patch.object(tiles, "_siraj_settings", return_value=_SirajCatalog._settings()),
			patch.object(tiles, "_cam_settings", return_value=cam_settings),
			patch.object(tiles, "_breaker_open", return_value=False),
			patch.object(tiles, "_open_breaker"),
			patch.object(tiles, "_log_upstream_failure"),
			patch.object(
				tile_cache,
				"get_tile",
				side_effect=tile_cache.TileUpstreamUnavailable("simulated provider outage"),
			),
		):
			response = tiles.tile("standard", "base", "9", "305", "208")
		self.assertEqual(response.status_code, 503)
		self.assertEqual(response.headers["Retry-After"], str(tiles._BREAKER_SECONDS))
		self.assertEqual(response.mimetype, "application/json")
		self.assertEqual(json.loads(response.get_data(as_text=True))["error"], "tile_unavailable")
