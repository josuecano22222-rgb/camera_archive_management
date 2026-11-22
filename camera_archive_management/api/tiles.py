"""Read-only, allow-listed access to the shared Siraj raster tile cache."""

from __future__ import annotations

import re
from pathlib import Path

import frappe
from werkzeug.wrappers import Response

_ROOT_NAME = "siraj_tile_cache"
_MAX_TILE_BYTES = 4 * 1024 * 1024
_COORDINATE = re.compile(r"^(?:0|[1-9][0-9]?)$")
_ALLOWED = {
	("standard", "base"): ("png",),
	("aerial", "base"): ("png", "jpg", "jpeg"),
	("hybrid", "base"): ("png", "jpg", "jpeg"),
	("hybrid", "overlay"): ("png", "jpg", "jpeg"),
}


def _tile_coordinate(value, label: str) -> int:
	text = str(value)
	if not _COORDINATE.fullmatch(text):
		frappe.throw(f"Invalid tile {label} coordinate.", frappe.ValidationError)
	return int(text)


def _tile_path(layer: str, variant: str, z: int, x: int, y: int) -> tuple[Path, str] | None:
	if (layer, variant) not in _ALLOWED:
		frappe.throw("Unsupported shared tile layer.", frappe.ValidationError)
	try:
		private_root = Path(frappe.get_site_path("private")).resolve(strict=True)
		root = (private_root / _ROOT_NAME).resolve(strict=True)
		root.relative_to(private_root)
	except (FileNotFoundError, OSError, ValueError):
		frappe.throw("Shared Siraj tile cache is not available inside private storage.", frappe.DoesNotExistError)
	if not root.is_dir():
		frappe.throw("Shared Siraj tile cache is not available inside private storage.", frappe.DoesNotExistError)
	# Siraj's cache uses `_` as the base-layer directory; also accept the
	# explicit `base` layout requested by this app's API contract. Never scan
	# beyond these two fixed cache layouts.
	cache_variants = ("base", "_") if variant == "base" else ("overlay",)
	for cache_variant in cache_variants:
		for extension in _ALLOWED[(layer, variant)]:
			candidate = root / layer / cache_variant / str(z) / str(x) / f"{y}.{extension}"
			if any(component.is_symlink() for component in (candidate, *candidate.parents) if component == root or root in component.parents):
				continue
			try:
				resolved = candidate.resolve(strict=True)
				resolved.relative_to(root)
			except (FileNotFoundError, OSError, ValueError):
				continue
			if not resolved.is_file() or resolved.stat().st_size > _MAX_TILE_BYTES:
				continue
			return resolved, extension
	return None


@frappe.whitelist(methods=["GET"])
def tile(layer: str, variant: str, z, x, y):
	"""Serve only existing tiles in the shared `private/siraj_tile_cache` tree."""
	if frappe.session.user == "Guest" or not frappe.has_permission("Camera", "read"):
		frappe.throw("Sign in with Camera read permission to access map tiles.", frappe.PermissionError)
	if not isinstance(layer, str) or len(layer) > 20 or not isinstance(variant, str) or len(variant) > 20:
		frappe.throw("Invalid tile layer.", frappe.ValidationError)
	z = _tile_coordinate(z, "zoom")
	x = _tile_coordinate(x, "x")
	y = _tile_coordinate(y, "y")
	if z > 19:
		frappe.throw("Only zoom levels 0 through 19 are available.", frappe.ValidationError)
	max_xy = 1 << z
	if x >= max_xy or y >= max_xy:
		frappe.throw("Tile x/y is outside the selected zoom level.", frappe.ValidationError)
	result = _tile_path(layer, variant, z, x, y)
	if not result:
		return Response(status=404, headers={"Cache-Control": "no-store"})
	path, extension = result
	try:
		with path.open("rb") as stream:
			data = stream.read(_MAX_TILE_BYTES + 1)
	except OSError:
		return Response(status=404, headers={"Cache-Control": "no-store"})
	if len(data) > _MAX_TILE_BYTES:
		return Response(status=404, headers={"Cache-Control": "no-store"})
	if extension == "png":
		if not data.startswith(b"\x89PNG\r\n\x1a\n"):
			return Response(status=404, headers={"Cache-Control": "no-store"})
		content_type = "image/png"
	else:
		if not data.startswith(b"\xff\xd8\xff"):
			return Response(status=404, headers={"Cache-Control": "no-store"})
		content_type = "image/jpeg"
	response = Response(data, content_type=content_type)
	response.headers["Cache-Control"] = "private, max-age=3600"
	response.headers["X-Content-Type-Options"] = "nosniff"
	return response
