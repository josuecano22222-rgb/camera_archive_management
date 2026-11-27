# Natural Earth Vector — comprehensive geography integration

This guide documents how the Camera Archive map makes full, advanced use of [Natural Earth Vector](https://github.com/nvkelso/natural-earth-vector): a ready-made, public-domain world geographic database bundled into the app and served entirely from the Bench server. It covers the data pack, the backend API, country intelligence, thematic (choropleth) mapping, the interactive map panel, licensing, limitations, ecosystem fit, and how to refresh and deploy the bundle.

The integration is **self-hosted and offline-capable**: every layer is a committed file verified by a SHA-256 pin, and no external map, geocoding, or statistics API is contacted at runtime. Site-owned data (cameras, motion events) is joined to geography through Frappe's permission-filtered queries, so per-user access rules always apply.

## 1. What is bundled

The pack lives in `camera_archive_management/data/natural_earth/` and is described by `catalog.json`. It contains **18 layers and 3,450 features**, pinned to Natural Earth revision `ca96624a56bd078437bca8184e78163e5039ad19`.

| Layer id | Theme | Category | Geometry | Scale | Features |
| --- | --- | --- | --- | --- | ---: |
| `countries_110m` | countries | cultural | polygon | 1:110m | 177 |
| `countries_50m` | countries | cultural | polygon | 1:50m | 242 |
| `admin1_110m` | administrative | cultural | polygon | 1:110m | 51 |
| `boundary_lines_110m` | boundaries | cultural | line | 1:110m | 331 |
| `disputed_boundaries_50m` | boundaries | cultural | line | 1:50m | 34 |
| `disputed_areas_50m` | boundaries | cultural | polygon | 1:50m | 28 |
| `populated_places_110m` | places | cultural | point | 1:110m | 243 |
| `airports_10m` | transport | cultural | point | 1:10m | 893 |
| `ports_10m` | transport | cultural | point | 1:10m | 1,081 |
| `land_110m` | land | physical | polygon | 1:110m | 127 |
| `ocean_110m` | water | physical | polygon | 1:110m | 2 |
| `coastline_110m` | water | physical | line | 1:110m | 134 |
| `rivers_110m` | water | physical | line | 1:110m | 13 |
| `lakes_110m` | water | physical | polygon | 1:110m | 24 |
| `glaciated_110m` | land | physical | polygon | 1:110m | 11 |
| `physical_points_110m` | land | physical | point | 1:110m | 3 |
| `marine_polys_110m` | water | physical | polygon | 1:110m | 29 |
| `graticules_20` | grid | physical | line | 1:110m | 27 |

This spans the three geometry families (points, lines, polygons), the three cartographic scales (1:110m overview, 1:50m regional, 1:10m detail), and both cultural and physical geography. Each catalog entry carries the source URL, feature count, geometry types, bounding box, a Leaflet rendering style, a primary label field, and a SHA-256 integrity pin.

### Deliberate scope limits

- **Roads and railways are not bundled.** Their only Natural Earth vector source is 1:10m, and the files are tens of megabytes (roads ≈ 49 MB, railroads ≈ 38 MB) — far beyond a reasonable committed pack and the 25 MiB dataset import cap. There are no 1:50m roads/railroads layers at the pinned revision.
- **1:10m polygon themes are omitted** (countries, lakes, rivers, coastline, land, ocean) in favor of their 1:110m/1:50m equivalents, keeping the bundle near 8 MB. 1:10m is used only for the airport and port point layers.
- **Population and GDP are Natural Earth estimates** (circa 2019), not a live statistical database.

## 2. Architecture

```
data/natural_earth/*.geojson + catalog.json   committed, integrity-pinned reference pack
        │
geo/natural_earth.py                          framework-independent core (no Frappe import):
        │                                     catalog validation, layer loading + SHA-256 check,
        │                                     country hit-testing/profile, choropleth classification
api/natural_earth.py                          permission-checked, read-only whitelisted endpoints
        │
public/js/camera_natural_earth.js             map UI: layer panel, scale switching, inspector,
        │                                     choropleth + legend (window.cam_natural_earth)
public/css/camera_natural_earth.css           panel styles (dedicated file; see deployment note)
page/camera_archive_map/camera_archive_map.js hosts the panel and forwards zoom/click events
```

- The core module (`geo/natural_earth.py`) imports no Frappe symbols, so it is unit-testable without a running site. It caches the catalog and loaded layers in memory (`lru_cache`).
- The API layer (`api/natural_earth.py`) gates every endpoint on an authenticated, non-Guest session with **Camera read** permission — the same gate as the existing map payload. Site data joins use `frappe.get_list`, which enforces per-user permissions; the movements metric additionally requires **Motion Event read**.
- The UI module is loaded globally via `app_include_js` and initialized by the map page. It talks only to the four endpoints below.

The bundle is served directly from files; it is **not** seeded into `Geo Boundary` rows. This keeps the database lean (3,450 features stay on disk) while the existing seeded 1:110m country dataset continues to power the separate "Country borders" overlay. The two are complementary.

## 3. Backend API reference

All endpoints are `GET`, require Camera read permission, and return JSON. Errors use `frappe.ValidationError` / `frappe.PermissionError`.

### `get_catalog()`
Returns the full catalog (layer metadata, no geometry) plus a `summary` (counts by category, geometry family, and scale; total features; license; revision), `attribution`, and `limitations`.

### `get_layer(layer_id)`
Returns `{ layer, geojson, attribution }` for one layer. `layer_id` must be a known catalog id (≤ 64 chars). The file's SHA-256 is verified against the catalog pin and the feature count is checked before serving; any mismatch raises a validation error. `layer` includes the rendering `style`, `name_field`, `bounds`, `source`, and `sha256`.

### `get_country_profile(code=None, latitude=None, longitude=None)`
Returns `{ profile, attribution }`. Provide either an ISO_A3 / boundary `code` (≤ 8 chars) or a WGS84 `latitude`/`longitude` pair (validated by the shared coordinate parser). The profile is built from the bundled country attributes:

- Identity: `code`, `iso_a2`, `name`, `name_long`, `sovereign`, `type`.
- Geography: `continent`, `region`, `subregion`, `area_km2` (spherical estimate), `label_longitude`/`label_latitude`.
- Estimates: `population_estimate` + `population_year`, `gdp_million_usd` + `gdp_year`, `economy`, `income_group`.
- `capital`: derived from the populated-places layer (`FEATURECLA = "Admin-0 capital"`), with name, admin1, coordinates, and population.

Returns `profile: null` when no country matches (e.g. open ocean). Natural Earth stores some `ISO_A3` values as `-99` (France, Norway, …); the code normalizes these from `ADM0_A3` so lookups remain correct.

### `get_country_choropleth(metric="cameras", method="quantile", classes=5, values=None)`
Aggregates a metric per country and classifies it for choropleth rendering. Returns `{ values, classification, meta }`.

- **Metrics**:
  - `cameras` — counts permission-filtered cameras per country by point-in-polygon join against the bundle (works even for cameras that have not been geo-resolved). Bounded to 5,000 cameras; `meta.truncated` flags the cap and `meta.located_cameras` reports how many had coordinates.
  - `movements` — sums permission-filtered motion events per country through their cameras (requires Motion Event read).
  - `population` / `gdp` — Natural Earth's own per-country estimates (`meta.note` flags that they are not live).
  - `custom` — an external ISO-code→number mapping supplied as JSON in `values` (≤ 300 entries, finite numbers). This is the hook for joining outside datasets such as climate or business indicators.
- **Classification**: `method` is `quantile` (even feature distribution) or `equal_interval` (equal-width bands); `classes` is an integer 2–9. `classification` returns `breaks` (class upper bounds), `min`, `max`, and `empty`.
- `meta.provenance` is `site_data`, `natural_earth_bundle`, or `external_join` accordingly.

## 4. Interactive map panel

Open **Geography layers** in the map toolbox to reveal the panel (a docked overlay on the map canvas). It has three sections:

1. **Reference layers** — a Countries toggle with a scale selector (**Auto detail by zoom**, 1:110m, or 1:50m), plus grouped Cultural and Physical layer checkboxes, each showing its scale badge and feature count. Enabling a layer fetches and integrity-checks it once, then renders it with its catalog style. Points become circle markers, lines render with their dash pattern, polygons are filled. Every feature has a name tooltip.
2. **Thematic map (choropleth)** — choose a metric, class count, and classification method (or paste custom ISO→number JSON), then **Apply theme**. The country layer is recolored along a yellow→red ramp, a legend with class ranges and a "No data" swatch appears, and a note reports provenance and any camera-scan truncation. **Clear theme** restores the plain outlines.
3. **Inspector** — click any bundled feature (country, city, river, airport, …) to highlight it and see its details. Countries show the full profile card (name, capital, population, GDP, area, continent, region, economy) with a **Zoom to country** button; other features show their key attributes and a **Zoom to feature** button. Clicking empty map space looks up the country under the cursor (or reports open ocean).

### Scale selection
In **Auto** mode the country layer uses 1:110m below zoom 5 and switches to 1:50m at zoom 5 and above, balancing cleanliness at global view against detail when zoomed in. The switch is seamless and re-applies any active choropleth. You can also pin a scale explicitly.

### Attribution
The panel footer shows the license, pinned revision, and limitations. The first time a layer is enabled, "Natural Earth · public domain" is added to the map's attribution control.

## 5. Disputed boundaries and point of view

The `disputed_boundaries_50m` (lines) and `disputed_areas_50m` (polygons) layers expose Natural Earth's disputed/breakaway representation as distinct, optionally-enabled red-dashed overlays. They are **off by default** and labeled as disputed. Natural Earth ships a single default point of view; these layers reflect that default and are **not** an authoritative or selectable sovereignty determination. For alternative political worldviews, import a dataset with its own provenance through the existing Geo Dataset pipeline.

## 6. Licensing and terms of use

Natural Earth vector data is **public domain** — free for commercial and non-commercial use without fee or permission. The app retains provenance (source repository, pinned revision, per-layer source URLs) and surfaces attribution in the catalog, API responses, and map panel, consistent with Natural Earth's [Terms of Use](https://www.naturalearthdata.com/about/terms-of-use/). No warranty is implied; the data is provided "as is".

## 7. Limitations (read before operational use)

- Generalized **small-scale cartography**. Not cadastral, not legal boundaries, not street-level navigation, not live traffic, not imagery, and not a live population/statistical feed.
- Accuracy depends on scale: 1:110m is heavily generalized; 1:50m and 1:10m add detail but remain cartographic, not survey-grade.
- Not automatically current: the pack is pinned to a fixed revision; refresh it deliberately (below).
- Country area is a spherical estimate for comparison, not a legal survey area.
- Disputed boundaries reflect Natural Earth's default point of view only.

## 8. Ecosystem fit

Every layer is standard **GeoJSON** (WGS84 / EPSG:4326), so the pack interoperates directly with QGIS, GeoPandas, PostGIS (`ST_GeomFromGeoJSON`), MapLibre/Mapbox GL, D3, and Leaflet. The committed files can be loaded into any of these tools without conversion; the catalog's `source` URLs point back to the exact upstream features.

## 9. Refreshing the bundle

The pack is generated by `scripts/build_natural_earth_bundle.py` (optional maintenance tooling; the app never runs it):

```bash
python3 scripts/build_natural_earth_bundle.py
```

The script downloads each selected layer through the GitHub git-blob API at the pinned `REVISION`, compact-serializes the GeoJSON, and regenerates `catalog.json` with fresh feature counts, bounds, geometry types, and SHA-256 pins. To move to a newer Natural Earth revision, update `REVISION` (and the layer list if desired), run the script, review the diff, and commit the regenerated files. The runtime integrity checks will then enforce the new pins.

## 10. Tests

- `camera_archive_management/geo/test_natural_earth.py` — framework-independent unit tests (catalog validity, per-file integrity pins, geometry-family consistency, country hit-testing and profiles, ISO `-99` normalization, choropleth classification, geodesic area). Runs with plain `python3 -m unittest`.
- `camera_archive_management/api/test_natural_earth.py` — site tests (`FrappeTestCase`) for permission gates, layer serving and validation, country profiles, and all choropleth metrics including permission-filtered camera/movement joins and custom-value validation.

Run the pure-Python suite locally:

```bash
python3 -m unittest camera_archive_management.geo.test_natural_earth camera_archive_management.geo.test_geometry
```

Run the full app suite on the site (see the deployment commands below).

## 11. Deploying to `frappe.com`

This change adds bundled files, a read-only API, and two new global assets (`camera_natural_earth.js` and `camera_natural_earth.css`). It introduces **no DocType, schema, or patch changes**, so no data migration is required. Build the assets and clear caches so the new `app_include_js` / `app_include_css` entries are picked up.

> **Why the panel styles live in their own file.** Frappe serves non-`.bundle.` app CSS with a plain `<link href="…">` and **no cache-busting version**. Adding rules to the already-cached `camera_archive.css` would not reach browsers that hold a stale copy. The Natural Earth styles therefore ship in a dedicated `camera_natural_earth.css` (a new URL fetched fresh by every browser), registered separately in `app_include_css`. If the panel ever appears unstyled, confirm that file is listed in `app_include_css` and that caches were cleared after the hooks change.

```bash
cd ~/frappe-bench/apps/camera_archive_management
git pull --ff-only
git rev-parse HEAD   # confirm it matches the pushed commit

cd ~/frappe-bench
bench --site frappe.com backup --with-files
bench build --app camera_archive_management
bench --site frappe.com clear-cache
bench --site frappe.com clear-website-cache
bench restart
bench doctor
```

`bench migrate` is harmless to run but not needed for this change. Then verify:

```bash
bench --site frappe.com run-tests --app camera_archive_management
```

Open **Camera Archive Map**, click **Geography layers**, enable a few cultural and physical layers, switch the country scale, click a country to inspect its profile, and apply a choropleth (e.g. *Cameras per country*). Confirm the legend, attribution, and integrity-checked layers render and that no external map API is contacted.
