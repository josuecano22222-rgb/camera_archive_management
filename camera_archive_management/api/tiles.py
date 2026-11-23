"""Authenticated, cache-first proxy for the Siraj Research tile catalog."""

from __future__ import annotations

import hashlib
import importlib
import json
import threading
import time

import frappe
from frappe.rate_limiter import rate_limit
from werkzeug.wrappers import Response

from camera_archive_management.geo import tile_cache

_SUPPORTED_LAYERS = ("standard", "aerial", "hybrid")
_LOG_LOCK = threading.Lock()
_LAST_FAILURE_LOG: dict[str, float] = {}
_BREAKER_SECONDS = 20
_REFRESH_COOLDOWN_SECONDS = 60


def _json_response(status: int, code: str, message: str, *, headers: dict | None = None) -> Response:
	response = Response(
		json.dumps({"error": code, "message": message}, separators=(",", ":")),
		status=status,
		content_type="application/json; charset=utf-8",
	)
	response.headers["Cache-Control"] = "no-store"
	response.headers["X-Content-Type-Options"] = "nosniff"
	if status == 503:
		response.headers["Retry-After"] = str(_BREAKER_SECONDS)
	for key, value in (headers or {}).items():
		response.headers[key] = value
	return response


def _authorize() -> None:
	if frappe.session.user == "Guest" or not frappe.has_permission("Camera", "read"):
		frappe.throw("Sign in with Camera read permission to access map tiles.", frappe.PermissionError)


def _siraj_module():
	try:
		return importlib.import_module("siraj_research.tile_cache")
	except ModuleNotFoundError as exc:
		if exc.name == "siraj_research" or exc.name == "siraj_research.tile_cache":
			return None
		raise


def _log_throttled(key: str, interval: float, level: str, message: str, *args) -> None:
	now = time.monotonic()
	with _LOG_LOCK:
		if now - _LAST_FAILURE_LOG.get(key, 0) < interval:
			return
		_LAST_FAILURE_LOG[key] = now
	getattr(frappe.logger("camera_archive_management.tiles"), level)(message, *args)


def _siraj_settings(tile_module):
	try:
		return tile_module._settings()
	except Exception as exc:
		_log_throttled(
			"siraj-settings-unavailable", 60, "warning",
			"Siraj tile settings unavailable; external tile fetch is disabled (%s)", type(exc).__name__
		)
		return None


def _cam_settings():
	try:
		return frappe.get_single("CAM Geo Settings")
	except Exception as exc:
		_log_throttled(
			"cam-settings-unavailable", 60, "warning",
			"CAM Geo Settings unavailable; external tile fetch is disabled (%s)", type(exc).__name__
		)
		return None


def _enabled_by_siraj(tile_module, siraj_settings, layer: str) -> bool:
	if not tile_module or siraj_settings is None:
		return True
	flag_name = tile_module._ENABLE_FLAG.get(layer)
	if not flag_name:
		return False
	return tile_cache._strict_true(getattr(siraj_settings, flag_name, False))


def _online_allowed(cam_settings) -> bool:
	if cam_settings is None or not tile_cache._strict_true(
		getattr(cam_settings, "enable_online_tile_fetch", False)
	):
		return False
	# This site-wide switch is an emergency deny-only override. The CAM setting
	# remains the explicit per-site opt-in; site_config can never turn it on.
	site_override = frappe.conf.get("camera_archive_allow_online_tile_fetch")
	if site_override is not None and not tile_cache._strict_true(site_override):
		return False
	return True


def _breaker_key(host: str) -> str:
	return f"cam_tile_upstream_breaker:{host}"


def _breaker_open(host: str) -> bool:
	try:
		return bool(frappe.cache().get_value(_breaker_key(host), shared=True))
	except Exception:
		return False


def _open_breaker(host: str) -> None:
	try:
		frappe.cache().set_value(_breaker_key(host), 1, expires_in_sec=_BREAKER_SECONDS, shared=True)
	except Exception:
		# Cache outage must not prevent serving a valid tile or returning a
		# bounded upstream failure; the explicit HTTP timeout remains in force.
		pass


def _log_upstream_failure(host: str, layer: str, variant: str, z: int, x: int, y: int, error: Exception) -> None:
	_log_throttled(
		f"upstream:{host}:{layer}:{variant}",
		30,
		"warning",
		"tile upstream unavailable host=%s layer=%s variant=%s z=%s x=%s y=%s error=%s",
		host,
		layer,
		variant,
		z,
		x,
		y,
		type(error).__name__,
	)


def _tile_response(result: tile_cache.TileResult) -> Response:
	response = Response(result.data, content_type=result.content_type)
	response.headers["Cache-Control"] = "private, max-age=3600"
	response.headers["X-Content-Type-Options"] = "nosniff"
	response.headers["X-CAM-Tile-Cache"] = result.source.upper()
	if result.write_failed:
		response.headers["X-CAM-Tile-Write"] = "FAILED"
	return response


def _enqueue_stale_refresh(layer: str, variant: str, z: int, x: int, y: int, host: str) -> None:
	if _breaker_open(host):
		return
	key = hashlib.sha256(f"{layer}/{variant}/{z}/{x}/{y}".encode()).hexdigest()
	cooldown_key = f"cam_tile_refresh_cooldown:{key}"
	try:
		cache = frappe.cache()
		if cache.get_value(cooldown_key, shared=True):
			return
		cache.set_value(cooldown_key, 1, expires_in_sec=_REFRESH_COOLDOWN_SECONDS, shared=True)
		frappe.enqueue(
			"camera_archive_management.api.tiles.refresh_stale_tile",
			queue="short",
			timeout=15,
			job_id=f"cam-tile-refresh-{key}",
			deduplicate=True,
			layer=layer,
			variant=variant,
			z=z,
			x=x,
			y=y,
		)
	except Exception as exc:
		frappe.logger("camera_archive_management.tiles").warning(
			"stale tile refresh was not queued layer=%s z=%s x=%s y=%s error=%s",
			layer,
			z,
			x,
			y,
			type(exc).__name__,
		)


def _timeouts(cam_settings) -> tuple[float, float]:
	connect = getattr(cam_settings, "tile_connect_timeout_seconds", 2) if cam_settings else 2
	read = getattr(cam_settings, "tile_read_timeout_seconds", 3) if cam_settings else 3
	try:
		return min(5.0, max(1.0, float(connect))), min(5.0, max(1.0, float(read)))
	except (TypeError, ValueError):
		return 2.0, 3.0


def _cache_only(private_path, layer: str, variant: str, z: int, x: int, y: int):
	try:
		return tile_cache.read_cached_tile(private_path, layer, variant, z, x, y)
	except tile_cache.TileCacheError as exc:
		_log_throttled(
			f"invalid-cache:{layer}:{variant}",
			60,
			"error",
			"unsafe or invalid tile cache entry layer=%s variant=%s z=%s x=%s y=%s error=%s",
			layer,
			variant,
			z,
			x,
			y,
			type(exc).__name__,
		)
		return exc


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=1200, seconds=60)
def tile(layer: str, variant: str, z, x, y):
	"""Serve a Siraj cache tile or fetch an enabled provider tile on a cache miss."""
	_authorize()
	try:
		layer, variant = tile_cache.validate_layer(layer, variant)
		z, x, y = tile_cache.parse_xyz(z, x, y)
	except tile_cache.InvalidTile as exc:
		return _json_response(400, "invalid_tile", str(exc) or exc.public_message)

	private_path = frappe.get_site_path("private")
	tile_module = _siraj_module()
	siraj_settings = _siraj_settings(tile_module) if tile_module else None
	if not _enabled_by_siraj(tile_module, siraj_settings, layer):
		return _json_response(403, "layer_disabled", tile_cache.DisabledTileLayer.public_message)
	if tile_module is None or siraj_settings is None:
		cached = _cache_only(private_path, layer, variant, z, x, y)
		if isinstance(cached, tile_cache.TileCacheError):
			return _json_response(cached.status_code, "cache_invalid", cached.public_message)
		if cached is None:
			return _json_response(404, "tile_missing", tile_cache.TileNotFound.public_message)
		return _tile_response(cached)

	cam_settings = _cam_settings()
	allow_fetch = _online_allowed(cam_settings)
	allow_write = bool(cam_settings and tile_cache._strict_true(getattr(cam_settings, "allow_tile_cache_write", False)))
	connect_timeout, read_timeout = _timeouts(cam_settings)
	try:
		host = tile_cache.provider_host(tile_module, layer, variant)
		breaker_open = _breaker_open(host)
		result = tile_cache.get_tile(
			private_path=private_path,
			layer=layer,
			variant=variant,
			z=z,
			x=x,
			y=y,
			tile_module=tile_module,
			siraj_settings=siraj_settings,
			allow_online_fetch=allow_fetch,
			allow_cache_write=allow_write,
			connect_timeout=connect_timeout,
			read_timeout=read_timeout,
			breaker_open=breaker_open,
		)
		if result.write_failed:
			_log_throttled(
				f"write-failed:{layer}:{variant}",
				60,
				"warning",
				"valid tile served but shared-cache write failed layer=%s variant=%s z=%s x=%s y=%s",
				layer,
				variant,
				z,
				x,
				y,
			)
		if result.stale and allow_fetch and allow_write and tile_cache._strict_true(
			getattr(siraj_settings, "allow_fetch", False)
		):
			_enqueue_stale_refresh(layer, variant, z, x, y, host)
		return _tile_response(result)
	except tile_cache.TileCacheError as exc:
		if isinstance(exc, (tile_cache.TileUpstreamUnavailable, tile_cache.InvalidUpstreamTile)):
			_open_breaker(host)
			_log_upstream_failure(host, layer, variant, z, x, y, exc)
		return _json_response(exc.status_code, "tile_unavailable", exc.public_message)
	except Exception as exc:
		_log_throttled(
			f"handler-failure:{layer}:{variant}",
			30,
			"error",
			"tile handler failed layer=%s variant=%s z=%s x=%s y=%s error=%s",
			layer,
			variant,
			z,
			x,
			y,
			type(exc).__name__,
		)
		return _json_response(503, "tile_service_unavailable", tile_cache.TileUpstreamUnavailable.public_message)


def refresh_stale_tile(layer: str, variant: str, z: int, x: int, y: int) -> None:
	"""Bounded background stale-while-revalidate job; never a web endpoint."""
	try:
		layer, variant = tile_cache.validate_layer(layer, variant)
		z, x, y = tile_cache.parse_xyz(z, x, y)
		tile_module = _siraj_module()
		if tile_module is None:
			return
		siraj_settings = _siraj_settings(tile_module)
		cam_settings = _cam_settings()
		if not _online_allowed(cam_settings) or not (
			cam_settings and tile_cache._strict_true(getattr(cam_settings, "allow_tile_cache_write", False))
		):
			return
		if not _enabled_by_siraj(tile_module, siraj_settings, layer):
			return
		host = tile_cache.provider_host(tile_module, layer, variant)
		if _breaker_open(host):
			return
		connect_timeout, read_timeout = _timeouts(cam_settings)
		tile_cache.get_tile(
			private_path=frappe.get_site_path("private"),
			layer=layer,
			variant=variant,
			z=z,
			x=x,
			y=y,
			tile_module=tile_module,
			siraj_settings=siraj_settings,
			allow_online_fetch=True,
			allow_cache_write=True,
			connect_timeout=connect_timeout,
			read_timeout=read_timeout,
			breaker_open=False,
			force_refresh=True,
		)
	except (tile_cache.TileUpstreamUnavailable, tile_cache.InvalidUpstreamTile) as exc:
		try:
			_open_breaker(tile_cache.provider_host(tile_module, layer, variant))
		except Exception:
			pass
		_log_upstream_failure("background", layer, variant, z, x, y, exc)
	except Exception as exc:
		frappe.logger("camera_archive_management.tiles").warning(
			"background stale tile refresh failed layer=%s variant=%s z=%s x=%s y=%s error=%s",
			layer,
			variant,
			z,
			x,
			y,
			type(exc).__name__,
		)


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=60, seconds=60)
def config():
	"""Expose only enabled Siraj raster layers, with attribution and cache mode."""
	_authorize()
	tile_module = _siraj_module()
	siraj_settings = _siraj_settings(tile_module) if tile_module else None
	layers = []
	if tile_module and siraj_settings:
		for layer in _SUPPORTED_LAYERS:
			if not _enabled_by_siraj(tile_module, siraj_settings, layer):
				continue
			spec = tile_module.LAYERS[layer]
			layers.append(
				{
					"id": layer,
					"label": spec["label"],
					"attribution": spec["attribution"],
					"minZoom": int(spec.get("min_zoom", 0)),
					"maxZoom": min(19, int(spec.get("max_zoom", 19))),
					"overlay": layer == "hybrid" and "overlay_url" in spec,
				}
			)
	cam_settings = _cam_settings()
	return {
		"layers": layers,
		"fetch_enabled": bool(
			tile_module
			and siraj_settings
			and _online_allowed(cam_settings)
			and cam_settings
			and tile_cache._strict_true(getattr(cam_settings, "allow_tile_cache_write", False))
			and tile_cache._strict_true(getattr(siraj_settings, "allow_fetch", False))
		),
		"server_cache": True,
		"browser_offline": False,
	}
