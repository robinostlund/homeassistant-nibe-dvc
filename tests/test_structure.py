"""Structural checks on the integration's metadata.

These need no Home Assistant instance -- they guard the kind of mistake that
silently degrades the UI rather than raising, such as an entity translation key
with no matching string (the entity then falls back to its device class name).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

COMPONENT = Path(__file__).parent.parent / "custom_components" / "ecovent"


def _load(name: str) -> dict:
    return json.loads((COMPONENT / name).read_text())


def test_translations_match_strings() -> None:
    """translations/en.json must stay in sync with strings.json.

    Home Assistant reads translations/ at runtime; strings.json is only the
    source. Editing one and not the other loses entity names silently.
    """
    assert _load("strings.json") == _load("translations/en.json")


def test_manifest_required_keys() -> None:
    """The manifest carries everything HACS and hassfest require."""
    manifest = _load("manifest.json")

    for key in (
        "domain",
        "name",
        "codeowners",
        "config_flow",
        "documentation",
        "iot_class",
        "issue_tracker",
        "requirements",
        "version",
    ):
        assert key in manifest, f"manifest.json is missing {key}"

    assert manifest["domain"] == "ecovent"
    assert manifest["config_flow"] is True
    # The protocol client ships with the integration; no external packages.
    assert manifest["requirements"] == []


@pytest.mark.parametrize(
    ("platform", "key"),
    [
        ("fan", "ecovent"),
        ("binary_sensor", "alarm"),
        ("binary_sensor", "boost_mode"),
        ("binary_sensor", "filter"),
    ],
)
def test_entity_translation_keys_exist(platform: str, key: str) -> None:
    """Every translation_key used by an entity has a strings.json entry."""
    entities = _load("strings.json")["entity"]

    assert platform in entities, f"no strings for platform {platform}"
    assert key in entities[platform], f"no strings for {platform}.{key}"


def test_no_services_yaml() -> None:
    """Airflow is a fan preset mode, so the integration registers no services."""
    assert not (COMPONENT / "services.yaml").exists()
    assert "services" not in _load("strings.json")


# RFC 1918 private ranges. A real LAN address committed to a public repo leaks
# the maintainer's network layout, so tests must use the RFC 5737
# documentation range (192.0.2.0/24) and live tests must read the host from
# ECOVENT_TEST_HOST instead.
PRIVATE_IP = re.compile(
    r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b"
)

REPO = Path(__file__).parent.parent


@pytest.mark.parametrize(
    "path",
    sorted(
        [*(REPO / "tests").rglob("*.py"), *COMPONENT.rglob("*.py"), REPO / "README.md"]
    ),
    ids=lambda p: str(p.relative_to(REPO)),
)
def test_no_private_ip_addresses(path: Path) -> None:
    """No real LAN address is committed anywhere."""
    found = PRIVATE_IP.findall(path.read_text())

    assert not found, (
        f"{path.relative_to(REPO)} contains private IP address(es) {found}. "
        "Use the RFC 5737 documentation range (192.0.2.x) instead."
    )
