"""Explicitly opt-in Nominatim fallback; no caller-controlled host or URL."""

from __future__ import annotations

import json
import time

import frappe

NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"


def reverse_lookup(latitude: float, longitude: float) -> dict | None:
	settings = frappe.get_single("CAM Geo Settings")
	if not settings.enable_online_geocoder or settings.online_provider != "Nominatim (OpenStreetMap)":
		return None
	user_agent = (settings.online_user_agent or "").strip()
	if not user_agent:
		frappe.throw(
			"External geocoding is enabled without a contact-bearing User-Agent.", frappe.ValidationError
		)

	cache_key = f"cam:geo:nominatim:{latitude:.5f}:{longitude:.5f}"
	cached = frappe.cache().get_value(cache_key)
	if cached:
		try:
			return json.loads(cached)
		except (TypeError, json.JSONDecodeError):
			pass

	# Enforce both the administrator's per-minute cap and Nominatim's
	# one-request-per-second policy across all workers with Redis primitives.
	redis = frappe.cache()
	minute = int(time.time() // 60)
	minute_key = redis.make_key(f"cam:geo:nominatim:minute:{minute}")
	request_count = redis.incr(minute_key)
	if request_count == 1:
		redis.expire(minute_key, 61)
	if request_count > int(settings.online_rate_limit_per_min or 30):
		frappe.throw("External geocoder per-minute limit reached.", frappe.TooManyRequestsError)
	gap_key = redis.make_key("cam:geo:nominatim:last-request")
	if not redis.set(gap_key, str(time.time()), nx=True, ex=1):
		frappe.throw("External geocoder is rate limited; retry shortly.", frappe.TooManyRequestsError)

	try:
		import requests

		response = requests.get(
			NOMINATIM_REVERSE_URL,
			params={
				"format": "jsonv2",
				"lat": latitude,
				"lon": longitude,
				"zoom": 18,
				"addressdetails": 1,
			},
			headers={"User-Agent": user_agent, "Accept-Language": "en"},
			timeout=(3.05, 8),
			allow_redirects=False,
		)
		response.raise_for_status()
		payload = response.json()
		result = {
			"provider": "Nominatim (OpenStreetMap)",
			"display_name": str(payload.get("display_name") or "")[:1000],
			"address": payload.get("address") if isinstance(payload.get("address"), dict) else {},
			"provenance": "external_provider",
			"confidence": 0.5,
			"ambiguous": not bool(payload.get("display_name")) or not bool(payload.get("address")),
		}
		frappe.cache().set_value(cache_key, json.dumps(result), expires_in_sec=86400)
		return result
	except Exception as exc:
		frappe.logger("camera_archive_management.geo").warning(
			"External reverse-geocoding failed: %s", str(exc)[:250]
		)
		return None
