# Camera Archive Management — guided onboarding

**العربية:** [دليل التهيئة باللغة العربية](../ar/onboarding/README.md)

This guide follows the native Frappe **Module Onboarding → Onboarding Step** framework, as implemented in the public Siraj-Research app. The in-app checklist is called **Camera Archive Management Setup** and is embedded in the Camera Archive Management workspace. It walks from geographic and classification reference data to a camera, a vehicle, a movement observation, and an indexed/verified archive asset. The JSON records live under `camera_archive_management/camera_archive_management/module_onboarding/` and `onboarding_step/`; the workspace embeds the named onboarding block and tests verify every step target.

## Show the checklist

Frappe v15 hides onboarding when the global **Enable Onboarding** setting is off. A System Manager should open **System Settings**, enable **Enable Onboarding**, and save. This app deliberately does not toggle that global setting during installation: doing so could also expose onboarding flows belonging to other apps. Reload Desk and open `/app/camera-archive-management`.

The checklist is shown to System Manager, CAM Operator, CAM Archive Manager, and CAM Geo Administrator. Read-only CAM Viewer and CAM Analyst roles still use the workspace, live cards, charts, and reports; the create-heavy setup checklist is not shown to them. Some steps are marked optional because permissions are intentionally split across geo, operations, and archive roles. The onboarding checklist does not grant permissions. Ask a System Manager to assign the minimum needed CAM roles before starting:

| Role | Typical work |
|---|---|
| CAM Viewer | Read workspace, map, reports, and records |
| CAM Operator | Maintain camera/vehicle/event operational records |
| CAM Analyst | Review authorized reports and movement data |
| CAM Archive Manager | Manage archive assets and ingest operations |
| CAM Geo Administrator | Maintain geographic datasets, areas, and boundaries |
| System Manager | Site-wide configuration and restricted credentials |

Some records have narrower permissions than the general onboarding. In particular, Camera Credential is restricted. The credential step is optional and should only be opened by an authorized user. If a step is inaccessible, request the correct role; do not broaden DocType permissions just to make onboarding clickable.

## Recommended sequence

1. **Workspace and access** — identify the responsible operator, analyst, archive manager, and geo administrator.
2. **Geographic settings and source** — decide whether local/offline data is required; review the active dataset, tile policy, online geocoder, and source licensing.
3. **Geographic reference data** — register a dataset, build administrative areas, then import/verify boundary geometry. The install includes generalized Natural Earth country outlines only; these are not legal boundaries or detailed local coverage.
4. **Operational taxonomies** — create Camera Areas (operational hierarchy), review Camera Types, and review Vehicle Types. The app seeds missing core camera/vehicle classifications additively and preserves local changes.
5. **Archive policy** — review retention, checksum, external-reference, integrity-check, and alert defaults before archiving real material.
6. **Inventory** — register the camera with precise coordinates and provenance; store credentials only in the protected credential DocType when genuinely needed. Add vehicle identities only when supported and authorized.
7. **Observation and archive** — record a movement event with accurate time/direction; link it to a vehicle only when supported. Index the recording as an Archive Asset, then use a stable idempotency key for a batch ingest where the ingest pipeline applies.
8. **Quality loop** — inspect the map, Camera Coverage, Vehicle Movement Timeline, Archive Integrity, and Geo Location Quality reports. Fix issues in the source records and re-run the relevant report.

Detailed notes: [01 — Geographic reference data](01-reference-data.md), [02 — Camera registry](02-camera-registry.md), [03 — Movements and archive](03-movements-archive.md), and [04 — Operations and privacy](04-operations.md).

## How to read the live dashboard

The workspace includes eight live Number Cards: total/active cameras, camera areas, recorded movements, registered vehicles, archive assets, pending archive indexing, and failed ingest batches. The charts cover camera status, daily movements, Entry/Exit direction, vehicle type, cameras by area, archive retention state, archive index status, ingest-batch pipeline status, and the archive-intake trend.

These are triage indicators, not evidence by themselves. A zero can mean no records, insufficient permission, or an incomplete import; charts aggregate records visible to the current user. Always drill into the source list/report, verify date/time zones and source coverage, and account for role permissions before making operational conclusions.

## Safe update and verification commands

From the Bench directory, update the app branch that carries these changes, rebuild assets, migrate the `frappe.com` site, and clear its cache. Do not run a migration against a production site without your normal backup and change-approval procedure.

```bash
# From your Bench directory. Review `git status --short` first and preserve local changes.
APP=apps/camera_archive_management
BRANCH=arena/8970c81a-camera-archive-management
git -C "$APP" status --short
git -C "$APP" fetch origin "$BRANCH"
if git -C "$APP" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git -C "$APP" switch "$BRANCH"
else
  git -C "$APP" switch --track -c "$BRANCH" "origin/$BRANCH"
fi
git -C "$APP" pull --ff-only origin "$BRANCH"
bench build --app camera_archive_management
bench --site frappe.com migrate
bench --site frappe.com clear-cache
```

For a fresh site only, install the app before migrating (do not repeat this on an already-installed site):

```bash
bench --site frappe.com install-app camera_archive_management
bench build --app camera_archive_management
bench --site frappe.com migrate
```

To check the packaged JSON and static workspace references without a live site, run the app's tests from the repository root:

```bash
python -m unittest camera_archive_management.camera_archive_management.test_workspace -v
python -m compileall -q camera_archive_management
```

A static test is not a substitute for clicking the onboarding flow in a running Frappe site with the actual Desk roles, site data, and browser. Confirm `Enable Onboarding`, role visibility, create/save actions, chart results, and report routes in the target site after migration.
