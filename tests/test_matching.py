import pytest


def matches(conn, term, match_type, text):
    return conn.execute(
        "select %s ~* keyword_pattern(%s, %s)", (text, term, match_type)
    ).fetchone()[0]


@pytest.mark.parametrize("text,expected", [
    ("Approve the charter petition", True),
    ("CHARTER SCHOOLS", True),
    ("two charters were renewed", True),
    ("the charter's renewal", True),
    ("a chartered bus", False),
    ("supercharter", False),
])
def test_word_matches_whole_word_and_plurals(conn, text, expected):
    assert matches(conn, "charter", "word", text) is expected


def test_phrase_tolerates_whitespace_and_escapes_specials(conn):
    assert matches(conn, "SB 740", "phrase", "Funding under SB\n 740 determinations")
    assert not matches(conn, "SB 740", "phrase", "SB 7400")
    assert matches(conn, "A.B. 1505", "phrase", "per A.B. 1505")
    assert not matches(conn, "A.B. 1505", "phrase", "per AxBx 1505")


def test_starter_regex_for_prop_39(conn):
    term = conn.execute("select term from keywords where match_type = 'regex'").fetchone()[0]
    for text in ("Prop 39 facilities", "Proposition 39", "Prop. 39 request"):
        assert matches(conn, term, "regex", text), text
    assert not matches(conn, term, "regex", "Prop 390")


def test_invalid_regex_keyword_is_rejected(conn):
    import psycopg
    with pytest.raises(psycopg.errors.InvalidRegularExpression):
        conn.execute("insert into keywords (term, match_type) values ('(unclosed', 'regex')")
