# 04 — Routine operations, statistics, privacy, and recovery

## A useful review cadence

Set a cadence appropriate to operational volume and legal obligations:

- **Each ingest run:** review queued/running/failed batches, processed counts, error logs, and pending archive indexes.
- **Daily or per shift:** inspect camera status changes, movement timestamps/direction, and location or ingest exceptions that affect active operations.
- **Weekly:** use Camera Coverage, Vehicle Movement Timeline, Archive Integrity, and Geo Location Quality to resolve gaps and stale/inconsistent records.
- **At the approved retention interval:** review expired assets and legal holds through the organization's authorized deletion/retention procedure. A dashboard is not a deletion approval.

## Interpret dashboard statistics carefully

Number Cards count documents visible under the current user's read permissions. Filtered cards report Active Cameras, Pending Archive Index, and Failed Ingest Batches. Charts show distributions by camera status/area, movement direction, vehicle type, archive retention/index state, batch status, and daily movement/intake trends. The daily movement chart uses the event detection time; the archive intake trend groups created Archive Asset records by creation time. These are different clocks.

A chart count is not an independent audit. Missing records, role-limited visibility, delayed workers, duplicate source events, or the wrong timezone can distort a trend. Compare the aggregate with the report and source records; investigate a sudden jump or drop instead of inferring a cause from the graph alone.

## Privacy and security checklist

- Assign only the CAM roles needed for each job; test with a non-System-Manager account.
- Protect Camera Credential values and camera connectivity details; review export, report, backup, and administrator access.
- Treat movement histories, image/video attachments, manifests, and precise locations as potentially sensitive. Follow purpose limitation, retention, access logging, and legal hold rules.
- Online geocoding and tile requests may disclose locations to a third party. Keep integrations disabled until reviewed, and document the provider and data-flow approval.
- Use private files for sensitive source manifests and dataset GeoJSON as required by the DocType validation. Never publish secret-bearing manifests or storage references.
- Preserve provenance and audit history. Do not overwrite source facts to make dashboard totals or reports look tidy.

## Troubleshooting guide

- **Checklist missing:** System Settings → Enable Onboarding must be on; reload Desk; confirm the user has a CAM role and read access to the workspace.
- **Create step unavailable:** the onboarding entry does not grant access. Ask an administrator to assign the appropriate role rather than weakening DocType permissions.
- **Workspace card is blank:** verify the Number Card imported during migrate, the linked DocType is readable, and the user's role can read its source records. Check the browser/server logs for import or permission errors.
- **Map point absent or ambiguous:** verify coordinate order, signs, exact source values, active dataset coverage, and Geo Location Quality. Do not round coordinates to work around a mismatch.
- **Archive index pending/failed:** inspect the worker queue, asset storage link, batch status/error log, file permissions, and checksum. Follow the approved retry procedure; retain the failure trail.
- **Unexpected movement pattern:** validate time zone, camera clock, direction, duplicate events, and data completeness before treating it as a real route.

## Safe deployment sequence

On an already-installed `frappe.com` site, pull the approved app branch, rebuild assets, migrate, and clear cache. Take the normal database/files backup and use change approval before production updates:

```bash
git -C apps/camera_archive_management pull origin arena/8970c81a-camera-archive-management
bench build --app camera_archive_management
bench --site frappe.com migrate
bench --site frappe.com clear-cache
```

The migration imports app-owned Number Card JSON idempotently and refreshes standard Dashboard Chart fixtures and onboarding records. Validate the workspace and checklist in Desk after migration. Do not run `install-app` again on an already-installed site.
