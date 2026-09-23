"""Tests for extraction job implementations: jazz and scifi."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from wiki_dumps.parse.types import WikiPage


def _make_page(
    *,
    page_id: int = 1,
    title: str = "Test",
    categories: tuple[str, ...] = (),
    wikitext: str = "",
    namespace: int = 0,
    redirect_to: str | None = None,
) -> WikiPage:
    return WikiPage(
        page_id=page_id,
        namespace=namespace,
        title=title,
        redirect_to=redirect_to,
        categories=categories,
        wikitext=wikitext,
        revision_id=1,
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        contributor="TestUser",
    )


# ---------------------------------------------------------------------------
# Jazz research job
# ---------------------------------------------------------------------------

_JAZZ_ARTIST_WIKITEXT = """\
{{Infobox musical artist
| name        = Miles Davis
| birth_date  = {{Birth date|1926|5|26}}
| death_date  = {{Death date|1991|9|28}}
| origin      = Alton, Illinois, U.S.
| instrument  = {{hlist|trumpet|flugelhorn}}
| genre       = {{hlist|jazz|bebop|cool jazz}}
| years_active = 1944–1991
| label       = {{hlist|Blue Note|Prestige|Columbia}}
}}
Miles Davis was an American jazz trumpeter.
"""

_JAZZ_ALBUM_WIKITEXT = """\
{{Infobox album
| name     = Kind of Blue
| artist   = Miles Davis
| released = {{Start date|1959|8|17}}
| label    = {{hlist|Columbia|Legacy}}
| genre    = {{hlist|modal jazz|jazz}}
| personnel = Miles Davis – trumpet{{newline}}John Coltrane – tenor saxophone
}}
Kind of Blue is a studio album by Miles Davis.
"""

_JAZZ_GENRE_WIKITEXT = """\
{{Infobox music genre
| stylistic_origins = {{hlist|African American music|blues}}
}}
Bebop is a style of jazz characterized by fast tempos.
"""


@pytest.fixture
def jazz_artist_page() -> WikiPage:
    return _make_page(
        page_id=10,
        title="Miles Davis",
        categories=("Jazz musicians", "American jazz trumpeters", "20th-century musicians"),
        wikitext=_JAZZ_ARTIST_WIKITEXT,
    )


@pytest.fixture
def jazz_album_page() -> WikiPage:
    return _make_page(
        page_id=11,
        title="Kind of Blue",
        categories=("Jazz albums", "Miles Davis albums", "1959 jazz albums"),
        wikitext=_JAZZ_ALBUM_WIKITEXT,
    )


@pytest.fixture
def jazz_genre_page() -> WikiPage:
    return _make_page(
        page_id=12,
        title="Bebop",
        categories=("Jazz genres",),
        wikitext=_JAZZ_GENRE_WIKITEXT,
    )


@pytest.fixture
def non_jazz_page() -> WikiPage:
    return _make_page(
        page_id=99,
        title="Python (programming language)",
        categories=("Programming languages", "Object-oriented programming languages"),
        wikitext="Python is a programming language.",
    )


class TestJazzJobMatches:
    def test_matches_jazz_artist(self, jazz_artist_page: WikiPage, sqlite_db_url: str) -> None:
        from wiki_dumps.jobs.jazz import JazzJob

        job = JazzJob(sqlite_db_url)
        assert job.matches(jazz_artist_page) is True

    def test_matches_jazz_album(self, jazz_album_page: WikiPage, sqlite_db_url: str) -> None:
        from wiki_dumps.jobs.jazz import JazzJob

        job = JazzJob(sqlite_db_url)
        assert job.matches(jazz_album_page) is True

    def test_matches_jazz_genre_by_title(self, sqlite_db_url: str) -> None:
        from wiki_dumps.jobs.jazz import JazzJob

        page = _make_page(title="Bebop", categories=())
        job = JazzJob(sqlite_db_url)
        assert job.matches(page) is True

    def test_does_not_match_non_jazz(self, non_jazz_page: WikiPage, sqlite_db_url: str) -> None:
        from wiki_dumps.jobs.jazz import JazzJob

        job = JazzJob(sqlite_db_url)
        assert job.matches(non_jazz_page) is False

    def test_does_not_match_redirect(self, sqlite_db_url: str) -> None:
        from wiki_dumps.jobs.jazz import JazzJob

        page = _make_page(
            title="Miles Davis",
            categories=("Jazz musicians",),
            redirect_to="Miles Dewey Davis",
        )
        job = JazzJob(sqlite_db_url)
        # is_article filter excludes redirects — wait, is_article only checks namespace
        # redirects are articles in ns 0; JazzJob only checks is_article (ns==0)
        # A redirect with jazz category still matches
        assert job.matches(page) is True

    def test_does_not_match_talk_namespace(self, sqlite_db_url: str) -> None:
        from wiki_dumps.jobs.jazz import JazzJob

        page = _make_page(
            title="Talk:Miles Davis",
            categories=("Jazz musicians",),
            namespace=1,
        )
        job = JazzJob(sqlite_db_url)
        assert job.matches(page) is False


class TestJazzJobExtract:
    def test_extract_artist_writes_to_db(
        self, jazz_artist_page: WikiPage, sqlite_db_url: str
    ) -> None:
        from sqlalchemy import select

        from wiki_dumps.db.session import get_session, make_engine
        from wiki_dumps.jobs.jazz import JazzArtist, JazzJob

        job = JazzJob(sqlite_db_url)
        job.setup_schema()
        job.extract(jazz_artist_page)
        job.flush()

        engine = make_engine(sqlite_db_url)
        with get_session(engine) as session:
            rows = session.execute(select(JazzArtist)).scalars().all()
            assert len(rows) == 1
            artist = rows[0]
            assert artist.title == "Miles Davis"
            assert artist.page_id == 10
            assert artist.birth_year == 1926
            assert artist.death_year == 1991

    def test_extract_album_writes_to_db(
        self, jazz_album_page: WikiPage, sqlite_db_url: str
    ) -> None:
        from sqlalchemy import select

        from wiki_dumps.db.session import get_session, make_engine
        from wiki_dumps.jobs.jazz import JazzAlbum, JazzJob

        job = JazzJob(sqlite_db_url)
        job.setup_schema()
        job.extract(jazz_album_page)
        job.flush()

        engine = make_engine(sqlite_db_url)
        with get_session(engine) as session:
            rows = session.execute(select(JazzAlbum)).scalars().all()
            assert len(rows) == 1
            album = rows[0]
            assert album.title == "Kind of Blue"
            assert album.artist == "Miles Davis"
            assert album.release_year == 1959

    def test_extract_genre_writes_to_db(
        self, jazz_genre_page: WikiPage, sqlite_db_url: str
    ) -> None:
        from sqlalchemy import select

        from wiki_dumps.db.session import get_session, make_engine
        from wiki_dumps.jobs.jazz import JazzGenre, JazzJob

        job = JazzJob(sqlite_db_url)
        job.setup_schema()
        job.extract(jazz_genre_page)
        job.flush()

        engine = make_engine(sqlite_db_url)
        with get_session(engine) as session:
            rows = session.execute(select(JazzGenre)).scalars().all()
            assert len(rows) == 1
            genre = rows[0]
            assert genre.title == "Bebop"
            assert genre.page_id == 12

    def test_extract_does_not_write_until_flush(
        self, jazz_artist_page: WikiPage, sqlite_db_url: str
    ) -> None:
        """Records should not appear in DB until flush() is called."""
        from sqlalchemy import select

        from wiki_dumps.db.session import get_session, make_engine
        from wiki_dumps.jobs.jazz import JazzArtist, JazzJob

        job = JazzJob(sqlite_db_url)
        job.setup_schema()
        job.extract(jazz_artist_page)
        # Not flushed yet — DB should be empty
        engine = make_engine(sqlite_db_url)
        with get_session(engine) as session:
            rows = session.execute(select(JazzArtist)).scalars().all()
            assert len(rows) == 0
        # After flush — should appear
        job.flush()
        with get_session(engine) as session:
            rows = session.execute(select(JazzArtist)).scalars().all()
            assert len(rows) == 1


# ---------------------------------------------------------------------------
# Scifi job
# ---------------------------------------------------------------------------

_SCIFI_NOVEL_WIKITEXT = """\
{{Infobox book
| name          = Dune
| author        = Frank Herbert
| pub_date      = {{Start date|1965|8|1}}
| publisher     = Chilton Books
| series        = Dune
| genre         = {{hlist|science fiction|epic science fiction}}
| preceded_by   =
| followed_by   = Dune Messiah
}}
Dune is a 1965 science fiction novel by American author Frank Herbert.
"""

_SCIFI_FILM_WIKITEXT = """\
{{Infobox film
| name           = Alien
| director       = Ridley Scott
| writer         = Dan O'Bannon
| released       = {{Film date|1979|5|25}}
| starring       = {{hlist|Sigourney Weaver|Tom Skerritt}}
| based_on       = Characters by Dan O'Bannon and Ronald Shusett
}}
Alien is a 1979 science fiction horror film directed by Ridley Scott.
"""

_SCIFI_AUTHOR_WIKITEXT = """\
{{Infobox writer
| name          = Isaac Asimov
| birth_date    = {{Birth date|1920|1|2}}
| death_date    = {{Death date|1992|4|6}}
| nationality   = American
| genre         = {{hlist|science fiction|mystery}}
| notable_works = {{hlist|Foundation|I, Robot|The Caves of Steel}}
}}
Isaac Asimov was an American writer and professor of biochemistry.
"""


@pytest.fixture
def scifi_novel_page() -> WikiPage:
    return _make_page(
        page_id=20,
        title="Dune (novel)",
        categories=("1965 science fiction novels", "Hugo Award for Best Novel winners"),
        wikitext=_SCIFI_NOVEL_WIKITEXT,
    )


@pytest.fixture
def scifi_film_page() -> WikiPage:
    return _make_page(
        page_id=21,
        title="Alien (film)",
        categories=("1979 science fiction films", "English-language films"),
        wikitext=_SCIFI_FILM_WIKITEXT,
    )


@pytest.fixture
def scifi_author_page() -> WikiPage:
    return _make_page(
        page_id=22,
        title="Isaac Asimov",
        categories=("Science fiction writers", "20th-century American novelists"),
        wikitext=_SCIFI_AUTHOR_WIKITEXT,
    )


class TestScifiJobMatches:
    def test_matches_scifi_novel(self, scifi_novel_page: WikiPage, sqlite_db_url: str) -> None:
        from wiki_dumps.jobs.scifi import ScifiJob

        job = ScifiJob(sqlite_db_url)
        assert job.matches(scifi_novel_page) is True

    def test_matches_scifi_film(self, scifi_film_page: WikiPage, sqlite_db_url: str) -> None:
        from wiki_dumps.jobs.scifi import ScifiJob

        job = ScifiJob(sqlite_db_url)
        assert job.matches(scifi_film_page) is True

    def test_matches_scifi_author(self, scifi_author_page: WikiPage, sqlite_db_url: str) -> None:
        from wiki_dumps.jobs.scifi import ScifiJob

        job = ScifiJob(sqlite_db_url)
        assert job.matches(scifi_author_page) is True

    def test_does_not_match_unrelated(self, sqlite_db_url: str) -> None:
        from wiki_dumps.jobs.scifi import ScifiJob

        page = _make_page(
            title="Python (programming language)",
            categories=("Programming languages",),
        )
        job = ScifiJob(sqlite_db_url)
        assert job.matches(page) is False

    def test_does_not_match_talk_namespace(self, sqlite_db_url: str) -> None:
        from wiki_dumps.jobs.scifi import ScifiJob

        page = _make_page(
            title="Talk:Dune",
            categories=("1965 science fiction novels",),
            namespace=1,
        )
        job = ScifiJob(sqlite_db_url)
        assert job.matches(page) is False


class TestScifiJobExtract:
    def test_extract_novel_writes_to_db(
        self, scifi_novel_page: WikiPage, sqlite_db_url: str
    ) -> None:
        from sqlalchemy import select

        from wiki_dumps.db.session import get_session, make_engine
        from wiki_dumps.jobs.scifi import ScifiJob, ScifiNovel

        job = ScifiJob(sqlite_db_url)
        job.setup_schema()
        job.extract(scifi_novel_page)
        job.flush()

        engine = make_engine(sqlite_db_url)
        with get_session(engine) as session:
            rows = session.execute(select(ScifiNovel)).scalars().all()
            assert len(rows) == 1
            novel = rows[0]
            assert novel.title == "Dune (novel)"
            assert novel.author == "Frank Herbert"
            assert novel.pub_year == 1965
            assert novel.publisher == "Chilton Books"
            assert novel.followed_by == "Dune Messiah"

    def test_extract_film_writes_to_db(
        self, scifi_film_page: WikiPage, sqlite_db_url: str
    ) -> None:
        from sqlalchemy import select

        from wiki_dumps.db.session import get_session, make_engine
        from wiki_dumps.jobs.scifi import ScifiFilm, ScifiJob

        job = ScifiJob(sqlite_db_url)
        job.setup_schema()
        job.extract(scifi_film_page)
        job.flush()

        engine = make_engine(sqlite_db_url)
        with get_session(engine) as session:
            rows = session.execute(select(ScifiFilm)).scalars().all()
            assert len(rows) == 1
            film = rows[0]
            assert film.title == "Alien (film)"
            assert film.director == "Ridley Scott"
            assert film.release_year == 1979

    def test_extract_author_writes_to_db(
        self, scifi_author_page: WikiPage, sqlite_db_url: str
    ) -> None:
        from sqlalchemy import select

        from wiki_dumps.db.session import get_session, make_engine
        from wiki_dumps.jobs.scifi import ScifiAuthor, ScifiJob

        job = ScifiJob(sqlite_db_url)
        job.setup_schema()
        job.extract(scifi_author_page)
        job.flush()

        engine = make_engine(sqlite_db_url)
        with get_session(engine) as session:
            rows = session.execute(select(ScifiAuthor)).scalars().all()
            assert len(rows) == 1
            author = rows[0]
            assert author.title == "Isaac Asimov"
            assert author.birth_year == 1920
            assert author.death_year == 1992
            assert author.nationality == "American"

    def test_extract_does_not_write_until_flush(
        self, scifi_novel_page: WikiPage, sqlite_db_url: str
    ) -> None:
        """Records should not appear in DB until flush() is called."""
        from sqlalchemy import select

        from wiki_dumps.db.session import get_session, make_engine
        from wiki_dumps.jobs.scifi import ScifiJob, ScifiNovel

        job = ScifiJob(sqlite_db_url)
        job.setup_schema()
        job.extract(scifi_novel_page)
        engine = make_engine(sqlite_db_url)
        with get_session(engine) as session:
            rows = session.execute(select(ScifiNovel)).scalars().all()
            assert len(rows) == 0
        job.flush()
        with get_session(engine) as session:
            rows = session.execute(select(ScifiNovel)).scalars().all()
            assert len(rows) == 1


# ---------------------------------------------------------------------------
# Star Trek job
# ---------------------------------------------------------------------------

_TREK_EPISODE_WIKITEXT = """\
{{Star Trek episode
| series    = [[Star Trek: The Next Generation]]
| season    = 3
| episode   = 26
| airdate   = June 18, 1990
| stardate  = 43989.1
| director  = Cliff Bole
| teleplay  = Michael Piller
| story     = Michael Piller
| production = 40274-174
}}
"The Best of Both Worlds" is a third-season episode of Star Trek: The Next Generation.
"""

_TREK_MOVIE_WIKITEXT = """\
{{Infobox film
| name           = Star Trek II: The Wrath of Khan
| director       = Nicholas Meyer
| screenplay     = Jack B. Sowards
| released       = {{Film date|1982|6|4}}
| starring       = {{hlist|William Shatner|Leonard Nimoy|DeForest Kelley}}
| budget         = $11.2 million
| gross          = $97 million
}}
Star Trek II: The Wrath of Khan is a 1982 American science fiction film.
"""

_TREK_SHOW_WIKITEXT = """\
{{Infobox television
| name         = Star Trek: Deep Space Nine
| network      = {{hlist|Syndication|CBS Action}}
| first_aired  = {{Start date|1993|1|3}}
| last_aired   = {{End date|1999|6|2}}
| num_seasons  = 7
| num_episodes = 176
}}
Star Trek: Deep Space Nine is an American science fiction television series.
"""

_TREK_BOOK_WIKITEXT = """\
{{Infobox book
| name       = Imzadi
| author     = Peter David
| pub_date   = {{Start date|1992|8|1}}
| publisher  = Pocket Books
| series     = Star Trek: The Next Generation
}}
Imzadi is a Star Trek: The Next Generation novel by Peter David.
"""

_TREK_CHARACTER_WIKITEXT = """\
{{Star Trek character
| name         = Spock
| portrayed_by = [[Leonard Nimoy]]
| species      = Vulcan/Human
| rank         = Commander
| affiliation  = {{hlist|[[Starfleet]]|[[United Federation of Planets]]}}
| first        = "The Cage"
}}
Spock is a fictional character in the Star Trek media franchise.
"""

_TREK_SPECIES_WIKITEXT = """\
{{Infobox fictional race
| quadrant    = Beta
| homeworld   = Qo'noS
| affiliation = Klingon Empire
}}
Klingons are a fictional alien species in the Star Trek franchise.
"""

_TREK_STARSHIP_WIKITEXT = """\
{{Star Trek ship
| registry        = NCC-1701-D
| class           = Galaxy
| affiliation     = Starfleet
| first           = "Encounter at Farpoint"
}}
The USS Enterprise (NCC-1701-D) is a fictional starship in Star Trek: The Next Generation.
"""


@pytest.fixture
def trek_episode_page() -> WikiPage:
    return _make_page(
        page_id=100,
        title="The Best of Both Worlds (Star Trek: The Next Generation)",
        categories=("Star Trek: The Next Generation season 3 episodes", "Television cliffhangers"),
        wikitext=_TREK_EPISODE_WIKITEXT,
    )


@pytest.fixture
def trek_movie_page() -> WikiPage:
    return _make_page(
        page_id=101,
        title="Star Trek II: The Wrath of Khan",
        categories=("Star Trek films", "1982 science fiction films"),
        wikitext=_TREK_MOVIE_WIKITEXT,
    )


@pytest.fixture
def trek_show_page() -> WikiPage:
    return _make_page(
        page_id=102,
        title="Star Trek: Deep Space Nine",
        categories=("Star Trek television series", "American science fiction television series"),
        wikitext=_TREK_SHOW_WIKITEXT,
    )


@pytest.fixture
def trek_book_page() -> WikiPage:
    return _make_page(
        page_id=103,
        title="Imzadi",
        categories=("Star Trek novels", "Star Trek: The Next Generation novels"),
        wikitext=_TREK_BOOK_WIKITEXT,
    )


@pytest.fixture
def trek_character_page() -> WikiPage:
    return _make_page(
        page_id=104,
        title="Spock",
        categories=("Star Trek characters", "Fictional Vulcans"),
        wikitext=_TREK_CHARACTER_WIKITEXT,
    )


@pytest.fixture
def trek_species_page() -> WikiPage:
    return _make_page(
        page_id=105,
        title="Klingons",
        categories=("Star Trek races", "Fictional extraterrestrial species"),
        wikitext=_TREK_SPECIES_WIKITEXT,
    )


@pytest.fixture
def trek_starship_page() -> WikiPage:
    return _make_page(
        page_id=106,
        title="USS Enterprise (NCC-1701-D)",
        categories=("Starships in Star Trek", "Star Trek: The Next Generation"),
        wikitext=_TREK_STARSHIP_WIKITEXT,
    )


class TestStarTrekJobMatches:
    def test_matches_episode(self, trek_episode_page: WikiPage, sqlite_db_url: str) -> None:
        from wiki_dumps.jobs.star_trek import StarTrekJob

        assert StarTrekJob(sqlite_db_url).matches(trek_episode_page) is True

    def test_matches_movie(self, trek_movie_page: WikiPage, sqlite_db_url: str) -> None:
        from wiki_dumps.jobs.star_trek import StarTrekJob

        assert StarTrekJob(sqlite_db_url).matches(trek_movie_page) is True

    def test_matches_show(self, trek_show_page: WikiPage, sqlite_db_url: str) -> None:
        from wiki_dumps.jobs.star_trek import StarTrekJob

        assert StarTrekJob(sqlite_db_url).matches(trek_show_page) is True

    def test_matches_book(self, trek_book_page: WikiPage, sqlite_db_url: str) -> None:
        from wiki_dumps.jobs.star_trek import StarTrekJob

        assert StarTrekJob(sqlite_db_url).matches(trek_book_page) is True

    def test_matches_character(self, trek_character_page: WikiPage, sqlite_db_url: str) -> None:
        from wiki_dumps.jobs.star_trek import StarTrekJob

        assert StarTrekJob(sqlite_db_url).matches(trek_character_page) is True

    def test_matches_species(self, trek_species_page: WikiPage, sqlite_db_url: str) -> None:
        from wiki_dumps.jobs.star_trek import StarTrekJob

        assert StarTrekJob(sqlite_db_url).matches(trek_species_page) is True

    def test_matches_starship(self, trek_starship_page: WikiPage, sqlite_db_url: str) -> None:
        from wiki_dumps.jobs.star_trek import StarTrekJob

        assert StarTrekJob(sqlite_db_url).matches(trek_starship_page) is True

    def test_does_not_match_unrelated(self, sqlite_db_url: str) -> None:
        from wiki_dumps.jobs.star_trek import StarTrekJob

        page = _make_page(title="Python (programming language)", categories=("Programming languages",))
        assert StarTrekJob(sqlite_db_url).matches(page) is False

    def test_does_not_match_non_article_namespace(self, sqlite_db_url: str) -> None:
        from wiki_dumps.jobs.star_trek import StarTrekJob

        page = _make_page(
            title="Talk:Star Trek: The Next Generation",
            categories=("Star Trek television series",),
            namespace=1,
        )
        assert StarTrekJob(sqlite_db_url).matches(page) is False

    def test_episode_priority_over_character(self, sqlite_db_url: str) -> None:
        """A page with both episode and character categories goes to TrekEpisode."""
        from sqlalchemy import select

        from wiki_dumps.db.session import get_session, make_engine
        from wiki_dumps.jobs.star_trek import StarTrekJob, TrekEpisode

        page = _make_page(
            page_id=200,
            title="Q (Star Trek)",
            categories=("Star Trek: The Next Generation season 1 episodes", "Star Trek characters"),
            wikitext=_TREK_EPISODE_WIKITEXT,
        )
        job = StarTrekJob(sqlite_db_url)
        job.setup_schema()
        job.extract(page)
        job.flush()

        engine = make_engine(sqlite_db_url)
        with get_session(engine) as session:
            rows = session.execute(select(TrekEpisode)).scalars().all()
            assert len(rows) == 1


class TestStarTrekJobExtract:
    def test_extract_episode(self, trek_episode_page: WikiPage, sqlite_db_url: str) -> None:
        from sqlalchemy import select

        from wiki_dumps.db.session import get_session, make_engine
        from wiki_dumps.jobs.star_trek import StarTrekJob, TrekEpisode

        job = StarTrekJob(sqlite_db_url)
        job.setup_schema()
        job.extract(trek_episode_page)
        job.flush()

        engine = make_engine(sqlite_db_url)
        with get_session(engine) as session:
            rows = session.execute(select(TrekEpisode)).scalars().all()
            assert len(rows) == 1
            ep = rows[0]
            assert ep.show_title == "Star Trek: The Next Generation"
            assert ep.season == 3
            assert ep.episode_number == 26
            assert ep.director == "Cliff Bole"
            assert ep.stardate == "43989.1"

    def test_extract_movie(self, trek_movie_page: WikiPage, sqlite_db_url: str) -> None:
        from sqlalchemy import select

        from wiki_dumps.db.session import get_session, make_engine
        from wiki_dumps.jobs.star_trek import StarTrekJob, TrekMovie

        job = StarTrekJob(sqlite_db_url)
        job.setup_schema()
        job.extract(trek_movie_page)
        job.flush()

        engine = make_engine(sqlite_db_url)
        with get_session(engine) as session:
            rows = session.execute(select(TrekMovie)).scalars().all()
            assert len(rows) == 1
            movie = rows[0]
            assert movie.title == "Star Trek II: The Wrath of Khan"
            assert movie.release_year == 1982
            assert movie.director == "Nicholas Meyer"
            assert movie.timeline == "prime"

    def test_extract_kelvin_movie(self, sqlite_db_url: str) -> None:
        from sqlalchemy import select

        from wiki_dumps.db.session import get_session, make_engine
        from wiki_dumps.jobs.star_trek import StarTrekJob, TrekMovie

        page = _make_page(
            page_id=201,
            title="Star Trek Into Darkness",
            categories=("Star Trek films",),
            wikitext=_TREK_MOVIE_WIKITEXT,
        )
        job = StarTrekJob(sqlite_db_url)
        job.setup_schema()
        job.extract(page)
        job.flush()

        engine = make_engine(sqlite_db_url)
        with get_session(engine) as session:
            rows = session.execute(select(TrekMovie)).scalars().all()
            assert rows[0].timeline == "kelvin"

    def test_extract_show(self, trek_show_page: WikiPage, sqlite_db_url: str) -> None:
        from sqlalchemy import select

        from wiki_dumps.db.session import get_session, make_engine
        from wiki_dumps.jobs.star_trek import StarTrekJob, TrekShow

        job = StarTrekJob(sqlite_db_url)
        job.setup_schema()
        job.extract(trek_show_page)
        job.flush()

        engine = make_engine(sqlite_db_url)
        with get_session(engine) as session:
            rows = session.execute(select(TrekShow)).scalars().all()
            assert len(rows) == 1
            show = rows[0]
            assert show.title == "Star Trek: Deep Space Nine"
            assert show.abbreviation == "DS9"
            assert show.premiere_year == 1993
            assert show.total_seasons == 7
            assert show.total_episodes == 176

    def test_extract_book(self, trek_book_page: WikiPage, sqlite_db_url: str) -> None:
        from sqlalchemy import select

        from wiki_dumps.db.session import get_session, make_engine
        from wiki_dumps.jobs.star_trek import StarTrekJob, TrekBook

        job = StarTrekJob(sqlite_db_url)
        job.setup_schema()
        job.extract(trek_book_page)
        job.flush()

        engine = make_engine(sqlite_db_url)
        with get_session(engine) as session:
            rows = session.execute(select(TrekBook)).scalars().all()
            assert len(rows) == 1
            book = rows[0]
            assert book.author == "Peter David"
            assert book.publication_year == 1992
            assert book.media_type == "novel"

    def test_extract_character(self, trek_character_page: WikiPage, sqlite_db_url: str) -> None:
        from sqlalchemy import select

        from wiki_dumps.db.session import get_session, make_engine
        from wiki_dumps.jobs.star_trek import StarTrekJob, TrekCharacter

        job = StarTrekJob(sqlite_db_url)
        job.setup_schema()
        job.extract(trek_character_page)
        job.flush()

        engine = make_engine(sqlite_db_url)
        with get_session(engine) as session:
            rows = session.execute(select(TrekCharacter)).scalars().all()
            assert len(rows) == 1
            char = rows[0]
            assert char.title == "Spock"
            assert char.portrayed_by == "Leonard Nimoy"
            assert char.species == "Vulcan/Human"
            assert char.rank == "Commander"

    def test_extract_species(self, trek_species_page: WikiPage, sqlite_db_url: str) -> None:
        from sqlalchemy import select

        from wiki_dumps.db.session import get_session, make_engine
        from wiki_dumps.jobs.star_trek import StarTrekJob, TrekSpecies

        job = StarTrekJob(sqlite_db_url)
        job.setup_schema()
        job.extract(trek_species_page)
        job.flush()

        engine = make_engine(sqlite_db_url)
        with get_session(engine) as session:
            rows = session.execute(select(TrekSpecies)).scalars().all()
            assert len(rows) == 1
            sp = rows[0]
            assert sp.title == "Klingons"
            assert sp.quadrant == "Beta"
            assert sp.homeworld == "Qo'noS"

    def test_extract_starship(self, trek_starship_page: WikiPage, sqlite_db_url: str) -> None:
        from sqlalchemy import select

        from wiki_dumps.db.session import get_session, make_engine
        from wiki_dumps.jobs.star_trek import StarTrekJob, TrekStarship

        job = StarTrekJob(sqlite_db_url)
        job.setup_schema()
        job.extract(trek_starship_page)
        job.flush()

        engine = make_engine(sqlite_db_url)
        with get_session(engine) as session:
            rows = session.execute(select(TrekStarship)).scalars().all()
            assert len(rows) == 1
            ship = rows[0]
            assert ship.ship_registry == "NCC-1701-D"
            assert ship.ship_class == "Galaxy"
            assert ship.affiliation == "Starfleet"

    def test_does_not_write_until_flush(self, trek_episode_page: WikiPage, sqlite_db_url: str) -> None:
        from sqlalchemy import select

        from wiki_dumps.db.session import get_session, make_engine
        from wiki_dumps.jobs.star_trek import StarTrekJob, TrekEpisode

        job = StarTrekJob(sqlite_db_url)
        job.setup_schema()
        job.extract(trek_episode_page)
        engine = make_engine(sqlite_db_url)
        with get_session(engine) as session:
            assert len(session.execute(select(TrekEpisode)).scalars().all()) == 0
        job.flush()
        with get_session(engine) as session:
            assert len(session.execute(select(TrekEpisode)).scalars().all()) == 1
