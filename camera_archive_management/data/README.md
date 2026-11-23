# Built-in data packs

**العربية:** [توثيق حزم البيانات باللغة العربية](README.ar.md)

## Core application references

- `core_reference_data.json` seeds additive Camera Type and Vehicle Type classifications. Existing records are not modified.
- `natural_earth_admin0_countries.geojson` is the global country-outline and country-level lookup pack. It is Natural Earth 1:110m Admin 0 data pinned to revision `ca96624a56bd078437bca8184e78163e5039ad19` from [nvkelso/natural-earth-vector](https://github.com/nvkelso/natural-earth-vector). Natural Earth describes the data as public domain in its [project README](https://github.com/nvkelso/natural-earth-vector/blob/ca96624a56bd078437bca8184e78163e5039ad19/README.md).

The bundled GeoJSON SHA-256 is `b587b32dc343c5896752d472f637bb050c8b8eccfbc7e5c8af72ada3072ac226`; the migration checks it before seeding. The polygons are deliberately generalized for global/continental/national map context. They are not cadastral, municipal, operational, legal, or authoritative sovereignty boundaries. The import creates the pinned dataset and missing country boundaries after migration, and selects it as the active dataset only if the site has not selected one already. Higher-resolution administrative and gazetteer data can be imported independently with their own source and license metadata.

## Synthetic demo scenario

Demo records are not included in either core data file. They are generated separately by the guarded helper documented in the project README, carry a `CAM-MAP-V1-DEMO` scenario tag, and are excluded from map results unless a user explicitly enables the synthetic-data toggle. The 12 small PNGs in `demo_camera_images/` are original, programmatically drawn illustrations; the generator attaches two distinct views to each synthetic camera. Four tiny PNGs in `demo_vehicle_images/` are original vehicle illustrations used for both per-vehicle images and demo vehicle-type fallback images. None are photographs, camera captures, real vehicle imagery, or operational seed data. Trial records include seven-decimal camera coordinates, four tagged areas, eight vehicles, and 72 Entry/Exit event snapshots with track and nearby-camera context. The generator only runs after explicit site opt-in and operator invocation; its cleanup removes the tagged trial records and their owned attachments.
