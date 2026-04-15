#!/usr/bin/env python3
"""Tests for scripts/export_dictionaries_csv.py"""
import csv
import json
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

import pytest

# Add project root to path so we can import the script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import export_dictionaries_csv as exporter


# --- strip_html tests ---
class TestStripHtml:
    def test_removes_simple_tags(self):
        assert exporter.strip_html("<b>bold</b>") == "bold"

    def test_removes_nested_tags(self):
        assert exporter.strip_html("<div><span>text</span></div>") == "text"

    def test_removes_anchor_tags(self):
        html = '<a class="refLink" href="/Genesis.1.1">Gen 1:1</a>'
        assert exporter.strip_html(html) == "Gen 1:1"

    def test_removes_rtl_spans(self):
        html = '<span dir="rtl">עברית</span>'
        assert exporter.strip_html(html) == "עברית"

    def test_removes_italic_tags(self):
        assert exporter.strip_html("<i>emphasis</i>") == "emphasis"

    def test_preserves_plain_text(self):
        assert exporter.strip_html("no tags here") == "no tags here"

    def test_collapses_whitespace(self):
        assert exporter.strip_html("lots   of   space") == "lots of space"

    def test_handles_empty_string(self):
        assert exporter.strip_html("") == ""

    def test_handles_none(self):
        assert exporter.strip_html(None) == ""

    def test_handles_complex_dictionary_html(self):
        html = (
            '<i>Ab,</i> the fifth month. '
            '<a class="refLink" href="/Mishnah_Rosh_Hashanah.1.3">'
            'R. Hash. I, 3</a>, '
            '<span dir="rtl">על אב וכ׳</span> for announcing.'
        )
        result = exporter.strip_html(html)
        assert "Ab," in result
        assert "R. Hash. I, 3" in result
        assert "על אב וכ׳" in result
        assert "<" not in result


# --- flatten_senses tests ---
class TestFlattenSenses:
    def test_single_sense(self):
        senses = [{"definition": "father"}]
        result = exporter.flatten_senses(senses)
        assert result == "father"

    def test_multiple_senses(self):
        senses = [
            {"definition": "father of an individual"},
            {"definition": "head of a household"},
        ]
        result = exporter.flatten_senses(senses)
        assert "father of an individual" in result
        assert "head of a household" in result

    def test_nested_senses(self):
        senses = [
            {
                "definition": "ancestor",
                "senses": [
                    {"definition": "grandfather"},
                    {"definition": "of people"},
                ],
            }
        ]
        result = exporter.flatten_senses(senses)
        assert "ancestor" in result
        assert "grandfather" in result

    def test_html_in_definitions(self):
        senses = [{"definition": "<i>Ab,</i> the fifth month"}]
        result = exporter.flatten_senses(senses)
        assert "Ab," in result
        assert "<i>" not in result

    def test_empty_senses(self):
        assert exporter.flatten_senses([]) == ""

    def test_sense_without_definition(self):
        senses = [{"grammar": "noun"}]
        result = exporter.flatten_senses(senses)
        assert result == ""


# --- entry_to_row tests ---
class TestEntryToRow:
    SAMPLE_JASTROW_ENTRY = {
        "headword": "אָב I",
        "parent_lexicon": "Jastrow Dictionary",
        "rid": "A00013",
        "refs": ["Rosh Hashanah 18b", "Megillah 5b:2"],
        "content": {
            "senses": [
                {
                    "definition": "<i>Ab,</i> the fifth month of the Jewish calendar"
                }
            ]
        },
        "plural_form": [],
        "alt_headwords": ["אב"],
        "prev_hw": "אַב־",
        "next_hw": "אָב II",
    }

    SAMPLE_BDB_STRONG_ENTRY = {
        "headword": "אָב",
        "parent_lexicon": "BDB Augmented Strong",
        "content": {
            "morphology": "n-m",
            "senses": [
                {"definition": "father of an individual"},
                {"definition": "of God as father of his people"},
            ],
        },
        "strong_number": "1",
        "transliteration": "ʼâb",
        "pronunciation": "awb",
        "language_code": "heb",
    }

    def test_jastrow_entry(self):
        row = exporter.entry_to_row(self.SAMPLE_JASTROW_ENTRY)
        assert row["headword"] == "אָב I"
        assert row["headword_id"] == "A00013"
        assert row["source_lexicon"] == "Jastrow Dictionary"
        assert row["prev_headword"] == "אַב־"
        assert row["next_headword"] == "אָב II"
        assert "Ab," in row["definition"]
        assert "<i>" not in row["definition"]
        assert row["alt_headwords"] == "אב"
        assert "Rosh Hashanah 18b" in row["cross_refs"]

    def test_bdb_strong_entry(self):
        row = exporter.entry_to_row(self.SAMPLE_BDB_STRONG_ENTRY)
        assert row["headword"] == "אָב"
        assert row["transliteration"] == "ʼâb"
        assert row["pronunciation"] == "awb"
        assert row["morphology"] == "n-m"
        assert row["strong_number"] == "1"
        assert row["language_code"] == "heb"

    def test_empty_entry(self):
        row = exporter.entry_to_row({})
        assert row["headword"] == ""
        assert row["definition"] == ""
        assert row["senses_json"] == ""

    def test_senses_json_roundtrips(self):
        row = exporter.entry_to_row(self.SAMPLE_BDB_STRONG_ENTRY)
        parsed = json.loads(row["senses_json"])
        assert isinstance(parsed, list)
        assert len(parsed) == 2


# --- Checkpoint tests ---
class TestCheckpoint:
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, ".test.checkpoint")
            exporter.save_checkpoint(path, "אָב", 42)
            result = exporter.load_checkpoint(path)
            assert result["last_headword"] == "אָב"
            assert result["count"] == 42

    def test_load_missing_file(self):
        assert exporter.load_checkpoint("/nonexistent/path") is None

    def test_save_overwrites(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, ".test.checkpoint")
            exporter.save_checkpoint(path, "א", 1)
            exporter.save_checkpoint(path, "ב", 100)
            result = exporter.load_checkpoint(path)
            assert result["last_headword"] == "ב"
            assert result["count"] == 100


# --- get_starting_headwords tests ---
class TestGetStartingHeadwords:
    @patch("export_dictionaries_csv.fetch_index")
    def test_extracts_headword_map(self, mock_fetch):
        mock_fetch.return_value = {
            "schema": {
                "nodes": [
                    {
                        "nodeType": "DictionaryNode",
                        "headwordMap": [
                            ["א", "Jastrow, א"],
                            ["ב", "Jastrow, ב"],
                        ],
                    }
                ]
            }
        }
        result = exporter.get_starting_headwords("Jastrow")
        assert len(result) == 2
        assert result[0] == ["א", "Jastrow, א"]

    @patch("export_dictionaries_csv.fetch_index")
    def test_returns_empty_for_no_dictionary_node(self, mock_fetch):
        mock_fetch.return_value = {
            "schema": {
                "nodes": [{"nodeType": "JaggedArrayNode"}]
            }
        }
        result = exporter.get_starting_headwords("Something")
        assert result == []


# --- Integration-style test with mocked API ---
class TestExportLexicon:
    @patch("export_dictionaries_csv.fetch_word_entries")
    @patch("export_dictionaries_csv.get_starting_headwords")
    def test_exports_csv_with_limit(self, mock_hw, mock_fetch):
        mock_hw.return_value = [["א", "Jastrow, א"]]

        # Simulate 3 entries linked together
        mock_fetch.side_effect = [
            [
                {
                    "headword": "א",
                    "parent_lexicon": "Jastrow Dictionary",
                    "rid": "A00001",
                    "content": {"senses": [{"definition": "first letter"}]},
                    "next_hw": "אָב",
                    "prev_hw": None,
                }
            ],
            [
                {
                    "headword": "אָב",
                    "parent_lexicon": "Jastrow Dictionary",
                    "rid": "A00002",
                    "content": {"senses": [{"definition": "father"}]},
                    "next_hw": "אֵב",
                    "prev_hw": "א",
                }
            ],
            [
                {
                    "headword": "אֵב",
                    "parent_lexicon": "Jastrow Dictionary",
                    "rid": "A00003",
                    "content": {"senses": [{"definition": "freshness"}]},
                    "next_hw": None,
                    "prev_hw": "אָב",
                }
            ],
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = exporter.export_lexicon(
                "Jastrow Dictionary", tmpdir, delay=0, limit=3
            )
            assert result is True

            csv_path = os.path.join(tmpdir, "Jastrow_Dictionary.csv")
            assert os.path.exists(csv_path)

            with open(csv_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            assert len(rows) == 3
            assert rows[0]["headword"] == "א"
            assert rows[1]["headword"] == "אָב"
            assert rows[2]["headword"] == "אֵב"
            assert rows[1]["definition"] == "father"

    def test_rejects_unknown_lexicon(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = exporter.export_lexicon("Nonexistent", tmpdir)
            assert result is False

    def test_rejects_lexicon_without_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = exporter.export_lexicon("BDB Augmented Strong", tmpdir)
            assert result is False


# --- CSV column tests ---
class TestCsvColumns:
    def test_all_columns_present(self):
        expected = {
            "headword", "headword_id", "transliteration", "pronunciation",
            "morphology", "definition", "senses_json", "alt_headwords",
            "plural_form", "strong_number", "language_code", "cross_refs",
            "source_lexicon", "prev_headword", "next_headword",
        }
        assert set(exporter.CSV_COLUMNS) == expected

    def test_entry_to_row_returns_all_columns(self):
        row = exporter.entry_to_row({})
        assert set(row.keys()) == set(exporter.CSV_COLUMNS)
