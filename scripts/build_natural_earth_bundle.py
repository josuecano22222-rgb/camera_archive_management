#!/usr/bin/env python3
"""Rebuild the bundled Natural Earth vector data pack from a pinned revision.

This is an optional maintenance script. The generated GeoJSON layers and
``catalog.json`` are committed to the repository, so the running application
never needs network access. Run it only to refresh the bundle against a new
pinned Natural Earth revision:

    python3 scripts/build_natural_earth_bundle.py

It downloads each selected layer through the GitHub git-blob API (which works
for files larger than the 1 MiB contents-API limit), compact-serializes the
GeoJSON, and regenerates ``catalog.json`` with feature counts, bounds, geometry
types, and a SHA-256 pin for every bundled file.
"""

from __future__ import annotations

import base64
import hashlib
import json
import urllib.request
from pathlib import Path

REVISION = "ca96624a56bd078437bca8184e78163e5039ad19"
REPO = "nvkelso/natural-earth-vector"
API = f"https://api.github.com/repos/{REPO}"
SOURCE_BASE = f"https://github.com/{REPO}/blob/{REVISION}/geojson"
LICENSE = "Public Domain"
ATTRIBUTION = (
	"Natural Earth vector data; public domain. Generalized cartographic data — not legal, "
	"cadastral, or authoritative sovereignty boundaries. Revision " + REVISION[:12] + "."
)

OUT_DIR = Path(__file__).resolve().parents[1] / "camera_archive_management" / "data" / "natural_earth"

# Ordered layer specifications. ``style`` carries Leaflet rendering hints consumed
# by the map; ``name_field`` is the primary label property used in popups/tooltips.
LAYERS = [
	{
		"id": "countries_110m",
		"source": "ne_110m_admin_0_countries",
		"label": "Countries (1:110m)",
		"category": "cultural",
		"theme": "countries",
		"geometry": "polygon",
		"scale": "110m",
		"name_field": "NAME",
		"default_visible": False,
		"description": "World countries and territories with rich attributes (ISO codes, capital, continent, region, population and GDP estimates).",
		"style": {
			"color": "#0f766e",
			"weight": 1.2,
			"opacity": 0.8,
			"fillColor": "#14b8a6",
			"fillOpacity": 0.04,
		},
	},
	{
		"id": "countries_50m",
		"source": "ne_50m_admin_0_countries",
		"label": "Countries (1:50m detail)",
		"category": "cultural",
		"theme": "countries",
		"geometry": "polygon",
		"scale": "50m",
		"name_field": "NAME",
		"default_visible": False,
		"description": "Higher-detail country boundaries for regional and national maps.",
		"style": {
			"color": "#0f766e",
			"weight": 1.1,
			"opacity": 0.8,
			"fillColor": "#14b8a6",
			"fillOpacity": 0.04,
		},
	},
	{
		"id": "admin1_110m",
		"source": "ne_110m_admin_1_states_provinces",
		"label": "States / provinces (1:110m)",
		"category": "cultural",
		"theme": "administrative",
		"geometry": "polygon",
		"scale": "110m",
		"name_field": "name",
		"default_visible": False,
		"description": "First-level administrative divisions (states and provinces).",
		"style": {
			"color": "#64748b",
			"weight": 0.7,
			"opacity": 0.7,
			"fillColor": "#94a3b8",
			"fillOpacity": 0.02,
			"dashArray": "2 3",
		},
	},
	{
		"id": "boundary_lines_110m",
		"source": "ne_110m_admin_0_boundary_lines_land",
		"label": "Country boundary lines (1:110m)",
		"category": "cultural",
		"theme": "boundaries",
		"geometry": "line",
		"scale": "110m",
		"name_field": "name",
		"default_visible": False,
		"description": "Land boundary lines between countries.",
		"style": {"color": "#475569", "weight": 1.1, "opacity": 0.8, "dashArray": "4 3"},
	},
	{
		"id": "disputed_boundaries_50m",
		"source": "ne_50m_admin_0_boundary_lines_disputed_areas",
		"label": "Disputed boundary lines (1:50m)",
		"category": "cultural",
		"theme": "boundaries",
		"geometry": "line",
		"scale": "50m",
		"name_field": "name",
		"default_visible": False,
		"description": "Boundary lines in disputed areas; alternative political representations.",
		"style": {"color": "#dc2626", "weight": 1.2, "opacity": 0.85, "dashArray": "2 3"},
	},
	{
		"id": "disputed_areas_50m",
		"source": "ne_50m_admin_0_breakaway_disputed_areas",
		"label": "Disputed / breakaway areas (1:50m)",
		"category": "cultural",
		"theme": "boundaries",
		"geometry": "polygon",
		"scale": "50m",
		"name_field": "name",
		"default_visible": False,
		"description": "Breakaway and disputed territories polygons.",
		"style": {
			"color": "#dc2626",
			"weight": 1,
			"opacity": 0.8,
			"fillColor": "#fca5a5",
			"fillOpacity": 0.12,
		},
	},
	{
		"id": "populated_places_110m",
		"source": "ne_110m_populated_places",
		"label": "Cities & populated places (1:110m)",
		"category": "cultural",
		"theme": "places",
		"geometry": "point",
		"scale": "110m",
		"name_field": "NAME",
		"default_visible": False,
		"description": "Major cities and populated places with population estimates and admin context.",
		"style": {
			"radius": 3.5,
			"color": "#1d4ed8",
			"weight": 1,
			"fillColor": "#3b82f6",
			"fillOpacity": 0.85,
		},
	},
	{
		"id": "airports_10m",
		"source": "ne_10m_airports",
		"label": "Airports (1:10m)",
		"category": "cultural",
		"theme": "transport",
		"geometry": "point",
		"scale": "10m",
		"name_field": "name",
		"default_visible": False,
		"description": "Major airports (point locations).",
		"style": {"radius": 3.5, "color": "#7c3aed", "weight": 1, "fillColor": "#a78bfa", "fillOpacity": 0.9},
	},
	{
		"id": "ports_10m",
		"source": "ne_10m_ports",
		"label": "Ports (1:10m)",
		"category": "cultural",
		"theme": "transport",
		"geometry": "point",
		"scale": "10m",
		"name_field": "name",
		"default_visible": False,
		"description": "Major seaports (point locations).",
		"style": {"radius": 3.5, "color": "#0891b2", "weight": 1, "fillColor": "#22d3ee", "fillOpacity": 0.9},
	},
	{
		"id": "land_110m",
		"source": "ne_110m_land",
		"label": "Land (1:110m)",
		"category": "physical",
		"theme": "land",
		"geometry": "polygon",
		"scale": "110m",
		"name_field": "featurecla",
		"default_visible": False,
		"description": "Global land mass polygons.",
		"style": {
			"color": "#d6d3d1",
			"weight": 0.5,
			"opacity": 0.6,
			"fillColor": "#f5f5f4",
			"fillOpacity": 0.5,
		},
	},
	{
		"id": "ocean_110m",
		"source": "ne_110m_ocean",
		"label": "Ocean (1:110m)",
		"category": "physical",
		"theme": "water",
		"geometry": "polygon",
		"scale": "110m",
		"name_field": "featurecla",
		"default_visible": False,
		"description": "Global ocean polygons.",
		"style": {
			"color": "#bfdbfe",
			"weight": 0.5,
			"opacity": 0.6,
			"fillColor": "#dbeafe",
			"fillOpacity": 0.5,
		},
	},
	{
		"id": "coastline_110m",
		"source": "ne_110m_coastline",
		"label": "Coastline (1:110m)",
		"category": "physical",
		"theme": "water",
		"geometry": "line",
		"scale": "110m",
		"name_field": "featurecla",
		"default_visible": False,
		"description": "Global coastline lines.",
		"style": {"color": "#0ea5e9", "weight": 1.2, "opacity": 0.85},
	},
	{
		"id": "rivers_110m",
		"source": "ne_110m_rivers_lake_centerlines",
		"label": "Rivers (1:110m)",
		"category": "physical",
		"theme": "water",
		"geometry": "line",
		"scale": "110m",
		"name_field": "name",
		"default_visible": False,
		"description": "Major river and lake centerlines.",
		"style": {"color": "#38bdf8", "weight": 1.3, "opacity": 0.85},
	},
	{
		"id": "lakes_110m",
		"source": "ne_110m_lakes",
		"label": "Lakes (1:110m)",
		"category": "physical",
		"theme": "water",
		"geometry": "polygon",
		"scale": "110m",
		"name_field": "name",
		"default_visible": False,
		"description": "Major lake polygons.",
		"style": {
			"color": "#7dd3fc",
			"weight": 0.8,
			"opacity": 0.8,
			"fillColor": "#bae6fd",
			"fillOpacity": 0.6,
		},
	},
	{
		"id": "glaciated_110m",
		"source": "ne_110m_glaciated_areas",
		"label": "Glaciated areas (1:110m)",
		"category": "physical",
		"theme": "land",
		"geometry": "polygon",
		"scale": "110m",
		"name_field": "featurecla",
		"default_visible": False,
		"description": "Glaciated area polygons (ice sheets).",
		"style": {
			"color": "#e0f2fe",
			"weight": 0.6,
			"opacity": 0.7,
			"fillColor": "#f0f9ff",
			"fillOpacity": 0.7,
		},
	},
	{
		"id": "physical_points_110m",
		"source": "ne_110m_geography_regions_points",
		"label": "Physical features (1:110m)",
		"category": "physical",
		"theme": "land",
		"geometry": "point",
		"scale": "110m",
		"name_field": "name",
		"default_visible": False,
		"description": "Named physical points such as mountain peaks and passes.",
		"style": {"radius": 3.5, "color": "#92400e", "weight": 1, "fillColor": "#d97706", "fillOpacity": 0.9},
	},
	{
		"id": "marine_polys_110m",
		"source": "ne_110m_geography_marine_polys",
		"label": "Seas & oceans (named, 1:110m)",
		"category": "physical",
		"theme": "water",
		"geometry": "polygon",
		"scale": "110m",
		"name_field": "name",
		"default_visible": False,
		"description": "Named marine regions (seas, gulfs, oceans).",
		"style": {
			"color": "#93c5fd",
			"weight": 0.5,
			"opacity": 0.5,
			"fillColor": "#eff6ff",
			"fillOpacity": 0.25,
		},
	},
	{
		"id": "graticules_20",
		"source": "ne_110m_graticules_20",
		"label": "Graticule (20°)",
		"category": "physical",
		"theme": "grid",
		"geometry": "line",
		"scale": "110m",
		"name_field": "degrees",
		"default_visible": False,
		"description": "Latitude/longitude graticule grid at 20-degree spacing.",
		"style": {"color": "#94a3b8", "weight": 0.5, "opacity": 0.5, "dashArray": "1 4"},
	},
]


def _get_json(url: str) -> dict:
	request = urllib.request.Request(
		url, headers={"User-Agent": "cam-natural-earth-builder", "Accept": "application/vnd.github+json"}
	)
	with urllib.request.urlopen(request, timeout=120) as response:
		return json.loads(response.read().decode("utf-8"))


def _positions(value):
	if isinstance(value, list) and len(value) >= 2 and all(isinstance(v, int | float) for v in value[:2]):
		yield value[0], value[1]
	elif isinstance(value, list):
		for child in value:
			yield from _positions(child)


def _bounds(features: list) -> list:
	lons, lats = [], []
	for feature in features:
		geometry = feature.get("geometry") or {}
		for lon, lat in _positions(geometry.get("coordinates")):
			lons.append(lon)
			lats.append(lat)
	if not lons:
		return [-180, -90, 180, 90]
	return [min(lons), min(lats), max(lons), max(lats)]


def main() -> None:
	OUT_DIR.mkdir(parents=True, exist_ok=True)
	tree = _get_json(f"{API}/git/trees/{REVISION}?recursive=1")
	sha_by_path = {item["path"]: item["sha"] for item in tree.get("tree", [])}
	layers = []
	for spec in LAYERS:
		path = f"geojson/{spec['source']}.geojson"
		blob = _get_json(f"{API}/git/blobs/{sha_by_path[path]}")
		raw = base64.b64decode(blob["content"])
		payload = json.loads(raw.decode("utf-8"))
		features = payload.get("features") or []
		file_name = f"{spec['id']}.geojson"
		compact = json.dumps(
			{"type": "FeatureCollection", "features": features},
			ensure_ascii=False,
			separators=(",", ":"),
			allow_nan=False,
		)
		(OUT_DIR / file_name).write_text(compact, encoding="utf-8")
		geometry_types = sorted(
			{(f.get("geometry") or {}).get("type") for f in features if f.get("geometry")}
		)
		layers.append(
			{
				**{
					k: spec[k]
					for k in (
						"id",
						"label",
						"category",
						"theme",
						"geometry",
						"scale",
						"name_field",
						"default_visible",
						"description",
						"style",
					)
				},
				"source_name": spec["source"],
				"file": file_name,
				"source": f"{SOURCE_BASE}/{spec['source']}.geojson",
				"feature_count": len(features),
				"geometry_types": geometry_types,
				"bounds": _bounds(features),
				"sha256": hashlib.sha256(compact.encode("utf-8")).hexdigest(),
			}
		)
		print(f"  {spec['id']:28s} {len(features):5d} features  {len(compact)/1024:8.1f} KB")

	catalog = {
		"catalog_version": 1,
		"dataset_id": "natural-earth-vector-bundle",
		"label": "Natural Earth Vector — bundled geographic layers",
		"revision": REVISION,
		"source_repo": f"https://github.com/{REPO}",
		"license": LICENSE,
		"attribution": ATTRIBUTION,
		"limitations": (
			"Generalized small-scale cartographic data. Not cadastral, not legal boundaries, not live. "
			"Roads and railways are not bundled (their 1:10m source files are tens of megabytes). "
			"Population and GDP figures are Natural Earth estimates, not a live statistical database."
		),
		"layers": layers,
		"summary": {
			"layers": len(layers),
			"cultural": sum(1 for layer in layers if layer["category"] == "cultural"),
			"physical": sum(1 for layer in layers if layer["category"] == "physical"),
			"point": sum(1 for layer in layers if layer["geometry"] == "point"),
			"line": sum(1 for layer in layers if layer["geometry"] == "line"),
			"polygon": sum(1 for layer in layers if layer["geometry"] == "polygon"),
			"scales": sorted({layer["scale"] for layer in layers}),
			"features": sum(layer["feature_count"] for layer in layers),
		},
	}
	(OUT_DIR / "catalog.json").write_text(
		json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
	)
	print(f"Wrote {len(layers)} layers; total features {catalog['summary']['features']}")


if __name__ == "__main__":
	main()
