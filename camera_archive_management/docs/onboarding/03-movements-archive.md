# 03 — Vehicle movements and archived recordings

## Record a movement

Create a **Motion Event** after selecting the correct camera. Record Entry or Exit as observed, with the actual detection time and correct timezone. Link a CAM Vehicle only when the observation supports that identity; the event is still valid without a vehicle link. Set importance only when the event warrants it. Keep notes factual and avoid unnecessary personal data.

The event stores camera/location snapshots so later edits to the camera record do not silently rewrite what the event captured. Review the snapshot and event after save. The map, camera record, and **Vehicle Movement Timeline** report should agree on time, direction, and location. Correct a mistaken event at the source and retain the normal audit/version history; do not create a second event simply to hide the first.

When **Enable Nearby Camera Alerts** is on in Archive Settings, saving a movement displays an in-form message for active cameras within the configured radius and cameras explicitly linked to the source Camera through its Nearby Cameras relation, in either direction. Submitting/approving the event displays the alert for that transition as well. The message distinguishes a configured connection from radius-only proximity and includes distance/direction/area where available. It does not claim that the other camera recorded the same vehicle; verify its own events before drawing conclusions.

## Create an Archive Asset

An **Archive Asset** is the catalog/index entry for one recording or evidence object. Link the camera, optional Motion Event, and optional Archive Ingest Batch. Populate capture start/end, media type, byte size, storage backend, retention state, and checksum where available or required. The Frappe File backend uses an authorized attachment; External storage uses the configured storage scope/reference and should not expose public/private URLs in notes.

Validate that the time window is sensible, the linked event belongs to the intended camera, and SHA-256 represents the exact stored bytes. Retention state must follow the approved retention schedule and any legal hold. Index status is workflow-managed; do not manually mark an asset complete to bypass indexing or integrity checks.

## Batch ingest

Use **Archive Ingest Batch** when processing a manifest or a pipeline batch. Select a source scope and a stable idempotency key. Keep manifests private when they contain identifiers or storage references. Validate source item keys, capture windows, camera references, file sizes and checksum formats before queueing. The batch status, started/finished times, processed count, and error log are the operational record of the run.

For a test, start with a small authorized manifest, wait for the worker result, inspect created Archive Assets, and retry only according to the idempotency contract. Reusing the same key is important for safe retry behavior; inventing a new key for an identical retry can create duplicates. Do not place access credentials in a manifest or error report.

## Validation checkpoint

- The Motion Event timestamp and direction match the original observation.
- Vehicle identity is linked only when supported.
- Archive Asset points to the correct camera/event and has a coherent recording window.
- Storage location is private/authorized; checksum and index state are independently verified.
- Ingest batch status and processed count reconcile with its manifest; failures are investigated, not hidden.

Then open **Archive Integrity** and **Vehicle Movement Timeline**. Drill from each aggregate back to source records before acting on the result.
