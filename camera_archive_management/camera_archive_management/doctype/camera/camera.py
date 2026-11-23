from __future__ import annotations

import json
from pathlib import PurePosixPath

import frappe
from frappe.model.document import Document

from camera_archive_management.geo.coordinates import (
	normalize_frappe_geolocation,
	point_feature_collection,
	point_from_geojson,
	validate_pair,
)
from camera_archive_management.utils.files import is_safe_frappe_file_url

MAX_PHOTO_CAPTION_LENGTH = 240
MAX_PHOTO_DESCRIPTION_LENGTH = 1200
_ALLOWED_IMAGE_SUFFIXES = {".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def _gallery_items(value) -> list[dict]:
	if not value:
		return []
	try:
		items = json.loads(value) if isinstance(value, str) else value
	except (TypeError, json.JSONDecodeError):
		frappe.throw("Camera image gallery data must be valid JSON.", frappe.ValidationError)
	if not isinstance(items, list):
		frappe.throw("Camera gallery data must be a JSON array.", frappe.ValidationError)

	result = []
	seen_urls = set()
	orders = []
	primary_count = 0
	for item in items:
		if not isinstance(item, dict):
			frappe.throw("Each camera gallery item must be an object.", frappe.ValidationError)
		url = item.get("url")
		if not is_safe_frappe_file_url(url):
			frappe.throw("Camera images must use a safe local Frappe file URL.", frappe.ValidationError)
		if url in seen_urls:
			frappe.throw("A camera image cannot appear more than once in its gallery.", frappe.ValidationError)
		seen_urls.add(url)

		caption = item.get("caption") or ""
		description = item.get("description") or ""
		if not isinstance(caption, str) or len(caption) > MAX_PHOTO_CAPTION_LENGTH:
			frappe.throw(f"Image captions must be at most {MAX_PHOTO_CAPTION_LENGTH} characters.", frappe.ValidationError)
		if not isinstance(description, str) or len(description) > MAX_PHOTO_DESCRIPTION_LENGTH:
			frappe.throw(
				f"Image descriptions must be at most {MAX_PHOTO_DESCRIPTION_LENGTH} characters.",
				frappe.ValidationError,
			)

		order = item.get("sort_order")
		if isinstance(order, bool) or not isinstance(order, int) or order < 0:
			frappe.throw("Every camera image requires a non-negative integer sort order.", frappe.ValidationError)
		is_primary = item.get("is_primary")
		if not isinstance(is_primary, bool):
			frappe.throw("The camera image main-image flag must be true or false.", frappe.ValidationError)
		primary_count += int(is_primary)
		orders.append(order)
		result.append(
			{
				"url": url,
				"caption": caption.strip(),
				"description": description.strip(),
				"is_primary": is_primary,
				"sort_order": order,
			}
		)

	if sorted(orders) != list(range(len(result))):
		frappe.throw("Camera image order must be a unique, contiguous sequence starting at zero.", frappe.ValidationError)
	result.sort(key=lambda photo: photo["sort_order"])
	if result and primary_count != 1:
		frappe.throw("Choose exactly one main image for a camera with gallery images.", frappe.ValidationError)
	return result


class Camera(Document):
	def validate(self) -> None:
		try:
			latitude, longitude = validate_pair(self.latitude, self.longitude)
			point = point_from_geojson(self.location)
		except ValueError as exc:
			frappe.throw(str(exc), frappe.ValidationError)
			return

		if point and latitude is None:
			self.latitude, self.longitude = str(point[0]), str(point[1])
		elif point and (latitude != point[0] or longitude != point[1]):
			frappe.throw(
				"Camera Location point and latitude/longitude disagree. Update them together explicitly.",
				frappe.ValidationError,
			)

		if point:
			self.location = normalize_frappe_geolocation(self.location)
		elif latitude is not None and longitude is not None:
			self.location = point_feature_collection(latitude, longitude)

		if self.port and not 1 <= int(self.port) <= 65535:
			frappe.throw("Port must be between 1 and 65535.", frappe.ValidationError)
		self._validate_image_gallery()

		nearby_names = [row.camera for row in self.nearby_cameras if row.camera]
		if self.name in nearby_names or len(nearby_names) != len(set(nearby_names)):
			frappe.throw(
				"Nearby cameras must be unique and cannot include this camera.", frappe.ValidationError
			)

		if self.area:
			parent = frappe.db.get_value("Camera Area", self.area, "is_group")
			if parent is None:
				frappe.throw("Selected Camera Area does not exist.", frappe.ValidationError)

	def _validate_image_gallery(self) -> None:
		photos = _gallery_items(self.camera_photos_json)
		if photos:
			urls = [photo["url"] for photo in photos]
			files = frappe.get_all(
				"File",
				filters={
					"file_url": ["in", urls],
					"attached_to_doctype": "Camera",
					"attached_to_name": self.name,
				},
				fields=["file_url", "file_name"],
				limit_page_length=len(urls) * 2,
			)
			files_by_url = {}
			for file_doc in files:
				files_by_url.setdefault(file_doc.file_url, []).append(file_doc)
			for photo in photos:
				matches = files_by_url.get(photo["url"], [])
				if len(matches) != 1:
					frappe.throw(
						"Every gallery image must be attached to this Camera as a Frappe File.",
						frappe.ValidationError,
					)
				file_doc = matches[0]
				suffix = PurePosixPath(file_doc.file_name or "").suffix.lower()
				if suffix not in _ALLOWED_IMAGE_SUFFIXES:
					frappe.throw("Camera gallery files must be recognized image formats.", frappe.ValidationError)

		self.camera_photos_json = json.dumps(photos, ensure_ascii=False, separators=(",", ":"))
		self.primary_image = next((photo["url"] for photo in photos if photo["is_primary"]), None)

	def before_save(self) -> None:
		# Location and address are deliberately not reverse-geocoded here. A user
		# must call the explicit lookup API and choose which fields to apply.
		if self.location and not isinstance(self.location, str):
			self.location = json.dumps(self.location, separators=(",", ":"))
