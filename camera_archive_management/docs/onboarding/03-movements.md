# 03 — Vehicle movements

## Record a movement

Create a **Motion Event** after selecting the correct camera. Record Entry or Exit as observed, with the actual detection time and correct timezone. Link a CAM Vehicle only when the observation supports that identity; the event is still valid without a vehicle link. Set importance only when the event warrants it. Keep notes factual and avoid unnecessary personal data.

The event stores camera/location snapshots so later edits to the camera record do not silently rewrite what the event captured. Review the snapshot and event after save. The map, camera record, and **Vehicle Movement Timeline** report should agree on time, direction, and location. Correct a mistaken event at the source and retain the normal audit/version history; do not create a second event simply to hide the first.

When **Enable Nearby Camera Alerts** is on in CAM Geo Settings → Motion Events, saving a movement displays an in-form message for active cameras within the configured radius and cameras explicitly linked to the source Camera through its Nearby Cameras relation, in either direction. Submitting/approving the event displays the alert for that transition as well. The message distinguishes a configured connection from radius-only proximity and includes distance/direction/area where available. It does not claim that the other camera recorded the same vehicle; verify its own events before drawing conclusions.

The default event importance is inherited from the camera; when the camera has none, the **Default Motion Importance** in CAM Geo Settings → Motion Events applies (Medium out of the box).

## Validation checkpoint

- The Motion Event timestamp and direction match the original observation.
- Vehicle identity is linked only when supported.
- The camera/location snapshot reflects what the event actually captured.
- Nearby-camera context is consistent with the configured radius and explicit connections.

Then open **Vehicle Movement Timeline** and **Camera Coverage**. Drill from each aggregate back to source records before acting on the result.
