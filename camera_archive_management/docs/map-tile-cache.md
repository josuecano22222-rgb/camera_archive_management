# Camera map tiles: Siraj shared cache and online fallback

**العربية:** [توثيق ذاكرة البلاطات باللغة العربية](ar/map-tile-cache.md)

The Camera Archive map uses the installed `siraj_research` tile catalog; it does
not define or substitute provider URLs. It reads and writes only the site's
private `siraj_tile_cache` tree in Siraj's compatible layout:

```text
private/siraj_tile_cache/<layer>/<_|overlay>/<z>/<x>/<y>.<format>
```

The API's `base` variant maps to Siraj's canonical `_` directory; existing
explicit `base` directories are accepted when reading for compatibility. When
both contain the same tile, canonical `_` takes precedence.

The server checks the Camera read permission before serving map tiles. Provider
fetching is cache-first, server-side, and disabled unless all of these are true:

1. `CAM Geo Settings.enable_online_tile_fetch` is enabled.
2. `CAM Geo Settings.allow_tile_cache_write` is enabled.
3. `Geo Settings.allow_tile_fetch` in Siraj Research is enabled.
4. The requested layer is enabled in Siraj's Geo Settings.
5. The optional site-wide `camera_archive_allow_online_tile_fetch` config is
   not set to false.

The two CAM flags default to off. Review the selected provider's current terms,
cache/retention rights, required attribution, and contact/User-Agent policy
before enabling. The client shows attribution from Siraj's layer catalog. This
app does not add provider endpoints or API keys of its own. If Siraj or its
Geo Settings cannot be loaded, the configuration endpoint reports no raster
layers and online fetch remains disabled; it does not substitute a guessed
catalog or attribution.

## Inspection and root-cause checklist

Before enabling provider access on a site, run these checks from the Bench root
and review the installed Siraj source and provider policy (do not copy URLs from
this app or guess them):

```bash
bench version
rg -n --glob '*.py' --glob '*.js' --glob '*.md' \
  'LAYERS|_resolve_url|_ENABLE_FLAG|allow_tile_fetch|User-Agent|attribution|tile_cache' \
  apps/siraj_research/siraj_research
rg -n 'tile_cache_days|allow_tile_fetch|enable_.*standard|enable_.*aerial|enable_.*hybrid' \
  apps/siraj_research/siraj_research/doctype
find sites/frappe.com/private/siraj_tile_cache -type f \
  \( -path '*/standard/*/5/13/8.*' -o -path '*/aerial/*/5/13/8.*' \
     -o -path '*/hybrid/*/5/13/8.*' \) -print 2>/dev/null
```

For each enabled provider, confirm in Siraj's live layer specification and its
current linked terms: URL resolver/host, image MIME and format, attribution,
request `User-Agent` and any required headers/keys, cache rights/retention, and
zoom coverage. Confirm the `Geo Settings` singleton field names and values
against `tile_cache._settings()` and `_ENABLE_FLAG`; verify Siraj writes base
tiles as `_` and overlays as `overlay`. Do not enable fetching until all these
checks agree with the running Siraj version. The application-side root cause
for the earlier 417s was the former endpoint's `^(?:0|[1-9][0-9]?)$`
coordinate expression, which rejected valid XYZ x/y values of 100 or more; the
current handler parses decimal values then applies zoom-dependent XYZ bounds.
Use the verification requests below to confirm the deployed response is fixed.

## Architecture and data flow

1. `camera_archive_management/api/tiles.py` authenticates `Camera` read access,
   validates request arguments, checks CAM/Siraj controls and responds with
   attribution-bearing layer config. It serves cache hits first, queues
   deduplicated stale refreshes, rate limits calls, and emits cache/status
   headers and throttled diagnostics.
2. `camera_archive_management/geo/tile_cache.py` owns strict XYZ/layer allowlists,
   safe shared-cache reads, Siraj provider resolution, bounded HTTP/image
   validation, cross-process miss locking, per-worker concurrency, and atomic
   writes. It only uses the installed Siraj catalog and private shared cache.
3. `CAM Geo Settings` (`camera_archive_management/camera_archive_management/doctype/cam_geo_settings/`)
   supplies default-off fetch/write controls and bounded timeouts.
4. `camera_archive_management/camera_archive_management/page/camera_archive_map/camera_archive_map.js`
   loads the authorized layer config, retains the existing map filters and
   route behavior, and reports cache/provider/tile errors without a retry loop.
5. `camera_archive_management/geo/test_tile_cache.py` has runnable isolated
   tests; this document gives site-level checks. No Frappe, ERPNext, or Siraj
   core files are changed.

Request flow: Desk → authenticated Camera tile API → validate coordinates and
layer → read shared Siraj cache → if absent/stale and all policy controls allow,
lock and recheck → bounded request via Siraj's resolver → validate HTTP image
and atomically write to Siraj's canonical cache layout → return tile or a
bounded JSON error. Stale tiles return immediately while a background job may
refresh; cache hits never depend on provider connectivity.

## Runtime behavior

- Valid XYZ coordinates are checked as decimal integers, with zoom 0–19 and
  `0 <= x,y < 2^z`. Invalid requests return HTTP 400 JSON instead of Frappe's
  generic HTTP 417 validation response.
- Existing tiles are served before any network check. Fresh tiles return
  `X-CAM-Tile-Cache: HIT`; expired but valid tiles return immediately with
  `STALE` while one deduplicated background refresh is queued.
- A browser `404` from the tile endpoint can be a successful API route with a
  cache-miss response (`tile_missing`), not a missing Frappe method. When no
  cached XYZ tile exists and online fetching is disabled by default, Leaflet
  reports the missing image as a `tileerror`; camera and vehicle markers remain
  independent of raster availability. Prepopulate the shared private cache or
  explicitly enable provider fetching only after the policy checks above.
- On a cache miss, camera requests use a two-second connect timeout and a
  three-second read timeout by default. CAM Geo Settings constrains each to
  1–5 seconds. Simultaneous requests for the same tile share a cross-process
  advisory lock (using a fixed set of 4,096 hash shards); a per-worker semaphore
  caps concurrent upstream fetches at four. After the lock is acquired, the
  cache is checked again.
- Successful provider responses must match the Siraj catalog's image MIME
  type, PNG/JPEG magic signature, and the 2 MiB byte ceiling. A validated tile
  is written to a same-directory temporary file, fsynced, and atomically
  replaced into the shared cache.
- Upstream timeouts or invalid responses never replace a cached tile. A shared
  short circuit-breaker suppresses repeated upstream attempts during outages.
  If no cached tile exists, the API returns an explicit 404 (disabled/no tile)
  or 503 (upstream unavailable), not a fake image.
- Browser-to-Bench disconnection is not supported by this server cache. A
  connected Desk user can still access tiles if the Bench server has lost its
  external internet connection; a browser that cannot reach Bench cannot fetch
  its server cache. This app does not install a service worker or store tiles in
  browser storage.

## Rollout on the site

After pulling the app update, run:

```bash
cd ~/frappe-bench
bench --site frappe.com migrate
bench build --app camera_archive_management
bench --site frappe.com clear-cache
bench restart
```

In **CAM Geo Settings**, first review the terms for the provider already
selected in **Geo Settings** (Siraj Research), then enable both **Enable Online
Tile Fetch** and **Allow Shared Tile Cache Writes**. Confirm the desired layers
are enabled in Siraj's Geo Settings and its **Allow server to fetch from
provider** setting is enabled. The Camera map will list only enabled Siraj
raster layers. Disable either CAM flag or Siraj's setting to stop new outbound
requests and writes; existing verified tiles remain available to authorized
Camera readers.

A site-wide emergency deny can be applied with:

```bash
bench --site frappe.com set-config camera_archive_allow_online_tile_fetch false
```

## Verification

From a logged-in browser on Desk, use DevTools Console to check configuration:

```js
fetch("/api/method/camera_archive_management.api.tiles.config")
  .then(async r => console.log(r.status, await r.json()));
```

A valid cached or freshly fetched standard tile should return HTTP 200 with an
image content type and `X-CAM-Tile-Cache` set to `HIT`, `STALE`, or `MISS`:

```js
fetch("/api/method/camera_archive_management.api.tiles.tile?layer=standard&variant=base&z=9&x=305&y=208")
  .then(async r => console.log(r.status, r.headers.get("content-type"),
    r.headers.get("x-cam-tile-cache"), r.status >= 400 ? await r.text() : "image bytes"));
```

This request also exercises coordinates that previously exceeded the old
one/two-digit validator and caused 417 responses. An out-of-range coordinate
such as `z=9&x=512&y=0` should return HTTP 400 JSON. For offline testing, fetch
and cache a tile first, disable CAM online fetching (or block the Bench host's
outbound provider access), then request that same tile: it should remain HTTP
200 from cache. A different uncached tile during an upstream outage should
return 503 within the configured timeout, with a warning rate-limited in the
server log.

Test concurrent cache misses against a staging provider before production;
the per-tile lock should result in one provider request per missing tile. To
verify Siraj sees the same tile, request the corresponding layer through
`/api/method/siraj_research.tile_cache.tile` as a user with Siraj's Place read
permission, then confirm the matching file exists under
`sites/frappe.com/private/siraj_tile_cache/`. Do not purge the shared cache as a
test; Siraj owns files in the same tree.
