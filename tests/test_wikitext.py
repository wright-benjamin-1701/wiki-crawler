"""Tests for the shared wikitext helpers (wiki_dumps/extract/wikitext.py).

These five helpers are used by every domain extraction job, so regressions here
surface across the whole job suite. The tests cover both the "happy" path (a
value is found / stripped / split correctly) and the relevant failure paths
(empty input, no match, None input).
"""

from __future__ import annotations

import mwparserfromhell  # type: ignore[import-untyped]
import pytest

from wiki_dumps.extract.wikitext import (
    clean_list_field,
    extract_year,
    first_sentence,
    infobox_value,
    strip_wikitext,
)

# ---------------------------------------------------------------------------
# extract_year
# ---------------------------------------------------------------------------


class TestExtractYear:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("1959", 1959),
            ("1926", 1926),
            ("{{Birth date|1926|5|26}}", 1926),
            ("{{Start date|1959|8|17}}", 1959),
            ("released in 1991", 1991),
            ("2024", 2024),
            ("1000", 1000),  # lower bound of the union regex
            ("a 1847 b", 1847),
        ],
    )
    def test_finds_year(self, text: str, expected: int) -> None:
        assert extract_year(text) == expected

    @pytest.mark.parametrize(
        "text",
        [
            None,
            "",
            "no year here",
            "12345",  # 5-digit word is not a year token
            "abc",
            "year: 195",  # 3-digit word is not a year token
        ],
    )
    def test_no_year(self, text: str | None) -> None:
        assert extract_year(text) is None

    def test_returns_int_type(self) -> None:
        assert isinstance(extract_year("1959"), int)


# ---------------------------------------------------------------------------
# infobox_value
# ---------------------------------------------------------------------------


class TestInfoboxValue:
    def test_scalar_value(self) -> None:
        wikicode = mwparserfromhell.parse("{{Infobox person|name = John Smith}}")
        assert infobox_value(wikicode, "name") == "John Smith"

    def test_wikilink_value_is_not_stripped(self) -> None:
        wikicode = mwparserfromhell.parse("{{Infobox|artist = [[John Smith]]}}")
        # infobox_value returns the RAW value (strip_wikitext is a separate step)
        assert infobox_value(wikicode, "artist") == "[[John Smith]]"

    def test_missing_key_is_none(self) -> None:
        wikicode = mwparserfromhell.parse("{{Infobox person|name = John}}")
        assert infobox_value(wikicode, "age") is None

    def test_empty_value_is_none(self) -> None:
        wikicode = mwparserfromhell.parse("{{Infobox person|name =   }}")
        assert infobox_value(wikicode, "name") is None

    def test_first_matching_template_wins(self) -> None:
        wikicode = mwparserfromhell.parse("{{a|x=1}} {{b|name = first}} {{c|name = second}}")
        assert infobox_value(wikicode, "name") == "first"


# ---------------------------------------------------------------------------
# strip_wikitext
# ---------------------------------------------------------------------------


class TestStripWikitext:
    def test_wikilink(self) -> None:
        assert strip_wikitext("[[John Smith]]") == "John Smith"

    def test_bare_template_is_removed(self) -> None:
        # A value that is *only* a template (e.g. {{Birth date|...}}) strips to nothing → None.
        assert strip_wikitext("{{Birth date|1926|5|26}}") is None

    def test_template_removed_surrounding_text_kept(self) -> None:
        # The template is dropped (leaving an extra space), the prose is kept.
        assert strip_wikitext("hello {{x|y}} world") == "hello  world"

    def test_plain_text(self) -> None:
        assert strip_wikitext("Alton, Illinois, U.S.") == "Alton, Illinois, U.S."

    def test_none_input(self) -> None:
        assert strip_wikitext(None) is None

    def test_empty_input(self) -> None:
        assert strip_wikitext("") is None

    def test_only_blanks(self) -> None:
        assert strip_wikitext("   ") is None


# ---------------------------------------------------------------------------
# clean_list_field
# ---------------------------------------------------------------------------


class TestCleanListField:
    def test_hlist_template(self) -> None:
        raw = "{{hlist|trumpet|flugelhorn}} "
        assert clean_list_field(raw) == "trumpet|flugelhorn"

    def test_wikilinks_hlist(self) -> None:
        raw = "{{hlist|[[Blue Note]]|[[Prestige]]|[[Columbia]]}}"
        assert clean_list_field(raw) == "Blue Note|Prestige|Columbia"

    def test_bare_comma_list(self) -> None:
        assert clean_list_field("a, b, c") == "a|b|c"

    def test_newline_list(self) -> None:
        assert clean_list_field("a\nb\nc") == "a|b|c"

    def test_bullet_list(self) -> None:
        assert clean_list_field("* a\n* b") == "a|b"

    def test_mixed_separators(self) -> None:
        assert clean_list_field("a, b\nc • d") == "a|b|c|d"

    def test_none_input(self) -> None:
        assert clean_list_field(None) is None

    def test_empty_input(self) -> None:
        assert clean_list_field("") is None

    def test_whitespace_only(self) -> None:
        assert clean_list_field("   ") is None


# ---------------------------------------------------------------------------
# first_sentence
# ---------------------------------------------------------------------------


class TestFirstSentence:
    def test_simple(self) -> None:
        wikicode = mwparserfromhell.parse("Miles Davis was an American jazz trumpeter.")
        assert first_sentence(wikicode) == "Miles Davis was an American jazz trumpeter"

    def test_multiple_sentences(self) -> None:
        wikicode = mwparserfromhell.parse("First sentence. Second sentence. Third.")
        assert first_sentence(wikicode) == "First sentence"

    def test_no_period(self) -> None:
        wikicode = mwparserfromhell.parse("No period here")
        assert first_sentence(wikicode) == "No period here"

    def test_strips_wikilinks(self) -> None:
        wikicode = mwparserfromhell.parse("[[Miles Davis]] was a trumpeter.")
        assert first_sentence(wikicode) == "Miles Davis was a trumpeter"


def test_list_templates_constant_includes_expected() -> None:
    from wiki_dumps.extract.wikitext import LIST_TEMPLATES

    for name in ("hlist", "flatlist", "plainlist", "unbulleted list", "ubl"):
        assert name in LIST_TEMPLATES


def test_year_range_is_union_of_all_prior_job_variants() -> None:
    """Sanity: the shared YEAR_RE should accept the years each job's own regex
    used to accept (so no regression)."""
    from wiki_dumps.extract.wikitext import YEAR_RE

    # jazz/scifi/star_trek/board_games used: 1[89]\d{2}
    assert YEAR_RE.search("1847") is not None
    assert YEAR_RE.search("1959") is not None
    # classical_music used: 1[3-9]\d{2}
    assert YEAR_RE.search("1347") is not None
    # literature/philosophy used: 1[0-9]\d{2}
    assert YEAR_RE.search("1047") is not None
    # upper bound
    assert YEAR_RE.search("2029") is not None
    assert YEAR_RE.search("2030") is None
    assert YEAR_RE.search("999") is None
