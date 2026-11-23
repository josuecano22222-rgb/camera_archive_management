# Offline map and dataset storage

The application ships Leaflet 1.9.4 and a generalized Natural Earth 1:110m
world-boundary asset. It does not ship raster tiles, provider credentials, or
country-scale administrative datasets. See the adjacent vendor license and
attribution notices before redistributing assets.

## Browser map persistence

The Camera Archive Map offers an explicit **Save map snapshot, details and
images offline** option. It is off by default. When enabled, the current
filtered map payload, camera/event popup records opened by the operator, and
viewed images are stored in the browser's IndexedDB, namespaced by site origin
and Frappe user. Image downloads use same-origin authenticated requests; only
image responses are cached. Per-snapshot, per-image, entry-count, and aggregate
storage limits bound browser usage. The map keeps only a small number of recent
filter snapshots and evicts older entries.

This can retain sensitive operational details and authorized private images on
the local browser profile. Enable it only on a trusted managed device. It is
not encryption or an access-control boundary against someone with access to
the browser profile. Turn the option off or use **Clear offline data** to remove
that user's saved records and image blobs. The map's **Show saved popup details** action can display previously opened camera/event records even when no exact map snapshot is available; it explicitly marks them as saved historical records and bypasses current filters. The app does not cache raster tiles in the browser: offline basemaps still depend on the shared server-side Siraj cache and a reachable Bench server. The browser feature supports an already
loaded map page and exact matching saved filter snapshots; it does not make
the entire Frappe application shell available for a fresh visit with the
server disconnected. Items without a matching snapshot or cached image are
marked unavailable rather than represented as current data.

## Site-private dataset and tile-pack layout

Run from the Bench directory with the intended site selected explicitly:

```bash
bench --site site.example execute camera_archive_management.setup.storage.ensure_private_storage
bench --site site.example execute camera_archive_management.setup.storage.storage_health_check
```

The helper creates/checks this layout without making network calls:

```text
sites/site.example/private/camera_archive_management/
  datasets/<approved-dataset-id>/
  tiles/<approved-tile-pack-id>/
  manifests/
```

Dataset and tile-pack IDs must be explicitly approved in `site_config.json`.
For example, after review, an administrator can set these JSON arrays with:

```bash
bench --site site.example set-config camera_archive_dataset_ids '["sample-boundaries"]' --parse
bench --site site.example set-config camera_archive_tile_pack_ids '["local-standard"]' --parse
```

These settings only allowlist identifiers; they do not download, install, or
serve content. Keep pack provenance, redistribution rights, attribution, and
coverage under administrative review. Do not put private datasets or licensed
raster tiles in Git or in the public asset directory.

## Manifest contract, version 1

Each UTF-8 JSON manifest is named `dataset-<id>.json` or
`tile_pack-<id>.json` and uses deterministic key ordering when written by the
storage helper. The required fields are:

```json
{
  "manifest_version": 1,
  "kind": "dataset",
  "id": "sample-boundaries",
  "version": "2026-01",
  "source": "Operator-provisioned GeoJSON",
  "license": "CC-BY-4.0",
  "attribution": "Dataset provider attribution",
  "bounds": {"west": -10, "south": 35, "east": 5, "north": 60},
  "files": [
    {
      "path": "boundaries.geojson",
      "size_bytes": 1234,
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }
  ]
}
```

`bounds` is optional and uses WGS84 decimal degrees. Each file path is relative
to its approved dataset or tile-pack directory; absolute paths, `.`/`..`
components, backslashes, duplicate paths, symlinks, and paths resolving outside
the configured root are rejected. File checksums are lowercase SHA-256 hex.
The manifest validator can verify each file's size and checksum when explicitly
requested. Import, tile serving, and external downloads are not performed by
the site-private storage helper.
