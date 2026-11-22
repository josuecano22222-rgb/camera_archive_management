# Phase 5: Frappe integration and production hardening

## Current verification boundary

The repository tests can verify deterministic cache, controller, API and migration
policy behavior. They cannot establish the state of the live `frappe.com` site,
its installed Siraj source, provider terms, Supervisor/Nginx/Redis health, or the
contents and ownership of `private/siraj_tile_cache`. Do not represent those
items as verified until site operators collect and review the evidence below.

Run the Frappe-integrated suite and migration rehearsal on a disposable staging
site cloned from the production schema and app versions, with credentials and
personal data protected. Do not run destructive or schema-changing tests
against the production site. Use a verified backup and restore rehearsal before
any production migration.

## Automated test manifest

- `camera_archive_management/api/test_tiles.py`: authenticated tile API behavior,
  valid multi-digit XYZ requests, cache hits, invalid coordinates, layer config,
  Camera-read permission boundary, bounded upstream responses, and throttled
  diagnostics.
- `camera_archive_management/api/test_map.py`: map API Camera-read permission,
  filter validation, and separation from Siraj's Place permission model.
- `camera_archive_management/api/test_permissions.py`: credential query/record
  authorization and checks that map payloads do not serialize credential
  material.
- `camera_archive_management/geo/test_tile_cache.py`: cache safety, atomic
  writes, Siraj `_`/legacy `base` behavior and canonical precedence, strict
  bounds, image validation, offline behavior, and concurrent miss deduplication.
- `camera_archive_management/camera_archive_management/doctype/cam_geo_settings/test_cam_geo_settings.py`:
  default-off fetch/write controls and timeout bounds.
- Existing Camera, Motion Event, Archive Asset, and Archive Ingest Batch tests
  now cover exact coordinate strings, historical location snapshots, private
  Frappe-file versus external-reference validation, and ingest idempotency.
- `camera_archive_management/patches/v1_0/test_migration_guards.py`: repeatable
  no-legacy/no-child-table cases and fail-closed collision checks for migrations.

These tests complement, but do not replace, a staging migration rehearsal on a
representative copy with legacy data. Review migration output and row counts
before and after; confirm credential plaintext is absent from legacy columns,
Siraj's `Geo Settings` metadata and Singles are unchanged, and existing app data
is retained. Rehearse the second migration pass on the same staging copy and
confirm it makes no unintended data changes.

## Live site evidence required

1. **Provider policy:** record the installed Siraj version and exact enabled
   layer catalog; the resolved provider host, User-Agent/headers, attribution,
   zoom limits, current provider terms, rate limits, cache/retention rights, and
   any credentials or date requirements. Keep both CAM tile controls disabled
   until the provider owner approves that record.
2. **Settings:** verify CAM fetch and cache-write flags are both disabled before
   rollout; confirm connect/read timeouts are 1–5 seconds. Capture Siraj's
   provider-fetch flag and per-layer enablement separately. A Siraj setting must
   not be treated as CAM authorization.
3. **Shared cache:** inventory overlapping `<layer>/base/<z>/<x>/<y>` and
   `<layer>/_/<z>/<x>/<y>` paths without changing or deleting files. CAM reads
   canonical `_` before legacy `base`; new base writes use `_`, overlays use
   `overlay`. Record duplicate counts and confirm which content is served for a
   known duplicate tile.
4. **HTTP behavior:** in an authenticated Camera-reader Desk session, exercise
   `standard/base` at `z=9,x=305,y=208` and `z=10,x=607,y=418`. A valid request
   must never return 417. Expect a cache hit or stale response with the matching
   cache header, a clean 404 JSON miss while fetching is disabled, or a 200 MISS
   only after policy-approved fetching and writing are deliberately enabled.
   `z=9,x=512,y=0` must return 400 JSON. A controlled upstream outage on an
   uncached tile should produce bounded 503 JSON with `Retry-After`; a cached
   tile must remain available without upstream connectivity.
5. **Coexistence and UI:** inspect CAM and Siraj map pages before and after
   rollout. Confirm attribution and layer controls, Desk-host tile URLs, route
   filter state/cleanup, camera image pins, vehicle icons/tracks, and cache/offline
   status. Verify Siraj Draw/map plugins and its own tile endpoint remain intact.
   Smoke-test Camera, Event, Archive forms and reports without changing records.
6. **Operations:** verify the backup archive and restore process, app build and
   migration results, web/worker/scheduler processes, Supervisor/Nginx/Redis
   health, logs, cache filesystem owner/mode, and that production
   `developer_mode` is disabled.

## Go/no-go gate

**No-go** if provider terms or attribution are unresolved, the installed Siraj
catalog does not match the integration assumptions, valid coordinates return
417, cache paths are unsafe, permission behavior is ambiguous, migration
rehearsal changes unrelated rows, tests fail, services are unhealthy, or the
backup cannot be restored.

**Go to controlled production enablement** only after all automated tests pass
on staging; migration is rehearsed twice on a representative clone; the live
policy/configuration and cache inventory are approved; UI/Siraj coexistence
passes; and backup, service health, logs, and production hardening are signed
by the site owner. Then an authorized administrator may enable both CAM flags
under the approved provider policy and verify one known tile before broader use.
