from __future__ import annotations

from app.dvr import edl_parser


def test_parse_edl_file_well_formed(tmp_path):
    edl = tmp_path / "recording.edl"
    edl.write_text("10.5 20.25 0\n50 65 0\n")

    segments = edl_parser.parse_edl_file(edl)

    assert segments == [
        {"start_seconds": 10.5, "end_seconds": 20.25},
        {"start_seconds": 50.0, "end_seconds": 65.0},
    ]


def test_parse_edl_file_two_column_defaults_to_commercial(tmp_path):
    edl = tmp_path / "recording.edl"
    edl.write_text("10 20\n")

    segments = edl_parser.parse_edl_file(edl)

    assert segments == [{"start_seconds": 10.0, "end_seconds": 20.0}]


def test_parse_edl_file_excludes_non_commercial_type(tmp_path):
    edl = tmp_path / "recording.edl"
    edl.write_text("10 20 0\n30 40 1\n")

    segments = edl_parser.parse_edl_file(edl)

    assert segments == [{"start_seconds": 10.0, "end_seconds": 20.0}]


def test_parse_edl_file_skips_malformed_lines(tmp_path):
    edl = tmp_path / "recording.edl"
    edl.write_text("not a number here\n10 20 0\n\n30 notanumber 0\n40 50 0\n")

    segments = edl_parser.parse_edl_file(edl)

    assert segments == [
        {"start_seconds": 10.0, "end_seconds": 20.0},
        {"start_seconds": 40.0, "end_seconds": 50.0},
    ]


def test_parse_edl_file_excludes_end_not_after_start(tmp_path):
    edl = tmp_path / "recording.edl"
    edl.write_text("10 10 0\n20 15 0\n30 40 0\n")

    segments = edl_parser.parse_edl_file(edl)

    assert segments == [{"start_seconds": 30.0, "end_seconds": 40.0}]


def test_parse_edl_file_sorts_by_start(tmp_path):
    edl = tmp_path / "recording.edl"
    edl.write_text("50 60 0\n10 20 0\n")

    segments = edl_parser.parse_edl_file(edl)

    assert segments == [
        {"start_seconds": 10.0, "end_seconds": 20.0},
        {"start_seconds": 50.0, "end_seconds": 60.0},
    ]


def test_parse_edl_file_empty_file(tmp_path):
    edl = tmp_path / "recording.edl"
    edl.write_text("")

    assert edl_parser.parse_edl_file(edl) == []


def test_parse_edl_file_missing_file(tmp_path):
    assert edl_parser.parse_edl_file(tmp_path / "does_not_exist.edl") == []
