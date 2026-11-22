"""Secure site-private storage layout and manifest contract.

The functions in this module are intended for trusted bench commands and
future background workers. They do not perform network access and do not
serve files. Dataset and tile-pack IDs must be explicitly allow-listed in
site_config.json before data paths can be resolved.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

LAYOUT = ("datasets", "tiles", "manifests")
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
MANIFEST_VERSION = 1


class StorageError(ValueError):
	"""Raised when configured private storage or a manifest is unsafe."""


def _frappe():
	try:
		import frappe
	except ImportError as exc:  # pragma: no cover - exercised in a bench
		raise RuntimeError("This command must run inside a Frappe bench site context") from exc
	return frappe


def _site_private_root() -> Path:
	frappe = _frappe()
	return Path(frappe.get_site_path("private")).absolute()


def _assert_not_symlink(path: Path) -> None:
	"""Reject a symlink at any existing path component."""
	for item in (path, *path.parents):
		try:
			if item.is_symlink():
				raise StorageError(f"Symlinked storage path is not allowed: {item}")
		except OSError as exc:
			raise StorageError(f"Cannot inspect storage path {item}: {exc}") from exc


def _contained_path(root: Path, *parts: str, create: bool = False) -> Path:
	"""Resolve a path under root while rejecting traversal and symlinks."""
	root = root.absolute()
	_assert_not_symlink(root)
	try:
		root_resolved = root.resolve(strict=True)
	except FileNotFoundError as exc:
		raise StorageError(f"Storage root does not exist: {root}") from exc

	candidate = root
	for part in parts:
		if not isinstance(part, str) or not part or part in {".", ".."}:
			raise StorageError("Empty or traversal path components are not allowed")

		component = Path(part)
		if component.is_absolute() or len(component.parts) != 1 or component.name != part:
			raise StorageError(f"Unsafe path component: {part!r}")
		candidate = candidate / part
		_assert_not_symlink(candidate)
		if create and not candidate.exists():
			candidate.mkdir(mode=0o750)
		_assert_not_symlink(candidate)

	try:
		resolved = candidate.resolve(strict=False)
		resolved.relative_to(root_resolved)
	except (OSError, ValueError) as exc:
		raise StorageError("Resolved path escapes the configured private storage root") from exc
	return candidate


def _allowed_ids(config_key: str) -> set[str]:
	conf = _frappe().get_conf()
	values = conf.get(config_key, []) if hasattr(conf, "get") else []
	if values is None:
		return set()
	if not isinstance(values, list | tuple):
		raise StorageError(f"{config_key} must be a list of approved IDs in site_config.json")
	result = set()
	for value in values:
		result.add(validate_id(value))
	return result


def validate_id(value: Any) -> str:
	"""Validate the conservative lowercase ID syntax used by directories."""
	if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
		raise StorageError("IDs must match [a-z0-9][a-z0-9._-]{0,63}")
	return value


def _require_allowlisted(value: Any, config_key: str) -> str:
	identifier = validate_id(value)
	if identifier not in _allowed_ids(config_key):
		raise StorageError(f"ID {identifier!r} is not listed in {config_key}")
	return identifier


def private_storage_root(create: bool = False) -> Path:
	"""Return the app's private root, optionally creating it safely."""
	root = _site_private_root()
	if not root.exists():
		raise StorageError(f"Frappe private directory does not exist: {root}")
	return _contained_path(root, "camera_archive_management", create=create)


def ensure_private_storage() -> dict[str, str]:
	"""Create the approved private directory layout; safe for bench execute."""
	root = private_storage_root(create=True)
	paths = {"root": str(root)}
	for dirname in LAYOUT:
		paths[dirname] = str(_contained_path(root, dirname, create=True))
	return paths


def dataset_path(dataset_id: str, *relative_parts: str, create: bool = False) -> Path:
	"""Resolve an allow-listed dataset path under private/datasets."""
	dataset_id = _require_allowlisted(dataset_id, "camera_archive_dataset_ids")
	root = private_storage_root(create=create)
	return _contained_path(root, "datasets", dataset_id, *relative_parts, create=create)


def tile_pack_path(pack_id: str, *relative_parts: str, create: bool = False) -> Path:
	"""Resolve an allow-listed tile-pack path under private/tiles."""
	pack_id = _require_allowlisted(pack_id, "camera_archive_tile_pack_ids")
	root = private_storage_root(create=create)
	return _contained_path(root, "tiles", pack_id, *relative_parts, create=create)


def manifest_path(kind: str, identifier: str, create: bool = False) -> Path:
	"""Resolve a manifest path for an approved dataset or tile-pack ID."""
	if kind == "dataset":
		identifier = _require_allowlisted(identifier, "camera_archive_dataset_ids")
	elif kind == "tile_pack":
		identifier = _require_allowlisted(identifier, "camera_archive_tile_pack_ids")
	else:
		raise StorageError("Manifest kind must be 'dataset' or 'tile_pack'")
	root = private_storage_root(create=create)
	if create:
		_contained_path(root, "manifests", create=True)
	return _contained_path(root, "manifests", f"{kind}-{identifier}.json")


def validate_manifest(manifest: Any, *, verify_files: bool = False) -> dict[str, Any]:
	"""Validate the stable JSON manifest contract and optionally file hashes.

	Required keys: manifest_version, kind, id, version, source, license,
	attribution, files. Each file has a relative path, byte size, and SHA-256.
	Optional bounds use west/south/east/north decimal-degree values.
	"""
	if not isinstance(manifest, dict):
		raise StorageError("Manifest must be a JSON object")
	required = {"manifest_version", "kind", "id", "version", "source", "license", "attribution", "files"}
	missing = required.difference(manifest)
	if missing:
		raise StorageError(f"Manifest is missing keys: {', '.join(sorted(missing))}")
	if manifest["manifest_version"] != MANIFEST_VERSION:
		raise StorageError(f"Unsupported manifest_version: {manifest['manifest_version']!r}")
	kind = manifest["kind"]
	identifier = manifest["id"]
	if kind == "dataset":
		identifier = _require_allowlisted(identifier, "camera_archive_dataset_ids")
	elif kind == "tile_pack":
		identifier = _require_allowlisted(identifier, "camera_archive_tile_pack_ids")
	else:
		raise StorageError("Manifest kind must be 'dataset' or 'tile_pack'")
	for key in ("version", "source", "license", "attribution"):
		if not isinstance(manifest[key], str) or not manifest[key].strip():
			raise StorageError(f"Manifest {key} must be a non-empty string")
	files = manifest["files"]
	if not isinstance(files, list):
		raise StorageError("Manifest files must be a list")
	seen = set()
	for entry in files:
		if not isinstance(entry, dict) or not {"path", "size_bytes", "sha256"}.issubset(entry):
			raise StorageError("Each manifest file requires path, size_bytes, and sha256")
		relative = entry["path"]
		if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
			raise StorageError("Manifest file paths must be non-empty relative paths")
		parts = Path(relative).parts
		if any(part in {".", ".."} for part in parts) or "\\" in relative or relative in seen:
			raise StorageError(f"Unsafe or duplicate manifest file path: {relative!r}")
		seen.add(relative)
		if (
			isinstance(entry["size_bytes"], bool)
			or not isinstance(entry["size_bytes"], int)
			or entry["size_bytes"] < 0
		):
			raise StorageError("Manifest size_bytes must be a non-negative integer")
		digest = entry["sha256"]
		if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
			raise StorageError("Manifest sha256 must be 64 lowercase hexadecimal characters")
		file_path = (
			_contained_path(private_storage_root(), "datasets", identifier, *parts)
			if kind == "dataset"
			else _contained_path(private_storage_root(), "tiles", identifier, *parts)
		)
		if verify_files:
			if not file_path.is_file():
				raise StorageError(f"Manifest file is missing or not a regular file: {relative}")
			if file_path.stat().st_size != entry["size_bytes"]:
				raise StorageError(f"Manifest file size mismatch: {relative}")
			hasher = hashlib.sha256()
			with file_path.open("rb") as handle:
				for block in iter(lambda: handle.read(1024 * 1024), b""):
					hasher.update(block)
			if hasher.hexdigest() != digest:
				raise StorageError(f"Manifest checksum mismatch: {relative}")
	bounds = manifest.get("bounds")
	if bounds is not None:
		if not isinstance(bounds, dict) or set(bounds) != {"west", "south", "east", "north"}:
			raise StorageError("bounds must contain exactly west, south, east, and north")
		try:
			west, south, east, north = (float(bounds[key]) for key in ("west", "south", "east", "north"))
		except (TypeError, ValueError) as exc:
			raise StorageError("bounds values must be numeric") from exc
		if not (-180 <= west <= 180 and -180 <= east <= 180 and -90 <= south <= 90 and -90 <= north <= 90):
			raise StorageError("bounds are outside WGS84 coordinate ranges")
		if south > north:
			raise StorageError("bounds south must not exceed north")
	return manifest


def write_manifest(manifest: dict[str, Any], *, verify_files: bool = False) -> Path:
	"""Validate then atomically write a deterministic UTF-8 JSON manifest."""
	validate_manifest(manifest, verify_files=verify_files)
	target = manifest_path(manifest["kind"], manifest["id"], create=True)
	payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
	fd, temporary_name = tempfile.mkstemp(prefix=".manifest-", dir=target.parent)
	try:
		with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
			handle.write(payload)
			handle.flush()
			os.fsync(handle.fileno())
		os.replace(temporary_name, target)
	except Exception:
		try:
			os.unlink(temporary_name)
		except FileNotFoundError:
			pass
		raise
	return target


def storage_health_check() -> dict[str, Any]:
	"""Check local private storage and manifests without network access."""
	root = private_storage_root()
	result: dict[str, Any] = {"ok": True, "network_access": False, "root": str(root), "directories": {}}
	for dirname in LAYOUT:
		path = _contained_path(root, dirname)
		result["directories"][dirname] = {
			"exists": path.is_dir(),
			"writable": os.access(path, os.W_OK) if path.is_dir() else False,
		}
		if not path.is_dir() or not os.access(path, os.W_OK):
			result["ok"] = False
	manifest_dir = _contained_path(root, "manifests")
	manifest_count = 0
	if manifest_dir.is_dir():
		for path in sorted(manifest_dir.glob("*.json")):
			_assert_not_symlink(path)
			try:
				data = json.loads(path.read_text(encoding="utf-8"))
				validate_manifest(data, verify_files=False)
			except (OSError, json.JSONDecodeError, StorageError) as exc:
				result["ok"] = False
				result.setdefault("manifest_errors", []).append({"file": path.name, "error": str(exc)})
			manifest_count += 1
	result["manifest_count"] = manifest_count
	return result
