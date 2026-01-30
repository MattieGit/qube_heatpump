"""Tests for the Qube Heat Pump modbus_probe utility."""

from __future__ import annotations

import pytest

from custom_components.qube_heatpump.modbus_probe import _decode_registers


class TestDecodeRegisters:
    """Tests for the _decode_registers function."""

    def test_decode_uint16(self) -> None:
        """Test decoding uint16 value."""
        result = _decode_registers([1234], "uint16", "big", "big")
        assert result == 1234

    def test_decode_uint16_max(self) -> None:
        """Test decoding max uint16 value."""
        result = _decode_registers([65535], "uint16", "big", "big")
        assert result == 65535

    def test_decode_int16_positive(self) -> None:
        """Test decoding positive int16 value."""
        result = _decode_registers([1000], "int16", "big", "big")
        assert result == 1000

    def test_decode_int16_negative(self) -> None:
        """Test decoding negative int16 value (two's complement)."""
        # -1 in two's complement = 0xFFFF = 65535
        result = _decode_registers([65535], "int16", "big", "big")
        assert result == -1

    def test_decode_int16_min(self) -> None:
        """Test decoding minimum int16 value."""
        # -32768 in two's complement = 0x8000 = 32768
        result = _decode_registers([32768], "int16", "big", "big")
        assert result == -32768

    def test_decode_float32_big_endian(self) -> None:
        """Test decoding float32 with big endian byte order."""
        # 42.0 in IEEE 754 big endian = 0x42280000
        result = _decode_registers([0x4228, 0x0000], "float32", "big", "big")
        assert abs(result - 42.0) < 0.001

    def test_decode_float32_little_word_order(self) -> None:
        """Test decoding float32 with little word order."""
        # 42.0 in IEEE 754 with swapped words
        result = _decode_registers([0x0000, 0x4228], "float32", "big", "little")
        assert abs(result - 42.0) < 0.001

    def test_decode_uint32_big_endian(self) -> None:
        """Test decoding uint32 with big endian."""
        # 0x00010002 = 65538
        result = _decode_registers([0x0001, 0x0002], "uint32", "big", "big")
        assert result == 65538

    def test_decode_uint32_little_word_order(self) -> None:
        """Test decoding uint32 with little word order."""
        # Words swapped: [0x0002, 0x0001] -> 0x00010002 = 65538
        result = _decode_registers([0x0002, 0x0001], "uint32", "big", "little")
        assert result == 65538

    def test_decode_int32_positive(self) -> None:
        """Test decoding positive int32 value."""
        result = _decode_registers([0x0000, 0x1000], "int32", "big", "big")
        assert result == 4096

    def test_decode_int32_negative(self) -> None:
        """Test decoding negative int32 value."""
        # -1 in two's complement = 0xFFFFFFFF
        result = _decode_registers([0xFFFF, 0xFFFF], "int32", "big", "big")
        assert result == -1

    def test_decode_requires_two_registers_for_32bit(self) -> None:
        """Test that 32-bit types require two registers."""
        with pytest.raises(ValueError, match="Need 2 registers"):
            _decode_registers([0x0001], "float32", "big", "big")

        with pytest.raises(ValueError, match="Need 2 registers"):
            _decode_registers([0x0001], "uint32", "big", "big")

        with pytest.raises(ValueError, match="Need 2 registers"):
            _decode_registers([0x0001], "int32", "big", "big")

    def test_decode_unknown_type_returns_raw(self) -> None:
        """Test that unknown types return raw 16-bit value."""
        result = _decode_registers([1234], "unknown", "big", "big")
        assert result == 1234

    def test_decode_handles_masked_values(self) -> None:
        """Test that values are properly masked to 16-bit."""
        # Even if a value is passed that's larger, it should be masked
        result = _decode_registers([0x1FFFF], "uint16", "big", "big")
        assert result == 0xFFFF
