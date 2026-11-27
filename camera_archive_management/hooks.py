app_name = "camera_archive_management"
app_title = "Camera Archive Management"
app_publisher = "Camera Archive Management"
app_description = (
	"Camera inventory, motion events, vehicle registers, and offline-capable geographic tools for Frappe."
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
	},
	{
		"dt": "Dashboard Chart",
		"filters": [["chart_name", "in", [
			"Camera Archive - Camera Status", "Camera Archive - Daily Movements",
			"Camera Archive - Movement Direction", "Camera Archive - Vehicles by Type",
			"Camera Archive - Cameras by Area",
		]]],
	},
]

# Keep map presentation styles global, but load Leaflet only inside our map page.
# The small compatibility script restores Frappe's Draw plugin only for the
# Camera Geolocation control when another app has replaced the global Leaflet.
app_include_js = [
	"/assets/camera_archive_management/js/camera_geolocation_compat.js",
	"/assets/camera_archive_management/js/camera_natural_earth.js",
]
app_include_css = ["/assets/camera_archive_management/css/camera_archive.css"]

# Camera credentials live on Camera at permlevel 1: only System Manager holds
# permlevel-1 read/write, so Frappe hides the fields in forms, strips them from
# API/list/report reads, and resets unauthorized writes. Password values are
# encrypted by Frappe's standard __Auth lifecycle.

doc_events = {
	"Geo Dataset": {
		"on_update": "camera_archive_management.jobs.dispatch.queue_geo_dataset_import",
	},
}

scheduler_events = {
	"daily": ["camera_archive_management.tasks.reconcile.requeue_pending_work"],
}

# Install additive reference catalogs and the app-owned dashboard counters.
# Number Card JSON is imported explicitly because Frappe v15 does not discover
# Number Cards in third-party app module folders (the Siraj-Research pattern).
after_migrate = [
	"camera_archive_management.setup.seed.seed_core_reference_data",
	"camera_archive_management.setup.dashboard.sync_number_cards",
]

# Offline assets are local. No tile or geocoder provider is configured here;
# all network integrations require a later explicit administrator opt-in.
