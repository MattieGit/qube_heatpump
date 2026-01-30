"""Tests for strings.json validation."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


# Allowed abbreviations and proper nouns that can be capitalized
ALLOWED_CAPITALS = {
    # Abbreviations
    "DHW",  # Domestic Hot Water
    "CV",  # Central Heating (Dutch: Centrale Verwarming)
    "SCOP",  # Seasonal Coefficient of Performance
    "COP",  # Coefficient of Performance
    "PV",  # Photovoltaic
    "SG",  # Smart Grid
    "IP",  # Internet Protocol
    "DSMR",  # Dutch Smart Meter Requirements
    "Wi-Fi",  # Wireless Fidelity
    "SSID",  # Service Set Identifier
    "RSSI",  # Received Signal Strength Indicator
    "dT",  # Delta Temperature
    # Proper nouns/brands
    "Qube",
    "Ready",  # Part of "SG Ready" standard
    "Linq",  # Qube Linq product name
    "Modbus",
    # Technical terms that are commonly capitalized
    "Anti-legionella",
    # Category prefixes (word before colon in "Category: description" format)
    "Alarm",
    "Max",  # Used in alarm descriptions
}

# Words that should remain capitalized when they appear
CAPITAL_WORDS_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(word) for word in ALLOWED_CAPITALS) + r")\b",
    re.IGNORECASE,
)


def _is_sentence_case(text: str) -> bool:
    """Check if text follows sentence case rules.

    Sentence case: First letter capitalized, rest lowercase,
    except for allowed abbreviations/proper nouns.

    Special handling:
    - After a colon, the next word can be capitalized (new phrase)
    - Words in parentheses follow the same rules
    """
    if not text:
        return True

    # Split by colon to handle "Category: Description" format
    # Each part after colon can start with capital
    parts = text.split(":")

    for part_idx, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue

        # Split into words
        words = part.split()
        if not words:
            continue

        for i, word in enumerate(words):
            # Remove punctuation for checking (but keep hyphens)
            clean_word = re.sub(r"[^\w-]", "", word)
            if not clean_word:
                continue

            # Check if this word (or part of it) is an allowed capital
            is_allowed = False
            for allowed in ALLOWED_CAPITALS:
                if allowed.lower() == clean_word.lower():
                    is_allowed = True
                    break
                # Also check if the word contains the allowed abbreviation
                if allowed.lower() in clean_word.lower():
                    is_allowed = True
                    break

            if is_allowed:
                continue

            # First word of each part (after colon) can be capitalized
            if i == 0:
                if clean_word and not clean_word[0].isupper():
                    # Exception for technical terms like "dT"
                    if clean_word.lower() not in [a.lower() for a in ALLOWED_CAPITALS]:
                        return False
                continue

            # Subsequent words should be lowercase (unless all caps = abbreviation)
            if clean_word[0].isupper():
                # If it's all caps, it's an abbreviation
                if clean_word.upper() == clean_word:
                    continue
                # Otherwise it's Title Case - not allowed
                return False

    return True


def _get_all_names(data: dict, path: str = "") -> list[tuple[str, str]]:
    """Recursively get all 'name' values from a dict."""
    names = []
    for key, value in data.items():
        current_path = f"{path}.{key}" if path else key
        if key == "name" and isinstance(value, str):
            names.append((current_path, value))
        elif isinstance(value, dict):
            names.extend(_get_all_names(value, current_path))
    return names


class TestStringsCapitalization:
    """Tests for proper capitalization in strings.json."""

    @pytest.fixture
    def strings_data(self) -> dict:
        """Load strings.json data."""
        strings_path = (
            Path(__file__).parent.parent
            / "custom_components"
            / "qube_heatpump"
            / "strings.json"
        )
        with open(strings_path, encoding="utf-8") as f:
            return json.load(f)

    def test_entity_names_use_sentence_case(self, strings_data: dict) -> None:
        """Test that all entity names use sentence case."""
        entity_section = strings_data.get("entity", {})
        names = _get_all_names(entity_section)

        violations = []
        for path, name in names:
            if not _is_sentence_case(name):
                violations.append(f"{path}: '{name}'")

        if violations:
            pytest.fail(
                f"Entity names should use sentence case. Violations:\n"
                + "\n".join(f"  - {v}" for v in violations)
            )

    def test_config_titles_use_sentence_case(self, strings_data: dict) -> None:
        """Test that config flow titles use sentence case."""
        config_section = strings_data.get("config", {})

        violations = []
        # Check step titles
        steps = config_section.get("step", {})
        for step_name, step_data in steps.items():
            if "title" in step_data:
                title = step_data["title"]
                if not _is_sentence_case(title):
                    violations.append(f"config.step.{step_name}.title: '{title}'")

        if violations:
            pytest.fail(
                f"Config titles should use sentence case. Violations:\n"
                + "\n".join(f"  - {v}" for v in violations)
            )

    def test_no_title_case_in_names(self, strings_data: dict) -> None:
        """Test that names don't use Title Case (except allowed words).

        Note: After a colon, capitalization resets (new phrase).
        """
        entity_section = strings_data.get("entity", {})
        names = _get_all_names(entity_section)

        # Pattern to find Title Case: multiple capitalized words in sequence
        # that are not in the allowed list
        title_case_violations = []

        for path, name in names:
            # Split by colon - each part is evaluated separately
            parts = name.split(":")

            for part in parts:
                part = part.strip()
                words = part.split()
                consecutive_caps = 0

                for i, word in enumerate(words):
                    clean_word = re.sub(r"[^\w-]", "", word)
                    if not clean_word:
                        continue

                    # First word of each part can be capitalized
                    if i == 0:
                        consecutive_caps = 0
                        continue

                    # Check if word starts with capital and is not allowed
                    is_allowed = any(
                        allowed.lower() in clean_word.lower()
                        for allowed in ALLOWED_CAPITALS
                    )

                    # All-caps words are abbreviations
                    if clean_word.upper() == clean_word:
                        is_allowed = True

                    if clean_word[0].isupper() and not is_allowed:
                        consecutive_caps += 1
                    else:
                        consecutive_caps = 0

                    if consecutive_caps >= 2:
                        title_case_violations.append(f"{path}: '{name}'")
                        break

        if title_case_violations:
            pytest.fail(
                f"Names should not use Title Case. Violations:\n"
                + "\n".join(f"  - {v}" for v in title_case_violations)
            )


class TestStringsStructure:
    """Tests for strings.json structure."""

    @pytest.fixture
    def strings_data(self) -> dict:
        """Load strings.json data."""
        strings_path = (
            Path(__file__).parent.parent
            / "custom_components"
            / "qube_heatpump"
            / "strings.json"
        )
        with open(strings_path, encoding="utf-8") as f:
            return json.load(f)

    def test_has_config_section(self, strings_data: dict) -> None:
        """Test that strings.json has a config section."""
        assert "config" in strings_data

    def test_has_entity_section(self, strings_data: dict) -> None:
        """Test that strings.json has an entity section."""
        assert "entity" in strings_data

    def test_has_exceptions_section(self, strings_data: dict) -> None:
        """Test that strings.json has an exceptions section."""
        assert "exceptions" in strings_data
        exceptions = strings_data["exceptions"]
        assert len(exceptions) > 0

        # Each exception should have a message
        for key, value in exceptions.items():
            assert "message" in value, f"Exception '{key}' missing 'message'"

    def test_exception_messages_are_sentences(self, strings_data: dict) -> None:
        """Test that exception messages are proper sentences."""
        exceptions = strings_data.get("exceptions", {})

        for key, value in exceptions.items():
            message = value.get("message", "")
            # Should start with capital letter
            assert message[0].isupper(), (
                f"Exception '{key}' message should start with capital: '{message}'"
            )
            # Should end with period
            assert message.endswith("."), (
                f"Exception '{key}' message should end with period: '{message}'"
            )

    def test_valid_json_structure(self, strings_data: dict) -> None:
        """Test that strings.json has valid structure."""
        # Check required top-level sections
        required_sections = ["config", "entity"]
        for section in required_sections:
            assert section in strings_data, f"Missing required section: {section}"

        # Check entity section has expected platforms
        entity = strings_data.get("entity", {})
        expected_platforms = ["sensor", "binary_sensor", "switch"]
        for platform in expected_platforms:
            assert platform in entity, f"Missing entity platform: {platform}"


class TestSentenceCaseHelper:
    """Tests for the sentence case helper function."""

    def test_simple_sentence_case(self) -> None:
        """Test simple sentence case strings."""
        assert _is_sentence_case("Power usage") is True
        assert _is_sentence_case("Water usage") is True
        assert _is_sentence_case("Status code") is True

    def test_title_case_rejected(self) -> None:
        """Test that Title Case is rejected."""
        assert _is_sentence_case("Power Usage") is False
        assert _is_sentence_case("Water Flow") is False
        assert _is_sentence_case("Measured Value") is False
        assert _is_sentence_case("Some Random Title Case") is False

    def test_abbreviations_allowed(self) -> None:
        """Test that abbreviations are allowed."""
        assert _is_sentence_case("DHW temperature") is True
        assert _is_sentence_case("CV setpoint") is True
        assert _is_sentence_case("SCOP (month)") is True
        assert _is_sentence_case("SG Ready mode") is True
        assert _is_sentence_case("PV surplus active") is True

    def test_brand_names_allowed(self) -> None:
        """Test that brand names are allowed."""
        assert _is_sentence_case("Qube info") is True
        assert _is_sentence_case("Qube IP address") is True
        assert _is_sentence_case("Linq room temperature") is True

    def test_mixed_content(self) -> None:
        """Test mixed content with abbreviations."""
        assert _is_sentence_case("Electric consumption DHW (month)") is True
        assert _is_sentence_case("Thermic yield CH (day)") is True
        assert _is_sentence_case("Anti-legionella enabled") is True
