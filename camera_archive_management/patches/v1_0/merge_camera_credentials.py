"""Merge the retired Camera Credential DocType into Camera's protected credential fields.

Camera now owns the credential profile at permlevel 1 (System Manager only).
This patch preserves existing secrets through Frappe's normal document save
lifecycle so Password values are re-encrypted into ``__Auth`` under Camera,
promotes any pre-isolation plaintext still sitting in Camera's legacy columns,
and only then retires the standalone DocType. It is repeatable and fail-closed:
ambiguous or undecryptable data aborts the migration instead of being discarded.
"""

from __future__ import annotations

import frappe

APP_NAME = "camera_archive_management"
LEGACY_DOCTYPE = "Camera Credential"
CREDENTIAL_FIELDS = (
	"credential_label",
	"credentials_active",
	"username",
	"password",
	"secondary_secret",
	"last_rotated_at",
	"credential_notes",
)


def _doctype_app(doctype: str) -> str | None:
	module = frappe.db.get_value("DocType", doctype, "module")
	return frappe.db.get_value("Module Def", module, "app_name") if module else None


def _is_dummy_password(value) -> bool:
	"""Frappe stores ``*****`` placeholders in Password columns; secrets live in __Auth."""
	return bool(value) and set(str(value)) == {"*"}


def _plaintext_camera_rows() -> list[dict]:
	"""Camera rows whose password column still holds pre-isolation plaintext."""
	if not frappe.db.table_exists("Camera") or not frappe.db.has_column("Camera", "password"):
		return []
	rows = frappe.db.sql(
		"SELECT `name`, `username`, `password` FROM `tabCamera` "
		"WHERE `password` IS NOT NULL AND `password` <> ''",
		as_dict=True,
	)
	return [row for row in rows if not _is_dummy_password(row.password)]


def _credential_rows() -> list[dict]:
	if not frappe.db.table_exists(LEGACY_DOCTYPE):
		return []
	return frappe.get_all(
		LEGACY_DOCTYPE,
		fields=["name", "camera", "credential_label", "active", "username", "last_rotated_at", "notes"],
		order_by="camera asc, name asc",
		limit_page_length=0,
	)


def _decrypted_secret(credential_doc, fieldname: str) -> str | None:
	"""Read a legacy secret, refusing to continue when it cannot be decrypted."""
	if not credential_doc.get(fieldname):
		return None
	value = credential_doc.get_password(fieldname, raise_exception=False)
	if not value:
		frappe.throw(
			f"Could not decrypt {fieldname} of Camera Credential {credential_doc.name}; "
			"refusing to discard the stored secret.",
			frappe.ValidationError,
		)
	return value


def execute() -> None:
	legacy_meta = bool(frappe.db.exists("DocType", LEGACY_DOCTYPE))
	legacy_table = bool(frappe.db.table_exists(LEGACY_DOCTYPE))
	plaintext_rows = _plaintext_camera_rows()
	if not legacy_meta and not legacy_table and not plaintext_rows:
		return
	if legacy_meta and _doctype_app(LEGACY_DOCTYPE) != APP_NAME:
		frappe.throw(
			f"{LEGACY_DOCTYPE} is not owned by {APP_NAME}; refusing to modify it.",
			frappe.PermissionError,
		)
	if legacy_table and not legacy_meta:
		frappe.throw(
			f"{LEGACY_DOCTYPE} table exists without DocType metadata; refusing destructive cleanup.",
			frappe.ValidationError,
		)

	missing = [field for field in CREDENTIAL_FIELDS if not frappe.db.has_column("Camera", field)]
	if missing:
		frappe.throw(
			f"Camera credential fields are not present after model sync ({', '.join(missing)}); "
			"no credentials were migrated.",
			frappe.ValidationError,
		)

	by_camera: dict[str, dict] = {}
	for row in _credential_rows():
		if row.camera in by_camera:
			frappe.throw(
				f"Multiple Camera Credential records exist for Camera {row.camera}; "
				"resolve the duplicates before merging.",
				frappe.ValidationError,
			)
		by_camera[row.camera] = row
	plaintext_by_camera = {row.name: row for row in plaintext_rows}

	migrated = 0
	skipped = 0
	for camera_name in sorted(set(by_camera) | set(plaintext_by_camera)):
		if not frappe.db.exists("Camera", camera_name):
			# Orphaned credential for a deleted camera: its secret is retired with the DocType.
			frappe.logger("camera_archive_management.credentials").warning(
				"Skipping Camera Credential for missing Camera %s", camera_name
			)
			skipped += 1
			continue

		credential = by_camera.get(camera_name)
		plaintext = plaintext_by_camera.get(camera_name) or {}
		camera = frappe.get_doc("Camera", camera_name)
		if credential:
			credential_doc = frappe.get_doc(LEGACY_DOCTYPE, credential.name)
			camera.credential_label = credential.credential_label
			camera.credentials_active = credential.active
			camera.last_rotated_at = credential.last_rotated_at
			camera.credential_notes = credential.notes
			if credential.username:
				camera.username = credential.username
			password = _decrypted_secret(credential_doc, "password")
			if password:
				camera.password = password
			elif plaintext.get("password"):
				camera.password = plaintext["password"]
			secondary_secret = _decrypted_secret(credential_doc, "secondary_secret")
			if secondary_secret:
				camera.secondary_secret = secondary_secret
		else:
			# Pre-isolation plaintext: promote it into the protected fields. Saving
			# through the document lifecycle encrypts the password into __Auth.
			camera.credentials_active = 1
			if plaintext.get("username"):
				camera.username = plaintext["username"]
			if plaintext.get("password"):
				camera.password = plaintext["password"]
		camera.save(ignore_permissions=True)
		migrated += 1

	if migrated + skipped != len(set(by_camera) | set(plaintext_by_camera)):
		frappe.throw(
			"Credential merge did not account for every source record; the legacy DocType was kept.",
			frappe.ValidationError,
		)

	# Secrets were re-encrypted under Camera; remove the legacy __Auth entries and retire the DocType.
	frappe.db.delete("__Auth", {"doctype": LEGACY_DOCTYPE})
	# Frappe keeps the physical table after DocType deletion; drop it while ownership is
	# still verifiable so no credential rows survive. sql_ddl commits first, so a failed
	# drop leaves a repeatable state (metadata present, table gone) rather than an orphan.
	if frappe.db.table_exists(LEGACY_DOCTYPE, cached=False):
		frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{LEGACY_DOCTYPE}`")
	if legacy_meta:
		frappe.delete_doc("DocType", LEGACY_DOCTYPE, force=True, ignore_permissions=True)
		frappe.clear_cache(doctype=LEGACY_DOCTYPE)
	frappe.logger("camera_archive_management.credentials").info(
		"Merged %s camera credential record(s) into Camera (%s orphaned skipped)", migrated, skipped
	)
