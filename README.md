# Camera Archive Management · 1.0.0

A Frappe v15 application for camera inventory, controlled image galleries, vehicle registers, motion-event review, and permission-aware geospatial operations.

## Release highlights

- Camera records own their ordered image gallery and selected main image. The main image is used for the native Frappe Image view and as the circular, coordinate-anchored map pin portrait.
- The Camera Archive Map includes configurable basemaps, camera/event/route layer toggles, date and record filters, a movement replay timeline, geodesic distance and area measurements, coordinate copy, and browser-local geolocation.
- Geographic lookup is local-first and supports imported, attributed GeoJSON datasets. External geocoding remains opt-in. Map tile fetching and shared-cache writes remain governed by the Siraj administrator settings and must not be enabled by this app by default.
- Camera and vehicle classification catalogs are additive core reference data. After migration, the app creates only missing classifications; it never overwrites site-defined descriptions or records.
- A separate, explicitly enabled synthetic scenario exercises the map with fictional Amsterdam-area cameras, vehicles, and motion events. It is not installed automatically, is excluded from the map by default, is visibly marked, and is refused on the production site `frappe.com`.

## Data and safety

The reference catalogs in `camera_archive_management/data/core_reference_data.json` are application master data, not demonstrations. Synthetic records are separate and created only by `camera_archive_management.setup.demo_data.create_demo_scenario` on a disposable, non-production site whose config explicitly sets `camera_archive_allow_demo_data=true`. On that disposable site only, enable the Boolean flag and invoke the generator with:

```bash
bench --site <disposable-demo-site> set-config camera_archive_allow_demo_data true --parse
bench --site <disposable-demo-site> execute camera_archive_management.setup.demo_data.create_demo_scenario
```

Delete only those generated records with `camera_archive_management.setup.demo_data.delete_demo_scenario` on that same safe site. The generator explicitly refuses `frappe.com`; do not add fictional camera, vehicle, or incident records to production.

The core pack includes Natural Earth generalized world country outlines (1:110m, public domain, pinned revision documented in `camera_archive_management/data/README.md`). These support global context and country-level local lookup, but are not legal, municipal, cadastral, or operational boundaries. The seed makes this pack active only when a site has no active dataset. Higher-resolution administrative or gazetteer datasets must be supplied by an administrator with verified provenance and license; the import path retains that attribution separately. The map can also be used for camera coordinates and authorized tile layers without any imported local data.

## Installation

Install from the release branch/tag appropriate to your Bench and supported Frappe v15 environment:

```bash
cd ~/frappe-bench
bench get-app https://github.com/josuecano22222-rgb/camera_archive_management --branch <release-ref>
bench --site <site-name> install-app camera_archive_management
```

The additive reference catalog is seeded after migration. Import boundary or gazetteer data only after verifying its provenance, license, coverage, and source-specific import requirements.

## Developer checks

Run framework-independent tests from the app repository:

```bash
python -m unittest camera_archive_management.geo.test_tile_cache camera_archive_management.geo.test_geometry camera_archive_management.camera_archive_management.test_doctype_interface -v
```

Run Frappe-dependent tests from a Frappe Bench environment with the app installed:

```bash
bench --site <test-site> run-tests --app camera_archive_management
```

Also validate Python and JavaScript syntax, build app assets, and review the data migration on a disposable copy before any production update.

## Version

This project declares its first complete release as **1.0.0**. The release is not production-ready until the migration and full Frappe test suite have passed on a disposable site, assets have built successfully, the required backup and maintenance-window procedure has been observed, and the operator explicitly approves deployment. Follow the gated, stop-and-confirm sequence in [`docs/v1.0.0-release-runbook.md`](docs/v1.0.0-release-runbook.md); it is guidance only and no production action is performed by these instructions.
