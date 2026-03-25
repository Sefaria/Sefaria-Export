#!/usr/bin/env python3
"""Tests for scripts/generate_books_json.py"""
import json
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

import pytest

# Add project root to path so we can import the script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import generate_books_json as gen


# --- parse_text_path tests ---

class TestParseTextPath:
    def test_standard_json_path(self):
        result = gen.parse_text_path("json/Tanakh/Torah/Genesis/English/merged.json")
        assert result == {
            "format": "json",
            "categories": ["Tanakh", "Torah"],
            "title": "Genesis",
            "language": "English",
            "version": "merged",
        }

    def test_txt_format(self):
        result = gen.parse_text_path("txt/Mishnah/Seder Zeraim/Mishnah Berakhot/Hebrew/merged.txt")
        assert result["format"] == "txt"
        assert result["categories"] == ["Mishnah", "Seder Zeraim"]
        assert result["title"] == "Mishnah Berakhot"

    def test_cltk_full_format(self):
        result = gen.parse_text_path("cltk-full/Tanakh/Torah/Genesis/English/merged.json")
        assert result["format"] == "cltk-full"

    def test_cltk_flat_format(self):
        result = gen.parse_text_path("cltk-flat/Tanakh/Torah/Genesis/English/merged.json")
        assert result["format"] == "cltk-flat"

    def test_deep_category_path(self):
        result = gen.parse_text_path("json/Talmud/Bavli/Seder Moed/Shabbat/Hebrew/merged.json")
        assert result["categories"] == ["Talmud", "Bavli", "Seder Moed"]
        assert result["title"] == "Shabbat"

    def test_single_category(self):
        result = gen.parse_text_path("json/Liturgy/Siddur/Hebrew/Ashkenaz.json")
        assert result["categories"] == ["Liturgy"]
        assert result["title"] == "Siddur"

    def test_version_without_extension(self):
        result = gen.parse_text_path("json/Tanakh/Torah/Genesis/English/noext")
        assert result["version"] == "noext"

    def test_too_short_path_returns_none(self):
        assert gen.parse_text_path("json/short") is None
        assert gen.parse_text_path("json/a/b") is None

    def test_unknown_format_returns_none(self):
        assert gen.parse_text_path("xml/Tanakh/Torah/Genesis/English/merged.xml") is None
        assert gen.parse_text_path("csv/something/title/English/v.csv") is None

    def test_empty_string_returns_none(self):
        assert gen.parse_text_path("") is None

    def test_schemas_returns_none(self):
        # schemas/ is not in FORMATS, so it should be treated as special
        assert gen.parse_text_path("schemas/Genesis.json") is None

    def test_links_returns_none(self):
        assert gen.parse_text_path("links/links0.csv") is None

    def test_no_categories_returns_empty_list(self):
        # format/title/language/version.ext -> categories = [] (empty)
        result = gen.parse_text_path("json/Genesis/English/merged.json")
        assert result is not None
        assert result["categories"] == []


# --- list_bucket_objects tests ---

class TestListBucketObjects:
    def _mock_response(self, items, next_page_token=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        data = {"items": items}
        if next_page_token:
            data["nextPageToken"] = next_page_token
        resp.json.return_value = data
        return resp

    @patch("generate_books_json.requests.get")
    def test_single_page(self, mock_get):
        mock_get.return_value = self._mock_response([
            {"name": "json/A/B/English/merged.json", "size": "100"}
        ])
        result = gen.list_bucket_objects("test-bucket")
        assert len(result) == 1
        assert result[0]["name"] == "json/A/B/English/merged.json"

    @patch("generate_books_json.requests.get")
    def test_pagination(self, mock_get):
        mock_get.side_effect = [
            self._mock_response(
                [{"name": "obj1", "size": "100"}],
                next_page_token="page2"
            ),
            self._mock_response(
                [{"name": "obj2", "size": "200"}]
            ),
        ]
        result = gen.list_bucket_objects("test-bucket")
        assert len(result) == 2
        assert mock_get.call_count == 2

    @patch("generate_books_json.requests.get")
    def test_empty_bucket(self, mock_get):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {}
        mock_get.return_value = resp
        result = gen.list_bucket_objects("test-bucket")
        assert result == []

    @patch("generate_books_json.requests.get")
    def test_prefix_parameter(self, mock_get):
        mock_get.return_value = self._mock_response([])
        gen.list_bucket_objects("test-bucket", prefix="json/")
        call_params = mock_get.call_args[1]["params"]
        assert call_params["prefix"] == "json/"

    @patch("generate_books_json.requests.get")
    def test_no_prefix_omits_param(self, mock_get):
        mock_get.return_value = self._mock_response([])
        gen.list_bucket_objects("test-bucket", prefix="")
        call_params = mock_get.call_args[1]["params"]
        assert "prefix" not in call_params


# --- main / end-to-end tests ---

class TestMain:
    FAKE_OBJECTS = [
        {"name": "json/Tanakh/Torah/Genesis/English/merged.json", "size": "5000"},
        {"name": "json/Tanakh/Torah/Genesis/Hebrew/merged.json", "size": "6000"},
        {"name": "txt/Tanakh/Torah/Genesis/English/merged.txt", "size": "3000"},
        {"name": "json/Talmud/Bavli/Seder Moed/Shabbat/Hebrew/merged.json", "size": "80000"},
        {"name": "schemas/Genesis.json", "size": "1000"},
        {"name": "links/links0.csv", "size": "50000"},
        {"name": "table_of_contents.json", "size": "10000"},
        {"name": "json/Tanakh/Torah/Genesis/English/", "size": "0"},  # directory marker
    ]

    @patch("generate_books_json.list_bucket_objects")
    def test_generates_valid_json(self, mock_list):
        mock_list.return_value = self.FAKE_OBJECTS
        with tempfile.TemporaryDirectory() as tmpdir:
            outfile = os.path.join(tmpdir, "books.json")
            import builtins
            real_open = builtins.open
            def patched_open(path, *args, **kwargs):
                if path == "books.json":
                    return real_open(outfile, *args, **kwargs)
                return real_open(path, *args, **kwargs)
            with patch("builtins.open", side_effect=patched_open):
                gen.main()
            with open(outfile) as f:
                data = json.load(f)

        assert "generated_at" in data
        assert "bucket" in data
        assert "base_url" in data
        assert "total_texts" in data
        assert "books" in data
        assert "special_files" in data

    @patch("generate_books_json.list_bucket_objects")
    def test_books_count(self, mock_list):
        mock_list.return_value = self.FAKE_OBJECTS
        with tempfile.TemporaryDirectory() as tmpdir:
            outfile = os.path.join(tmpdir, "books.json")
            import builtins
            real_open = builtins.open
            def patched_open(path, *args, **kwargs):
                if path == "books.json":
                    return real_open(outfile, *args, **kwargs)
                return real_open(path, *args, **kwargs)
            with patch("builtins.open", side_effect=patched_open):
                gen.main()
            with open(outfile) as f:
                data = json.load(f)

        # 3 unique (title, language, version, categories) combos for text formats:
        # (Genesis, English, merged, (Tanakh, Torah))  - has json + txt
        # (Genesis, Hebrew, merged, (Tanakh, Torah))   - json only
        # (Shabbat, Hebrew, merged, (Talmud, Bavli, Seder Moed)) - json only
        assert data["total_texts"] == 3
        assert len(data["books"]) == 3

    @patch("generate_books_json.list_bucket_objects")
    def test_special_files(self, mock_list):
        mock_list.return_value = self.FAKE_OBJECTS
        with tempfile.TemporaryDirectory() as tmpdir:
            outfile = os.path.join(tmpdir, "books.json")
            import builtins
            real_open = builtins.open
            def patched_open(path, *args, **kwargs):
                if path == "books.json":
                    return real_open(outfile, *args, **kwargs)
                return real_open(path, *args, **kwargs)
            with patch("builtins.open", side_effect=patched_open):
                gen.main()
            with open(outfile) as f:
                data = json.load(f)

        special_paths = [s["path"] for s in data["special_files"]]
        assert "schemas/Genesis.json" in special_paths
        assert "links/links0.csv" in special_paths
        assert "table_of_contents.json" in special_paths

    @patch("generate_books_json.list_bucket_objects")
    def test_multiple_format_urls(self, mock_list):
        mock_list.return_value = self.FAKE_OBJECTS
        with tempfile.TemporaryDirectory() as tmpdir:
            outfile = os.path.join(tmpdir, "books.json")
            import builtins
            real_open = builtins.open
            def patched_open(path, *args, **kwargs):
                if path == "books.json":
                    return real_open(outfile, *args, **kwargs)
                return real_open(path, *args, **kwargs)
            with patch("builtins.open", side_effect=patched_open):
                gen.main()
            with open(outfile) as f:
                data = json.load(f)

        # Genesis English should have both json_url and txt_url
        genesis_en = [b for b in data["books"]
                      if b["title"] == "Genesis" and b["language"] == "English"][0]
        assert "json_url" in genesis_en
        assert "txt_url" in genesis_en
        assert "sefaria-export" in genesis_en["json_url"]

    @patch("generate_books_json.list_bucket_objects")
    def test_directory_markers_skipped(self, mock_list):
        mock_list.return_value = self.FAKE_OBJECTS
        with tempfile.TemporaryDirectory() as tmpdir:
            outfile = os.path.join(tmpdir, "books.json")
            import builtins
            real_open = builtins.open
            def patched_open(path, *args, **kwargs):
                if path == "books.json":
                    return real_open(outfile, *args, **kwargs)
                return real_open(path, *args, **kwargs)
            with patch("builtins.open", side_effect=patched_open):
                gen.main()
            with open(outfile) as f:
                data = json.load(f)

        all_paths = [b.get("json_url", "") for b in data["books"]]
        all_paths += [s["path"] for s in data["special_files"]]
        for p in all_paths:
            assert not p.endswith("/")

    @patch("generate_books_json.list_bucket_objects")
    def test_categories_in_output(self, mock_list):
        mock_list.return_value = self.FAKE_OBJECTS
        with tempfile.TemporaryDirectory() as tmpdir:
            outfile = os.path.join(tmpdir, "books.json")
            import builtins
            real_open = builtins.open
            def patched_open(path, *args, **kwargs):
                if path == "books.json":
                    return real_open(outfile, *args, **kwargs)
                return real_open(path, *args, **kwargs)
            with patch("builtins.open", side_effect=patched_open):
                gen.main()
            with open(outfile) as f:
                data = json.load(f)

        shabbat = [b for b in data["books"] if b["title"] == "Shabbat"][0]
        assert shabbat["categories"] == ["Talmud", "Bavli", "Seder Moed"]
