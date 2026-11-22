"""Explicit permission hooks for sensitive Camera Archive Management records."""

from __future__ import annotations

import frappe


def _is_credential_authorized(user: str | None = None) -> bool:
	"""Return whether a user may access camera credentials.

	Credentials are System Manager-only by policy. Frappe's Administrator is
	also accepted as the site superuser, even if role lookup is bypassed.
	"""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return "System Manager" in frappe.get_roles(user)


def camera_credential_has_permission(doc=None, user: str | None = None, permission_type=None) -> bool:
	"""Deny Camera Credential access unless the caller is a site administrator."""
	return _is_credential_authorized(user)


def camera_credential_query_conditions(user: str | None = None) -> str:
	"""Prevent non-administrators from discovering any Camera Credential rows."""
	return "" if _is_credential_authorized(user) else "1=0"
