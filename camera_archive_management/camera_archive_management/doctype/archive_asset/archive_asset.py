from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

import frappe
from frappe.model.document import Document

_SHA256 = re.compile(r"^[a-fA-F0-9]{64}$")
_EXTERNAL_SCHEMES = {"archive", "https", "s3"}


class ArchiveAsset(Document):
	def validate(self) -> None:
		previous = self.get_doc_before_save()
		status_changed = not previous or previous.index_status != self.index_status
		if (
			status_changed
			and self.index_status in {"Running", "Complete", "Failed"}
			and not self.flags.get("worker_update")
		):
			frappe.throw(
				"Only the archive index worker may set Running, Complete, or Failed status.",
				frappe.PermissionError,
			)
		if self.checksum_sha256 and not _SHA256.fullmatch(self.checksum_sha256.strip()):
			frappe.throw("Checksum must be a 64-character SHA-256 hex digest.", frappe.ValidationError)
		if self.size_bytes is not None and int(self.size_bytes) < 0:
			frappe.throw("Size cannot be negative.", frappe.ValidationError)
		if self.recorded_from and self.recorded_to and self.recorded_to < self.recorded_from:
			frappe.throw("Recording end time must be after its start time.", frappe.ValidationError)

		backend = self.storage_backend or "Frappe File"
		if backend == "Frappe File":
			if not self.file_url or self.external_reference:
				frappe.throw("Frappe File storage requires file_url and no external reference.")
			self._validate_file_url()
		elif backend == "External":
			if self.file_url or not self.external_reference:
				frappe.throw("External storage requires an external reference and no file_url.")
			if not frappe.get_single("Archive Settings").allow_external_archive_references:
				frappe.throw(
					"External archive references are disabled in Archive Settings.", frappe.PermissionError
				)
			self._validate_external_reference()
		else:
			frappe.throw("Unsupported Archive Asset storage backend.", frappe.ValidationError)

	def _validate_file_url(self) -> None:
		url = str(self.file_url or "")
		if not (url.startswith("/private/files/") or url.startswith("/files/")):
			frappe.throw("file_url must be a Frappe-managed /files/ or /private/files/ URL.")
		if ".." in unquote(url).split("/") or "\\" in url or "\x00" in url:
			frappe.throw("Unsafe file URL path.", frappe.ValidationError)
		if self.flags.get("prevalidated_private_file") and frappe.flags.get("cam_archive_ingest_worker"):
			return
		file_doc = frappe.db.get_value("File", {"file_url": url}, ["name", "is_private"], as_dict=True)
		if not file_doc or not file_doc.is_private:
			frappe.throw("Archive Asset files must be private Frappe attachments.")

	def _validate_external_reference(self) -> None:
		reference = str(self.external_reference or "").strip()
		if len(reference) > 2048 or "\x00" in reference or "\\" in reference:
			frappe.throw("External reference is invalid or exceeds 2048 characters.", frappe.ValidationError)
		parsed = urlsplit(reference)
		if parsed.scheme.lower() not in _EXTERNAL_SCHEMES or not parsed.netloc:
			frappe.throw("External reference must use archive://, s3://, or https://.")
		if parsed.username or parsed.password or parsed.query or parsed.fragment:
			frappe.throw("External reference cannot include credentials, query parameters, or fragments.")
		if any(part == ".." for part in unquote(parsed.path).split("/")):
			frappe.throw("External reference cannot contain parent traversal components.")
		if parsed.scheme == "https" and not parsed.hostname:
			frappe.throw("External HTTPS reference requires a host.")
		if parsed.scheme.lower() == "s3":
			bucket = parsed.netloc
			object_key = unquote(parsed.path.lstrip("/"))
			if (
				len(bucket) < 3
				or not object_key
				or any(part in {"", ".", ".."} for part in object_key.split("/"))
			):
				frappe.throw(
					"S3 reference must identify a bucket and safe object key.", frappe.ValidationError
				)
