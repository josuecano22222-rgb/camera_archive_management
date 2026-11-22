from __future__ import annotations

import multiprocessing
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from camera_archive_management.geo import tile_cache

PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic-png-payload"
JPEG = b"\xff\xd8\xff" + b"synthetic-jpeg-payload"


class FakeRequestException(Exception):
	"""Stand-in for requests.RequestException in isolated fetch tests."""


class FakeResponse:
	def __init__(self, data=PNG, status=200, content_type="image/png"):
		self.data = data
		self.status_code = status
		self.headers = {"Content-Type": content_type}

	def __enter__(self):
		return self

	def __exit__(self, *_args):
		return None

	def iter_content(self, chunk_size=0):
		yield self.data


def _try_acquire_tile_lock(private_path, result_queue):
	lock = tile_cache.tile_lock(private_path, "standard", "base", 5, 13, 8, timeout=0.2)
	result_queue.put(lock is not False)
	if lock:
		lock.__exit__(None, None, None)


class FakeSirajTileModule:
	LAYERS = {
		"standard": {
			"url": "https://tile.example.test/{z}/{x}/{y}.png",
			"content_type": "image/png",
			"ext": "png",
			"user_agent": "Siraj-Test/1.0",
			"min_zoom": 0,
			"max_zoom": 19,
		}
	}

	@staticmethod
	def _resolve_url(spec, _settings, _variant, z):
		return spec["url"].replace("{z}", str(z))


class TestTileCache(unittest.TestCase):
	def setUp(self):
		self.temp = tempfile.TemporaryDirectory()
		self.private = Path(self.temp.name) / "private"
		self.private.mkdir()
		self.settings = SimpleNamespace(allow_fetch=True, cache_days=90)

	def tearDown(self):
		self.temp.cleanup()

	def get_tile(self, **overrides):
		args = {
			"private_path": self.private,
			"layer": "standard",
			"variant": "base",
			"z": 9,
			"x": 305,
			"y": 208,
			"tile_module": FakeSirajTileModule,
			"siraj_settings": self.settings,
			"allow_online_fetch": True,
			"allow_cache_write": True,
			"connect_timeout": 1,
			"read_timeout": 2,
		}
		args.update(overrides)
		return tile_cache.get_tile(**args)

	def requests_stub(self, *, side_effect=None, return_value=None):
		return SimpleNamespace(
			get=Mock(side_effect=side_effect, return_value=return_value),
			RequestException=FakeRequestException,
		)

	def test_xyz_bounds_accept_tiles_over_two_digits(self):
		self.assertEqual(tile_cache.parse_xyz("9", "305", "208"), (9, 305, 208))
		self.assertEqual(tile_cache.parse_xyz("10", "607", "418"), (10, 607, 418))
		self.assertEqual(tile_cache.parse_xyz("19", "524287", "524287"), (19, 524287, 524287))
		self.assertEqual(tile_cache.parse_xyz("0", "0", "0"), (0, 0, 0))

	def test_xyz_rejects_malformed_and_out_of_bounds(self):
		for values in (("20", "0", "0"), ("5", "32", "0"), ("5", "0", "-1"), ("5", "1.0", "2"), (True, "0", "0")):
			with self.subTest(values=values), self.assertRaises(tile_cache.InvalidTile):
				tile_cache.parse_xyz(*values)
		with self.assertRaises(tile_cache.InvalidTile):
			tile_cache.validate_layer("hybrid", "labels")

	def test_miss_fetches_valid_image_atomically_then_serves_cache(self):
		requests = self.requests_stub(return_value=FakeResponse())
		with patch.dict(sys.modules, {"requests": requests}):
			result = self.get_tile()
			self.assertEqual(result.source, "miss")
			self.assertEqual(result.content_type, "image/png")
			path = self.private / "siraj_tile_cache/standard/_/9/305/208.png"
			self.assertEqual(path.read_bytes(), PNG)
			self.assertEqual(list(path.parent.glob("*.tmp")), [])
			requests.get.side_effect = AssertionError("cache hit must not access the provider")
			cached = self.get_tile(allow_online_fetch=False, allow_cache_write=False)
		self.assertEqual(cached.data, PNG)
		self.assertIn(cached.source, {"hit", "stale"})

	def test_external_fetch_requires_both_explicit_flags(self):
		requests = self.requests_stub(return_value=FakeResponse())
		with patch.dict(sys.modules, {"requests": requests}):
			with self.assertRaises(tile_cache.TileNotFound):
				self.get_tile(allow_online_fetch=False)
			with self.assertRaises(tile_cache.TileNotFound):
				self.get_tile(allow_cache_write=False)
		requests.get.assert_not_called()

	def test_non_image_upstream_is_rejected_and_never_cached(self):
		requests = self.requests_stub(return_value=FakeResponse(data=b"not an image", content_type="text/html"))
		with patch.dict(sys.modules, {"requests": requests}):
			with self.assertRaises(tile_cache.InvalidUpstreamTile):
				self.get_tile()
		self.assertFalse((self.private / "siraj_tile_cache/standard/_/9/305/208.png").exists())

	def test_valid_upstream_tile_is_served_with_explicit_write_failure(self):
		requests = self.requests_stub(return_value=FakeResponse())
		with patch.dict(sys.modules, {"requests": requests}), patch.object(
			tile_cache, "write_cached_tile", side_effect=tile_cache.TileStorageError("disk full")
		):
			result = self.get_tile()
		self.assertEqual(result.data, PNG)
		self.assertTrue(result.write_failed)

	def test_oversized_upstream_body_is_rejected(self):
		requests = self.requests_stub(return_value=FakeResponse(data=PNG + b"x" * tile_cache.MAX_TILE_BYTES))
		with patch.dict(sys.modules, {"requests": requests}):
			with self.assertRaises(tile_cache.InvalidUpstreamTile):
				self.get_tile()

	def test_timeout_failure_is_bounded_error_not_empty_image(self):
		requests = self.requests_stub(side_effect=FakeRequestException("simulated timeout"))
		with patch.dict(sys.modules, {"requests": requests}):
			with self.assertRaises(tile_cache.TileUpstreamUnavailable):
				self.get_tile()
		self.assertFalse((self.private / "siraj_tile_cache/standard/_/9/305/208.png").exists())

	def test_parallel_misses_deduplicate_to_one_provider_request(self):
		def delayed_response(*_args, **_kwargs):
			time.sleep(0.08)
			return FakeResponse()

		requests = self.requests_stub(side_effect=delayed_response)
		with patch.dict(sys.modules, {"requests": requests}):
			with ThreadPoolExecutor(max_workers=6) as pool:
				results = list(pool.map(lambda _n: self.get_tile(), range(6)))
		self.assertEqual(requests.get.call_count, 1)
		self.assertEqual(sum(result.source == "miss" for result in results), 1)
		self.assertTrue(all(result.data == PNG for result in results))

	def test_tile_miss_lock_is_shared_across_processes(self):
		lock = tile_cache.tile_lock(self.private, "standard", "base", 5, 13, 8, timeout=1)
		self.assertTrue(lock)
		context = multiprocessing.get_context("fork")
		result_queue = context.Queue()
		process = context.Process(target=_try_acquire_tile_lock, args=(str(self.private), result_queue))
		try:
			process.start()
			self.assertFalse(result_queue.get(timeout=3))
			process.join(timeout=3)
			self.assertEqual(process.exitcode, 0)
		finally:
			if process.is_alive():
				process.terminate()
				process.join(timeout=3)
			lock.__exit__(None, None, None)
			result_queue.close()

	def test_symlinked_cache_root_is_rejected(self):
		outside = Path(self.temp.name) / "outside"
		outside.mkdir()
		(self.private / "siraj_tile_cache").symlink_to(outside, target_is_directory=True)
		with self.assertRaises(tile_cache.TileStorageError):
			tile_cache.read_cached_tile(self.private, "standard", "base", 5, 17, 8)

	def test_jpeg_magic_and_shared_hybrid_overlay_layout(self):
		path = self.private / "siraj_tile_cache/hybrid/overlay/9/305/208.jpg"
		tile_cache.write_cached_tile(self.private, "hybrid", "overlay", 9, 305, 208, "jpg", JPEG)
		result = tile_cache.read_cached_tile(self.private, "hybrid", "overlay", 9, 305, 208)
		self.assertEqual(path.read_bytes(), JPEG)
		self.assertEqual(result.content_type, "image/jpeg")

	def test_legacy_explicit_base_directory_is_readable(self):
		path = self.private / "siraj_tile_cache/standard/base/5/13/8.png"
		path.parent.mkdir(parents=True)
		path.write_bytes(PNG)
		result = tile_cache.read_cached_tile(self.private, "standard", "base", 5, 13, 8)
		self.assertEqual(result.data, PNG)
		self.assertEqual(result.source, "hit")

	def test_canonical_siraj_base_wins_over_legacy_duplicate(self):
		legacy = self.private / "siraj_tile_cache/standard/base/5/13/8.png"
		canonical = self.private / "siraj_tile_cache/standard/_/5/13/8.png"
		legacy.parent.mkdir(parents=True)
		canonical.parent.mkdir(parents=True)
		legacy.write_bytes(PNG + b"legacy")
		canonical.write_bytes(PNG + b"canonical")
		result = tile_cache.read_cached_tile(self.private, "standard", "base", 5, 13, 8)
		self.assertEqual(result.data, PNG + b"canonical")


if __name__ == "__main__":
	unittest.main()
