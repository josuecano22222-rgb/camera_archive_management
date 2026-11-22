from __future__ import annotations

from urllib.parse import unquote, urlsplit


def is_safe_frappe_file_url(value: str | None) -> bool:
	"""Accept only local Frappe file routes; reject URLs and traversal."""
	if not isinstance(value, str) or not value or len(value) > 512:
		return False
	parsed = urlsplit(value)
	if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
		return False
	path = unquote(parsed.path)
	if not (path.startswith("/files/") or path.startswith("/private/files/")):
		return False
	if "\\" in path or "\x00" in path:
		return False
	return all(part not in {".", ".."} for part in path.split("/"))
