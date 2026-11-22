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

# Load only the local Leaflet stylesheet globally. Leaflet's JS is loaded by
# map views on demand, avoiding Desk-wide JavaScript cost when no map is open.
app_include_css = ["/assets/camera_archive_management/vendor/leaflet/leaflet.css"]

# Sensitive credentials are protected independently of future DocType metadata.
permission_query_conditions = {
	"Camera Credential": "camera_archive_management.api.permissions.camera_credential_query_conditions",
}
has_permission = {
	"Camera Credential": "camera_archive_management.api.permissions.camera_credential_has_permission",
}

# Lifecycle and scheduled handlers are intentionally registered in Phase 3,
# alongside their real controller/task implementations. Keeping these maps
# empty makes Phase 2 migrations safe and avoids dangling hook paths.
doc_events = {}
scheduler_events = {}

# Offline assets are local. No tile or geocoder provider is configured here;
# all network integrations require a later explicit administrator opt-in.
