app_name = "camera_archive_management"
app_title = "Camera Archive Management"
app_publisher = "Camera Archive Management"
app_description = (
	"Camera inventory, archive management, motion events, and offline-capable geographic tools for Frappe."
)
app_email = "josuecano22222@gmail.com"
app_license = "mit"

# Frappe v15 is the supported major version. Bench owns the actual framework checkout.
required_apps = []

# Role records are provisioned as app fixtures. System Manager is a built-in role.
fixtures = [
	{
		"dt": "Role",
		"filters": [
			[
				"name",
				"in",
				[
					"CAM Viewer",
					"CAM Operator",
					"CAM Analyst",
					"CAM Archive Manager",
					"CAM Geo Administrator",
				],
			]
		],
	}
]

# Keep the approved local Leaflet build and map styles available throughout Desk.
app_include_css = [
	"/assets/camera_archive_management/vendor/leaflet/leaflet.css",
	"/assets/camera_archive_management/css/camera_archive.css",
]
app_include_js = ["/assets/camera_archive_management/vendor/leaflet/leaflet.js"]

# Sensitive credentials are protected independently of future DocType metadata.
permission_query_conditions = {
	"Camera Credential": "camera_archive_management.api.permissions.camera_credential_query_conditions",
}
has_permission = {
	"Camera Credential": "camera_archive_management.api.permissions.camera_credential_has_permission",
}

doc_events = {
	"Archive Ingest Batch": {
		"on_update": "camera_archive_management.jobs.dispatch.queue_ingest_batch",
	},
	"Geo Dataset": {
		"on_update": "camera_archive_management.jobs.dispatch.queue_geo_dataset_import",
	},
	"Archive Asset": {
		"on_update": "camera_archive_management.jobs.dispatch.queue_archive_asset_index",
	},
}

scheduler_events = {
	"daily": ["camera_archive_management.tasks.reconcile.requeue_pending_work"],
}

# Offline assets are local. No tile or geocoder provider is configured here;
# all network integrations require a later explicit administrator opt-in.
