"""Secure cache-first tile access to Siraj's configured raster providers.

This module deliberately does not define provider URLs. It consumes Siraj's
installed layer catalog and Geo Settings, writes only the compatible private
Siraj tile-cache layout, and keeps all cache data outside public assets.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

MAX_ZOOM = 19
MAX_TILE_BYTES = 2 * 1024 * 1024
SUPPORTED_VARIANTS = {
	"standard": frozenset({"base"}),
	"aerial": frozenset({"base"}),
	"hybrid": frozenset({"base", "overlay"}),
}
_CACHE_EXTENSIONS = {
	"standard": ("png",),
	"aerial": ("jpg", "jpeg", "png"),
	"hybrid": ("jpg", "jpeg", "png"),
}
_CANONICAL_INTEGER = re.compile(r"^[0-9]{1,6}$")
_UPSTREAM_SEMAPHORE = threading.BoundedSemaphore(4)


class TileCacheError(Exception):
	"""Base error with a safe HTTP status and public message."""

	status_code = 503
	public_message = "Map tile is temporarily unavailable."


class InvalidTile(TileCacheError):
	status_code = 400
	public_message = "Invalid tile coordinates or layer."


class DisabledTileLayer(TileCacheError):
	status_code = 403
	public_message = "This map layer is disabled by the site administrator."


class TileNotFound(TileCacheError):
	status_code = 404
	public_message = "This map tile is not available in the server cache."


class TileUpstreamUnavailable(TileCacheError):
	status_code = 503
	public_message = "No cached copy is available and the map provider is unavailable."


class InvalidUpstreamTile(TileCacheError):
	status_code = 502
	public_message = "The map provider returned an invalid raster tile."


class TileStorageError(TileCacheError):
	status_code = 500
	public_message = "The shared map-tile cache could not be accessed safely."


@dataclass(frozen=True)
class TileResult:
	data: bytes
	content_type: str
	source: str
	stale: bool = False
	write_failed: bool = False


def parse_xyz(z: object, x: object, y: object) -> tuple[int, int, int]:
	"""Parse canonical decimal XYZ arguments and enforce Web Mercator bounds."""
	values = []
	for value in (z, x, y):
		if isinstance(value, bool):
			raise InvalidTile()
		text = str(value)
		if not _CANONICAL_INTEGER.fullmatch(text):
			raise InvalidTile()
		values.append(int(text))
	zoom, tile_x, tile_y = values
	if zoom > MAX_ZOOM:
		raise InvalidTile()
	size = 1 << zoom
	if tile_x >= size or tile_y >= size:
		raise InvalidTile()
	return zoom, tile_x, tile_y


def validate_layer(layer: object, variant: object) -> tuple[str, str]:
	if not isinstance(layer, str) or not isinstance(variant, str):
		raise InvalidTile()
	if variant not in SUPPORTED_VARIANTS.get(layer, ()):
		raise InvalidTile()
	return layer, variant


def _mime_from_bytes(data: bytes, extension: str) -> str:
	if not data or len(data) > MAX_TILE_BYTES:
		raise TileStorageError("Empty or oversized cached tile")
	if extension == "png" and data.startswith(b"\x89PNG\r\n\x1a\n"):
		return "image/png"
	if extension in {"jpg", "jpeg"} and data.startswith(b"\xff\xd8\xff"):
		return "image/jpeg"
	raise TileStorageError("Cached tile signature does not match its extension")


def _private_root(private_path: str | Path) -> Path:
	try:
		private = Path(private_path).resolve(strict=True)
		if not private.is_dir():
			raise TileStorageError("Frappe private path is not a directory")
		return private
	except TileStorageError:
		raise
	except (OSError, RuntimeError) as exc:
		raise TileStorageError("Frappe private path is unavailable") from exc


def _cache_root(private_path: str | Path, *, create: bool = False) -> Path | None:
	private = _private_root(private_path)
	candidate = private / "siraj_tile_cache"
	try:
		if candidate.is_symlink():
			raise TileStorageError("Shared tile-cache root must not be a symlink")
		if not candidate.exists():
			if not create:
				return None
			candidate.mkdir(mode=0o700, exist_ok=True)
		if candidate.is_symlink():
			raise TileStorageError("Shared tile-cache root must not be a symlink")
		root = candidate.resolve(strict=True)
		root.relative_to(private)
		if not root.is_dir():
			raise TileStorageError("Shared tile-cache root is not a directory")
		return root
	except TileStorageError:
		raise
	except (OSError, ValueError, RuntimeError) as exc:
		raise TileStorageError("Shared tile-cache root is not safely contained") from exc


def _cache_relative_paths(layer: str, variant: str, z: int, x: int, y: int):
	# Canonical Siraj content wins when both layouts contain the same XYZ tile.
	cache_variants = ("_", "base") if variant == "base" else ("overlay",)
	for cache_variant in cache_variants:
		for extension in _CACHE_EXTENSIONS[layer]:
			yield Path(layer, cache_variant, str(z), str(x), f"{y}.{extension}"), extension


def _safe_file(root: Path, relative_path: Path) -> Path:
	candidate = root / relative_path
	try:
		for component in (candidate, *candidate.parents):
			if component == root:
				break
			if component.is_symlink():
				raise TileStorageError("Symlinks are not allowed in the shared tile cache")
		resolved = candidate.resolve(strict=False)
		resolved.relative_to(root)
		return resolved
	except TileStorageError:
		raise
	except (OSError, ValueError, RuntimeError) as exc:
		raise TileStorageError("Tile path escapes the shared cache root") from exc


def read_cached_tile(
	private_path: str | Path, layer: str, variant: str, z: int, x: int, y: int
) -> TileResult | None:
	root = _cache_root(private_path)
	if root is None:
		return None
	for relative_path, extension in _cache_relative_paths(layer, variant, z, x, y):
		path = _safe_file(root, relative_path)
		try:
			fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
		except FileNotFoundError:
			continue
		except OSError as exc:
			raise TileStorageError("Cached tile could not be opened safely") from exc
		with os.fdopen(fd, "rb") as stream:
			data = stream.read(MAX_TILE_BYTES + 1)
		if len(data) > MAX_TILE_BYTES:
			raise TileStorageError("Cached tile exceeds the configured byte limit")
		content_type = _mime_from_bytes(data, extension)
		return TileResult(data=data, content_type=content_type, source="hit")
	return None


def _ensure_directory(root: Path, relative_dir: Path) -> Path:
	current = root
	for part in relative_dir.parts:
		current = current / part
		if current.is_symlink():
			raise TileStorageError("Symlinks are not allowed in the shared tile cache")
		try:
			current.mkdir(mode=0o700, exist_ok=True)
		except OSError as exc:
			raise TileStorageError("Cache directory could not be created") from exc
		if current.is_symlink():
			raise TileStorageError("Cache directory changed to a symlink")
		try:
			current.resolve(strict=True).relative_to(root)
		except (OSError, ValueError, RuntimeError) as exc:
			raise TileStorageError("Cache directory is not safely contained") from exc
	return current


def write_cached_tile(
	private_path: str | Path,
	layer: str,
	variant: str,
	z: int,
	x: int,
	y: int,
	extension: str,
	data: bytes,
) -> None:
	if extension not in _CACHE_EXTENSIONS[layer]:
		raise TileStorageError("Unsupported tile file extension")
	_mime_from_bytes(data, extension)
	root = _cache_root(private_path, create=True)
	assert root is not None
	# Siraj canonicalizes its public `base` variant to `_` on disk.
	relative = Path(layer, "_" if variant == "base" else "overlay", str(z), str(x))
	directory = _ensure_directory(root, relative)
	target = _safe_file(root, relative / f"{y}.{extension}")
	temporary_path = None
	try:
		fd, name = tempfile.mkstemp(prefix=f".{y}.", suffix=".tmp", dir=directory)
		temporary_path = Path(name)
		os.fchmod(fd, 0o600)
		with os.fdopen(fd, "wb") as stream:
			stream.write(data)
			stream.flush()
			os.fsync(stream.fileno())
		os.replace(temporary_path, target)
		try:
			dir_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
			try:
				os.fsync(dir_fd)
			finally:
				os.close(dir_fd)
		except OSError:
			# The file replacement is already atomic; some filesystems do not
			# support fsync on directories.
			pass
	except TileStorageError:
		raise
	except OSError as exc:
		raise TileStorageError("Atomic tile-cache write failed") from exc
	finally:
		if temporary_path is not None:
			try:
				temporary_path.unlink(missing_ok=True)
			except OSError:
				pass


def _lock_directory(private_path: str | Path) -> Path:
	private = _private_root(private_path)
	app_root = private / "camera_archive_management"
	if app_root.is_symlink():
		raise TileStorageError("Camera Archive private cache must not be a symlink")
	try:
		app_root.mkdir(mode=0o700, exist_ok=True)
		app_root.resolve(strict=True).relative_to(private)
		lock_dir = app_root / "tile-locks"
		if lock_dir.is_symlink():
			raise TileStorageError("Tile lock directory must not be a symlink")
		lock_dir.mkdir(mode=0o700, exist_ok=True)
		lock_dir.resolve(strict=True).relative_to(private)
		return lock_dir
	except TileStorageError:
		raise
	except (OSError, ValueError, RuntimeError) as exc:
		raise TileStorageError("Tile lock directory is not safely contained") from exc


def tile_lock(private_path: str | Path, layer: str, variant: str, z: int, x: int, y: int, timeout: float = 2.0):
	"""Cross-process advisory lock keyed by one tile; returns False on timeout."""
	import fcntl

	lock_dir = _lock_directory(private_path)
	key = hashlib.sha256(f"{layer}/{variant}/{z}/{x}/{y}".encode()).hexdigest()
	# A fixed shard set prevents one lock file from accumulating per viewed tile.
	# Hash collisions only serialize unrelated tile misses; they never mix data.
	path = lock_dir / f"{key[:3]}.lock"
	fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
	deadline = time.monotonic() + timeout
	try:
		while True:
			try:
				fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
				return _TileLock(fd)
			except BlockingIOError:
				if time.monotonic() >= deadline:
					os.close(fd)
					return False
				time.sleep(0.05)
	except Exception:
		os.close(fd)
		raise


class _TileLock:
	def __init__(self, fd: int):
		self.fd = fd

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		import fcntl

		try:
			fcntl.flock(self.fd, fcntl.LOCK_UN)
		finally:
			os.close(self.fd)


def _source_url(tile_module, spec: dict, settings, variant: str, z: int, x: int, y: int) -> str:
	try:
		url = tile_module._resolve_url(spec, settings, variant, z)
		u = url.replace("{x}", str(x)).replace("{y}", str(y))
		p = urlsplit(u)
		base = spec["overlay_url"] if variant == "overlay" else spec["url"]
		origin = urlsplit(base)
		if (
			p.scheme != "https"
			or p.hostname != origin.hostname
			or p.port not in (None, 443)
			or p.username is not None
			or p.password is not None
		):
			raise TileUpstreamUnavailable("Configured provider URL is not an approved HTTPS origin")
		return u
	except TileCacheError:
		raise
	except Exception as exc:
		raise TileUpstreamUnavailable("Siraj tile provider configuration is invalid") from exc


def _fetch_image(
	url: str, user_agent: str, expected_type: str, connect_timeout: float, read_timeout: float
) -> tuple[bytes, str]:
	try:
		import requests
	except ImportError as exc:
		raise TileUpstreamUnavailable("HTTP client is unavailable") from exc

	try:
		with requests.get(
			url,
			headers={"User-Agent": user_agent, "Accept": expected_type},
			timeout=(connect_timeout, read_timeout),
			stream=True,
			allow_redirects=False,
		) as response:
			if response.status_code == 404:
				raise TileNotFound("Provider has no tile at these coordinates")
			if response.status_code != 200:
				raise TileUpstreamUnavailable(f"Provider returned HTTP {response.status_code}")
			actual_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
			if actual_type != expected_type.lower():
				raise InvalidUpstreamTile("Provider response is not the configured raster image type")
			chunks, size = [], 0
			for chunk in response.iter_content(chunk_size=64 * 1024):
				if not chunk:
					continue
				size += len(chunk)
				if size > MAX_TILE_BYTES:
					raise InvalidUpstreamTile("Provider tile exceeds the maximum byte limit")
				chunks.append(chunk)
		data = b"".join(chunks)
		extension = "png" if actual_type == "image/png" else "jpg"
		try:
			_mime_from_bytes(data, extension)
		except TileStorageError as exc:
			raise InvalidUpstreamTile("Provider body is not a valid tile image") from exc
		return data, actual_type
	except TileCacheError:
		raise
	except requests.RequestException as exc:
		raise TileUpstreamUnavailable("Tile provider request failed or timed out") from exc


def _cache_status(private_path: str | Path, layer: str, variant: str, z: int, x: int, y: int, cache_days: int):
	result = read_cached_tile(private_path, layer, variant, z, x, y)
	if result is None:
		return None
	root = _cache_root(private_path)
	assert root is not None
	age_seconds = None
	for relative_path, _extension in _cache_relative_paths(layer, variant, z, x, y):
		path = _safe_file(root, relative_path)
		try:
			age_seconds = max(0.0, time.time() - path.stat().st_mtime)
			break
		except FileNotFoundError:
			continue
		except OSError as exc:
			raise TileStorageError("Cached tile age could not be checked") from exc
	is_stale = age_seconds is not None and age_seconds > max(1, cache_days) * 86400
	return TileResult(result.data, result.content_type, "stale" if is_stale else "hit", stale=is_stale)


def get_tile(
	*,
	private_path: str | Path,
	layer: str,
	variant: str,
	z: int,
	x: int,
	y: int,
	tile_module,
	siraj_settings,
	allow_online_fetch: bool,
	allow_cache_write: bool,
	connect_timeout: float = 1.5,
	read_timeout: float = 2.5,
	breaker_open: bool = False,
	force_refresh: bool = False,
) -> TileResult:
	"""Serve cache-first; a miss may fetch only under both explicit opt-ins."""
	validate_layer(layer, variant)
	spec = tile_module.LAYERS[layer]
	if not spec.get("min_zoom", 0) <= z <= spec.get("max_zoom", MAX_ZOOM):
		raise TileNotFound("Layer has no coverage at this zoom")

	cache_days = max(1, min(3650, int(getattr(siraj_settings, "cache_days", 90) or 90)))
	connect_timeout = min(5.0, max(0.25, float(connect_timeout)))
	read_timeout = min(5.0, max(0.25, float(read_timeout)))
	cached = _cache_status(private_path, layer, variant, z, x, y, cache_days)
	if cached is not None and (not force_refresh or not cached.stale):
		return cached
	if not allow_online_fetch or not allow_cache_write or not _strict_true(getattr(siraj_settings, "allow_fetch", False)):
		raise TileNotFound()
	if breaker_open:
		raise TileUpstreamUnavailable()

	lock = tile_lock(private_path, layer, variant, z, x, y)
	if not lock:
		cached = _cache_status(private_path, layer, variant, z, x, y, cache_days)
		if cached is not None:
			return cached
		raise TileUpstreamUnavailable("Another request is retrieving this tile; retry shortly")
	with lock:
		cached = _cache_status(private_path, layer, variant, z, x, y, cache_days)
		if cached is not None and (not force_refresh or not cached.stale):
			return cached
		variant_name = "overlay" if variant == "overlay" else "base"
		if not _UPSTREAM_SEMAPHORE.acquire(timeout=1.0):
			raise TileUpstreamUnavailable("Tile provider request concurrency limit reached")
		try:
			url = _source_url(tile_module, spec, siraj_settings, variant_name, z, x, y)
			data, content_type = _fetch_image(
				url, spec["user_agent"], spec["content_type"], connect_timeout, read_timeout
			)
		finally:
			_UPSTREAM_SEMAPHORE.release()
		extension = "png" if content_type == "image/png" else "jpg"
		try:
			write_cached_tile(private_path, layer, variant, z, x, y, extension, data)
		except TileStorageError:
			return TileResult(data, content_type, "miss", write_failed=True)
		return TileResult(data, content_type, "miss")


def _strict_true(value: object) -> bool:
	return value is True or value == 1 or value == "1"


def provider_host(tile_module, layer: str, variant: str) -> str:
	spec = tile_module.LAYERS[layer]
	url = spec["overlay_url"] if variant == "overlay" else spec["url"]
	return urlsplit(url).hostname or "unknown"
