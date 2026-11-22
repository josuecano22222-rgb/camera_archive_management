# Offline map and dataset storage (Phase 2 contract)

The application ships only Leaflet 1.9.4 and a generalized Natural Earth
1:110m world-boundary asset. It does not ship raster tiles, country-scale
administrative datasets, or provider credentials. See the adjacent vendor
license and attribution notices before redistributing assets.

## Site-private layout

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
this Phase 2 helper.
