"""Codec tests on SYNTHETIC fixtures (no real Line 6 content in the public tree)."""
from helix_stadium_mcp.codec import MAGIC, read_hsp, round_trip, write_hsp
from helix_stadium_mcp.codec.floatfmt import to_decimal_string
from helix_stadium_mcp.codec.serialize import serialize

SYNTHETIC = {
    "b": {"x": 1, "y": 1.0, "z": True, "n": None, "small": 1.9999999494757503e-05},
    "a": [1, 2.5, "hi"],
    "10": "ten",
    "9": "nine",
}


def test_synthetic_round_trip_byte_exact():
    data = write_hsp(SYNTHETIC)
    assert data[:8] == MAGIC
    assert round_trip(data) == data          # write->read->write is idempotent
    assert read_hsp(data) == SYNTHETIC       # semantically lossless


def test_numeric_string_keys_sort_lexically():
    # "10" < "9" < "a" by raw code point (the preset.sources trap)
    s = serialize({"10": 0, "9": 0, "a": 0})
    assert s.index('"10"') < s.index('"9"') < s.index('"a"')


def test_int_float_bool_distinct():
    s = serialize({"i": 1, "f": 1.0, "b": True})
    assert '"b": true' in s
    assert '"f": 1.0' in s
    assert '"i": 1' in s and '"i": 1.0' not in s


def test_no_scientific_notation():
    s = serialize({"v": 1.9999999494757503e-05})
    assert "e" not in s and "E" not in s
    assert "0.000019999999494757503" in s


def test_empty_containers():
    assert serialize({}) == "{}"
    assert serialize([]) == "[]"


def test_two_space_indent_no_trailing_newline():
    s = serialize({"a": {"b": 1}})
    assert s == '{\n  "a": {\n    "b": 1\n  }\n}'
    assert not s.endswith("\n")


def test_floatfmt():
    assert to_decimal_string(10.0) == "10.0"
    assert to_decimal_string(-65.0) == "-65.0"
    assert "e" not in to_decimal_string(1e-05)
