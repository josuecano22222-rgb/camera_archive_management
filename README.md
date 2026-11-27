# Camera Archive Management · 1.1.0

**العربية:** [دليل التهيئة والتوثيق باللغة العربية](camera_archive_management/docs/ar/onboarding/README.md)

A Frappe v15 application for camera inventory, controlled image galleries, vehicle registers, motion-event review, and permission-aware geospatial operations.

## New in 1.1.0

- **Archive retirement & credential merge.** The `Archive Asset`, `Archive Ingest Batch`, and `Archive Settings` DocTypes and the `Archive Integrity` report are completely removed (including their physical tables), and `Camera Credential` is merged into `Camera` as permlevel-1 fields readable/writable only by System Manager. Migration patches fail closed and require a backup first — see [`docs/v1.0.0-release-runbook.md`](docs/v1.0.0-release-runbook.md) for the destructive-change details.
- **Natural Earth Vector geography.** A committed, SHA-256-pinned 18-layer public-domain pack (cultural + physical; points, lines, polygons; 1:110m / 1:50m / 1:10m) powers a new **Geography layers** panel on the map: zoom-based country detail switching, click-to-inspect country profiles (capital, population, GDP, area), disputed-boundary overlays, and choropleth theming from cameras, movements, Natural Earth estimates, or custom ISO-keyed data. Everything is self-hosted; no external map or statistics API is contacted. Full guide: [`docs/natural-earth-vector.md`](docs/natural-earth-vector.md).
- **Complete Arabic/English localization.** Every user-facing string — including the geography UI, layer labels, validation messages, and country/capital names (from Natural Earth `NAME_AR`) — is translated, with an RTL-correct panel layout and a regression test that fails on any untranslated feature string.
- **Cache-busted assets.** The geography JS/CSS carry a content-hash query (`?v=…`) so browsers always fetch the current version on a normal refresh.

## Release highlights

- Camera records own their ordered image gallery and selected main image. The main image is used for the native Frappe Image view and as the circular, coordinate-anchored map pin portrait.
- The Camera Archive Map includes configurable basemaps, status/area and record filters, synchronized route state, Field pulse metrics, movement replay, geodesic tools, and rich camera/event popups. Vehicle imagery is reused on events, track endpoints, feeds, and reports; camera pins reflect status and selection.
- With explicit browser-profile opt-in, the map can persist the current filtered snapshot, viewed popup details, and viewed images in IndexedDB for offline use. Uncached media and snapshots are visibly marked; storage can be cleared from the map. Raster tiles continue to use the shared Siraj server cache and are not copied into browser storage.
- Geographic lookup is local-first and supports imported, attributed GeoJSON datasets. External geocoding remains opt-in. Map tile fetching and shared-cache writes remain governed by the Siraj administrator settings and must not be enabled by this app by default.
- Camera and vehicle classification catalogs are additive core reference data. After migration, the app creates only missing classifications; it never overwrites site-defined descriptions or records.
- A separate, explicitly enabled synthetic scenario exercises the map with fictional Amsterdam-area camera areas, multi-image cameras at precise decimal coordinates, vehicle types and illustrations (including per-vehicle and type-fallback cases), and timestamped Entry/Exit events with replay tracks and nearby-camera context. It is never installed or seeded automatically, is excluded from the map by default, and is visibly marked. Creation requires a deliberate per-site opt-in and explicit administrator command.

## Data and safety

The reference catalogs in `camera_archive_management/data/core_reference_data.json` are application master data, not demonstrations. Synthetic records are separate, never created by install or migrate, and generated only by an explicit operator command after enabling the per-site Boolean `camera_archive_allow_demo_data=true`. The command works on a disposable test site and, when deliberately authorized, on `frappe.com`:

```bash
bench --site <site-name> set-config camera_archive_allow_demo_data True --parse
bench --site <site-name> execute camera_archive_management.setup.demo_data.create_demo_scenario
```

The generator creates 12 cameras with two attached illustrations each and seven-decimal coordinate strings, four filterable demo areas, eight vehicles across four demo-only vehicle types (half have their own image; the rest exercise type-image fallback), and 72 Entry/Exit events arranged as nine timestamped track points per vehicle. Events carry nearby-camera distances and bearings. Synthetic camera and vehicle illustrations are bundled in `camera_archive_management/data/demo_camera_images/` and `camera_archive_management/data/demo_vehicle_images/`; none are real photographs or surveillance footage. Generated cameras, areas, vehicles, demo-only vehicle types, events, and their attached files carry the `CAM-MAP-V1-DEMO` tag. Demo records are excluded from the map unless the synthetic-data toggle is selected. Remove only this scenario and its owned attachments with:

```bash
bench --site <site-name> execute camera_archive_management.setup.demo_data.delete_demo_scenario
bench --site <site-name> set-config camera_archive_allow_demo_data False --parse
```

Do not enable the flag casually: production demo records are fictional and must never be mistaken for operational cameras or incidents.

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
python -m unittest camera_archive_management.geo.test_tile_cache camera_archive_management.geo.test_geometry camera_archive_management.geo.test_natural_earth camera_archive_management.camera_archive_management.test_doctype_interface -v
```

Run Frappe-dependent tests from a Frappe Bench environment with the app installed:

```bash
bench --site <test-site> run-tests --app camera_archive_management
```

Also validate Python and JavaScript syntax, build app assets, and review the data migration on a disposable copy before any production update.

## Version

The current release is **1.1.0** (`main`, tag `v1.1.0`). Upgrading from `v1.0.0` runs the destructive archive-retirement and credential-merge patches: **take a full backup first** and follow [`docs/v1.1.0-release-runbook.md`](docs/v1.1.0-release-runbook.md) (which references the patch-level detail in [`docs/v1.0.0-release-runbook.md`](docs/v1.0.0-release-runbook.md)). Sites already updated along the release branch only need the standard build/cache/restart verification. The full suite is 153 tests. No synthetic records are created automatically.
