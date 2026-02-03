"""Tests for the Qube Heat Pump helper utilities."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from custom_components.qube_heatpump.helpers import (
    derive_label_from_title,
    slugify,
    suggest_object_id,
)


class TestSlugify:
    """Tests for the slugify function."""

    def test_simple_text(self) -> None:
        """Test slugify with simple text."""
        assert slugify("hello") == "hello"
        assert slugify("Hello") == "hello"
        assert slugify("HELLO") == "hello"

    def test_text_with_spaces(self) -> None:
        """Test slugify with spaces."""
        assert slugify("hello world") == "hello_world"
        assert slugify("Hello World") == "hello_world"

    def test_text_with_special_characters(self) -> None:
        """Test slugify with special characters."""
        assert slugify("hello-world") == "hello_world"
        assert slugify("hello.world") == "hello_world"
        assert slugify("hello/world") == "hello_world"
        assert slugify("hello@world") == "hello_world"

    def test_text_with_numbers(self) -> None:
        """Test slugify with numbers."""
        assert slugify("sensor123") == "sensor123"
        assert slugify("123sensor") == "123sensor"
        assert slugify("sensor_123") == "sensor_123"

    def test_ip_address(self) -> None:
        """Test slugify with IP address."""
        assert slugify("192.168.1.50") == "192_168_1_50"

    def test_strips_leading_trailing_underscores(self) -> None:
        """Test that leading/trailing underscores are stripped."""
        assert slugify("_hello_") == "hello"
        assert slugify("__hello__") == "hello"
        assert slugify("-hello-") == "hello"
        assert slugify("  hello  ") == "hello"

    def test_empty_string(self) -> None:
        """Test slugify with empty string."""
        assert slugify("") == ""

    def test_only_special_characters(self) -> None:
        """Test slugify with only special characters."""
        assert slugify("---") == ""
        assert slugify("...") == ""
        assert slugify("@#$") == ""

    def test_unicode_characters(self) -> None:
        """Test slugify with unicode characters."""
        # Unicode letters are alphanumeric
        assert slugify("héllo") == "héllo"
        assert slugify("Müller") == "müller"

    def test_mixed_content(self) -> None:
        """Test slugify with mixed content."""
        assert slugify("Qube Heat Pump (192.168.1.50)") == "qube_heat_pump__192_168_1_50"


class TestSuggestObjectId:
    """Tests for the suggest_object_id function."""

    @dataclass
    class MockEntityDef:
        """Mock entity definition for testing."""

        vendor_id: str | None = None

    def test_with_vendor_id(self) -> None:
        """Test suggest_object_id with vendor_id."""
        ent = self.MockEntityDef(vendor_id="temp_supply")
        assert suggest_object_id(ent, "qube") == "qube_temp_supply"

    def test_with_different_label(self) -> None:
        """Test suggest_object_id with different labels."""
        ent = self.MockEntityDef(vendor_id="cop_calc")
        assert suggest_object_id(ent, "qube1") == "qube1_cop_calc"
        assert suggest_object_id(ent, "qube_basement") == "qube_basement_cop_calc"

    def test_without_vendor_id(self) -> None:
        """Test suggest_object_id returns None without vendor_id."""
        ent = self.MockEntityDef(vendor_id=None)
        assert suggest_object_id(ent, "qube") is None

    def test_with_empty_vendor_id(self) -> None:
        """Test suggest_object_id returns None with empty vendor_id."""
        ent = self.MockEntityDef(vendor_id="")
        assert suggest_object_id(ent, "qube") is None

    def test_vendor_id_with_special_characters(self) -> None:
        """Test suggest_object_id slugifies special characters."""
        ent = self.MockEntityDef(vendor_id="temp-supply.value")
        assert suggest_object_id(ent, "qube") == "qube_temp_supply_value"

    def test_missing_vendor_id_attribute(self) -> None:
        """Test suggest_object_id with object missing vendor_id attribute."""

        class NoVendorId:
            pass

        ent = NoVendorId()
        assert suggest_object_id(ent, "qube") is None  # type: ignore[arg-type]


class TestDeriveLabelFromTitle:
    """Tests for the derive_label_from_title function."""

    def test_title_with_parentheses_ip(self) -> None:
        """Test derive_label_from_title with IP in parentheses."""
        title = "Qube Heat Pump (192.168.1.50)"
        assert derive_label_from_title(title) == "192_168_1_50"

    def test_title_with_parentheses_hostname(self) -> None:
        """Test derive_label_from_title with hostname in parentheses."""
        title = "Qube Heat Pump (qube-basement)"
        assert derive_label_from_title(title) == "qube_basement"

    def test_title_with_parentheses_custom_name(self) -> None:
        """Test derive_label_from_title with custom name in parentheses."""
        title = "My Heatpump (Living Room)"
        assert derive_label_from_title(title) == "living_room"

    def test_title_without_parentheses(self) -> None:
        """Test derive_label_from_title without parentheses."""
        title = "Qube Heat Pump"
        assert derive_label_from_title(title) == "qube_heat_pump"

    def test_title_simple_name(self) -> None:
        """Test derive_label_from_title with simple name."""
        title = "Basement"
        assert derive_label_from_title(title) == "basement"

    def test_title_empty_parentheses(self) -> None:
        """Test derive_label_from_title with empty parentheses falls back to title."""
        # Empty parentheses don't match regex [^)]+ (requires at least one char)
        title = "Qube Heat Pump ()"
        assert derive_label_from_title(title) == "qube_heat_pump"

    def test_title_empty_string(self) -> None:
        """Test derive_label_from_title with empty string falls back to qube1."""
        title = ""
        assert derive_label_from_title(title) == "qube1"

    def test_title_only_special_chars(self) -> None:
        """Test derive_label_from_title with only special chars falls back to qube1."""
        title = "---"
        assert derive_label_from_title(title) == "qube1"

    def test_multiple_parentheses(self) -> None:
        """Test derive_label_from_title with multiple parentheses uses first."""
        title = "Qube (first) Heat Pump (second)"
        # re.search finds first match
        assert derive_label_from_title(title) == "first"

    def test_nested_parentheses(self) -> None:
        """Test derive_label_from_title with nested parentheses."""
        title = "Qube Heat Pump (192.168.1.50 (main))"
        # Regex [^)]+ is non-greedy and stops at first )
        assert derive_label_from_title(title) == "192_168_1_50__main"
