"""Tests for the Qube Heat Pump helper utilities."""

from __future__ import annotations

from custom_components.qube_heatpump.helpers import slugify


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
