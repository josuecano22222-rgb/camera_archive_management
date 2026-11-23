"""Install app-owned Number Cards that power the Camera Archive workspace."""

from __future__ import annotations

import glob
import os

import frappe


def sync_number_cards() -> int:
	"""Idempotently import standard Number Card JSON during migrate.

	Frappe v15's module importer does not walk a non-core app's ``number_card``
	folder. Siraj-Research solves this by importing the app-owned records from
	an ``after_migrate`` hook; follow the same pattern rather than making the
	cards site fixtures. ``force=1`` makes app updates authoritative while
	repeated migrations stay safe by record name.
	"""
	from frappe.modules.import_file import import_file_by_path

	base = frappe.get_app_path("camera_archive_management", "camera_archive_management")
	paths = sorted(glob.glob(os.path.join(base, "number_card", "*", "*.json")))
	for path in paths:
		import_file_by_path(path, force=1, ignore_version=True)

	frappe.db.commit()
	frappe.logger().info("Camera Archive Management Number Cards synchronized: %s", len(paths))
	return len(paths)
