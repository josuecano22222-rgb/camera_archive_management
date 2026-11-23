# 02 — Camera registry and access

## Goal and prerequisites

Build a complete, spatially credible camera inventory. Complete the reference-data setup first: Camera Area and Camera Type records should exist, and geographic data should cover the deployment region. A CAM Operator can maintain cameras; CAM Geo Administrator maintains geographic catalogs. Site-specific permissions remain authoritative.

## Create the camera record

Open **Camera** → **New** and fill the fields your policy permits:

| Field group | Guidance |
|---|---|
| Camera Name, status, Camera Type | Use a durable, unique label; set Active/Inactive/Maintenance honestly; select a defined type. |
| Area | Select the operational Camera Area. Do not use a free-text jurisdiction name as a substitute. |
| Coordinates and location | Enter exact WGS84 latitude/longitude. Verify sign, coordinate order, and source precision. Add address, Geo Admin Area, and Geo Boundary only when substantiated. |
| Identifiers and deployment | Serial number, camera number, installation date, IP/port, importance, and description are optional—collect only what is needed, with appropriate access. |
| Image and coverage | Use an authorized main image. Describe field of view and coverage accurately; avoid exposing sensitive angles or network details to broad audiences. |

Save the record and reopen it. Confirm the pin is where expected, its area and geographic associations are right, and the lookup source/confidence/ambiguity fields tell the truth. Use **Camera Coverage** and **Geo Location Quality** for inventory-wide review.

## Credentials and permissions

Camera Credential is a separate restricted DocType, not a general notes field. Only the specifically authorized role should create or read it. Put secrets in the Password fields; keep the label and notes non-secret; record rotation dates. Never put passwords, tokens, or recovery codes in Camera descriptions, event notes, manifests, onboarding text, or screenshots. The onboarding credential action is optional because many deployments do not store credentials in Frappe and most CAM users must not access them.

Connectivity metadata can still be sensitive. Use least privilege for IP address, port, and camera identity; check list, export, report, and backup access—not only form visibility.

## Vehicle identities

Create a CAM Vehicle only when the identity is useful and justified. Select an existing Vehicle Type, use stable identifiers only when collection is authorized, and set status correctly. Do not create a new vehicle record for each observation. If identity is uncertain, leave the event's vehicle link blank and describe uncertainty through approved fields/processes rather than guessing.

## Validation checkpoint

A camera should have an appropriate type and operational area, verified coordinates and provenance, and a useful status. A vehicle should have a justified identity and type. Confirm each record is visible only to authorized roles, and verify the map marker against its source before using it for route or coverage conclusions.
