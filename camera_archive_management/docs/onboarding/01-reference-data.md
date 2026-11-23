# 01 — Geographic and operational reference data

## Goal and prerequisites

Make the geographic and classification vocabulary trustworthy before registering production cameras. A System Manager or CAM Geo Administrator should first confirm data-source licensing, privacy rules, and the intended jurisdiction labels. The app ships a pinned, public-domain Natural Earth 1:110m world-country outline set. It is deliberately coarse and cartographic; it is not a legal boundary, address gazetteer, or replacement for regional operational data.

## Configure spatial behavior

Open **CAM Geo Settings** from the workspace. Review the active dataset, default search radius and ambiguity threshold. Keep online geocoding disabled unless a privacy/security review approves the provider, user-agent, rate limit, cache duration, and the disclosure of lookup queries. Online tile fetching and writes to the shared tile cache are separate controls; approve each explicitly. For disconnected or sensitive environments, prefer authorized local data and local map resources.

Coordinates use WGS84 decimal degrees. Latitude is −90 through 90; longitude is −180 through 180. Preserve the source precision exactly. Do not treat a geocoder result as verified merely because it returned one result—record its provenance and resolve ambiguity.

## Dataset → areas → boundaries

### Geo Dataset

Create a dataset record before its children. Give it a stable lowercase dataset ID, label, source/publisher, version, license identifier, attribution, and country tags. Supply WGS84 coverage bounds as a complete west/south/east/north set when known. Preserve the original source file privately when importing: Geo Dataset rejects a source file that is not a private, registered Frappe File. Read the provider's redistribution and privacy terms first.

Let the importer manage import status, progress, feature count, timestamp, and error details. Do not hand-edit status to `Running`, `Complete`, or `Failed`. Check that the reported counts and coverage match the input before activating the dataset.

### Geo Admin Area

Create a clean parent-child hierarchy with stable codes and explicit dataset links. Use the source's level convention consistently, assign the correct parent before creating a child, and set `Is Group` only for parent nodes. Mark source provenance as Imported, Verified, Manual, or Disputed and explain manual/disputed decisions in source notes. Keep similarly named administrative areas disambiguated by their parent and source code.

### Geo Boundary

Create geometry against the correct dataset. Use a stable boundary code and source ID; link parent boundary and administrative area where supported. Include the required geometry child rows and bounds. Validate a small sample visually in the map before importing a large collection. Do not label generalized or disputed shapes as authoritative. If using a third-party boundary, record the license/attribution and keep the source revision reproducible.

## Operational classifications

- **Camera Area** is your operational deployment hierarchy: site, station, district, or another team-owned grouping. It is not the same as a jurisdiction.
- **Camera Type** describes device capability, not the location or status of one camera. Review seeded values before creating near-duplicates; deactivate obsolete categories rather than changing their meaning.
- **Vehicle Type** describes useful analysis classes. Avoid a class per individual vehicle unless the distinction is genuinely operational.

## Validation checkpoint

Before moving to the camera registry, verify: the intended active dataset is selected; its import is Complete (if imported); parent/child area links are coherent; source/license metadata is recorded; a known point resolves to the expected area; and a sample boundary appears in the expected place. Investigate an empty map through dataset coverage and location-quality reports before changing any camera coordinates.
