"""Workspace contract tests: links, live widgets, and native Frappe onboarding.

These pure-Python checks make the app workspace a tested deliverable without
requiring a running Bench site or database, and mirror the static integrity
checks used by Siraj-Research for its native Workspace content.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "camera_archive_management"
WORKSPACE_PATH = APP / "workspace" / "camera_archive_management" / "camera_archive_management.json"
ONBOARDING_NAME = "Camera Archive Management Setup"


def _json(path: Path) -> dict:
	return json.loads(path.read_text(encoding="utf-8"))


def _content(workspace: dict) -> list[dict]:
	content = workspace.get("content") or []
	return json.loads(content) if isinstance(content, str) else content


def _records(kind: str) -> dict[str, dict]:
	records = {}
	for path in (APP / kind).glob("*/*.json"):
		data = _json(path)
		if data.get("name"):
			records[data["name"]] = data
	return records


def _doctypes() -> dict[str, dict]:
	return {
		data["name"]: data
		for path in (APP / "doctype").glob("*/*.json")
		if (data := _json(path)).get("doctype") == "DocType" and data.get("name")
	}


def _every_app_doctype_is_discoverable():
	workspace = _json(WORKSPACE_PATH)
	linked = {
		row.get("link_to")
		for row in workspace.get("links", [])
		if row.get("type") == "Link" and row.get("link_type") == "DocType"
	}
	missing = sorted(set(_doctypes()) - linked)
	assert not missing, f"DocTypes missing from the workspace: {missing}"


def _workspace_links_are_unique():
	workspace = _json(WORKSPACE_PATH)
	links = [row for row in workspace.get("links", []) if row.get("type") == "Link"]
	keys = [(row.get("link_type"), row.get("link_to")) for row in links]
	assert len(keys) == len(set(keys)), "workspace has duplicate DocType/Page/Report links"


def _workspace_widgets_resolve():
	workspace = _json(WORKSPACE_PATH)
	content = _content(workspace)
	block_ids = [block.get("id") for block in content]
	assert len(block_ids) == len(set(block_ids)), "workspace content block IDs must be unique"
	onboardings = _records("module_onboarding")
	cards = _records("number_card")
	charts = {row["chart_name"] for row in json.loads((ROOT / "fixtures" / "dashboard_chart.json").read_text())}

	blocks = [block for block in content if block.get("type") == "onboarding"]
	assert len(blocks) == 1
	assert blocks[0]["data"]["onboarding_name"] in onboardings
	assert {row["number_card_name"] for row in workspace.get("number_cards", [])} == set(cards)
	assert {row["chart_name"] for row in workspace.get("charts", [])} == charts

	block_cards = {b.get("data", {}).get("number_card_name") for b in content if b.get("type") == "number_card"}
	block_charts = {b.get("data", {}).get("chart_name") for b in content if b.get("type") == "chart"}
	block_shortcuts = {
		b.get("data", {}).get("shortcut_name") for b in content if b.get("type") == "shortcut"
	}
	configured_shortcuts = {row.get("label") for row in workspace.get("shortcuts", [])}
	assert block_cards == set(cards)
	assert block_charts == charts
	assert block_shortcuts == configured_shortcuts


def _onboarding_is_deep_and_valid():
	onboardings = _records("module_onboarding")
	assert set(onboardings) == {ONBOARDING_NAME}
	onboarding = onboardings[ONBOARDING_NAME]
	steps = _records("onboarding_step")
	doctypes = _doctypes()
	reports = {
		data["name"]
		for path in (APP / "report").glob("*/*.json")
		if (data := _json(path)).get("doctype") == "Report"
	}
	rows = onboarding.get("steps", [])
	assert len(rows) >= 16, f"The setup journey is too thin: {len(rows)} steps"
	assert [row.get("idx") for row in rows] == list(range(1, len(rows) + 1))
	assert onboarding.get("allow_roles") and onboarding.get("module")
	assert len({row.get("step") for row in rows}) == len(rows)

	for row in rows:
		step_name = row.get("step")
		assert step_name in steps, f"Missing Onboarding Step record: {step_name!r}"
		step = steps[step_name]
		assert step.get("title") and step.get("description"), step_name
		action = step.get("action")
		assert action in {"Create Entry", "Update Settings", "Show Form Tour", "View Report", "Go to Page", "Watch Video"}
		if action == "Create Entry":
			assert step.get("reference_document") in doctypes, step_name
			assert step.get("show_full_form") == 1, f"{step_name} should expose the full form"
		elif action == "View Report":
			assert step.get("reference_report") in reports, step_name
		elif action == "Go to Page":
			assert step.get("path"), step_name

	# Keep the core end-to-end journey explicit: taxonomy → camera → vehicle → movement → coverage.
	ordered = [row["step"] for row in rows]
	for earlier, later in [
		("Define camera-area taxonomy", "Register a camera"),
		("Register a camera", "Register a vehicle"),
		("Register a vehicle", "Record a vehicle movement event"),
		("Record a vehicle movement event", "Explore camera coverage and the map"),
	]:
		assert ordered.index(earlier) < ordered.index(later)


def _onboarding_data_fields_fit_frappe_limits():
	"""Frappe Data fields default to 140 chars; long guidance belongs in Markdown descriptions."""
	for kind in ("module_onboarding", "onboarding_step", "number_card"):
		for name, record in _records(kind).items():
			for fieldname in (
				"name", "title", "subtitle", "success_message", "documentation_url", "action_label",
				"path", "reference_document", "reference_report", "report_description", "label", "module",
			):
				value = record.get(fieldname)
				if isinstance(value, str):
					assert len(value) <= 140, (
						f"{kind}/{name}.{fieldname} is {len(value)} chars; Frappe Data fields allow 140"
					)


def _number_cards_use_real_fields():
	doctypes = _doctypes()
	cards = _records("number_card")
	assert len(cards) >= 5
	for name, card in cards.items():
		doctype = card["document_type"]
		assert doctype in doctypes, (name, doctype)
		fields = {field["fieldname"] for field in doctypes[doctype].get("fields", [])}
		filters = json.loads(card.get("filters_json") or "[]")
		for filter_row in filters:
			assert len(filter_row) == 4, (name, filter_row)
			assert filter_row[0] == doctype, (name, filter_row)
			assert filter_row[1] in fields, (name, filter_row)
			assert filter_row[2] in {"=", "!=", ">", ">=", "<", "<=", "in", "not in", "like", "not like"}


def _dashboard_charts_use_real_fields():
	doctypes = _doctypes()
	charts = json.loads((ROOT / "fixtures" / "dashboard_chart.json").read_text(encoding="utf-8"))
	assert len(charts) >= 5
	for chart in charts:
		doctype = chart["document_type"]
		assert doctype in doctypes, chart["chart_name"]
		fields = {field["fieldname"] for field in doctypes[doctype].get("fields", [])}
		for fieldname in (chart.get("based_on"), chart.get("group_by_based_on")):
			if fieldname:
				assert fieldname == "creation" or fieldname in fields, (chart["chart_name"], fieldname)


def _workspace_sections_render():
	workspace = _json(WORKSPACE_PATH)
	breaks = {row["label"] for row in workspace.get("links", []) if row.get("type") == "Card Break"}
	cards = {block.get("data", {}).get("card_name") for block in _content(workspace) if block.get("type") == "card"}
	assert breaks == cards


class WorkspaceContractTests(unittest.TestCase):
	"""Run the workspace contract using only the Python standard library."""

	def test_every_app_doctype_is_discoverable(self):
		_every_app_doctype_is_discoverable()

	def test_workspace_links_are_unique(self):
		_workspace_links_are_unique()

	def test_workspace_widgets_resolve(self):
		_workspace_widgets_resolve()

	def test_onboarding_is_deep_and_valid(self):
		_onboarding_is_deep_and_valid()

	def test_onboarding_data_fields_fit_frappe_limits(self):
		_onboarding_data_fields_fit_frappe_limits()

	def test_number_cards_use_real_fields(self):
		_number_cards_use_real_fields()

	def test_dashboard_charts_use_real_fields(self):
		_dashboard_charts_use_real_fields()

	def test_workspace_sections_render(self):
		_workspace_sections_render()
