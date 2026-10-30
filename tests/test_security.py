import psycopg
import pytest

from tests.test_pipeline import add_user, mark_succeeded_before, nov_meeting, run_once


def as_user(conn, uid):
    conn.execute("set local role authenticated")
    conn.execute("select set_config('request.jwt.claim.sub', %s, true)", (str(uid),))


def test_team_member_can_read_review_and_edit_keywords(conn, fetcher):
    mark_succeeded_before(conn)
    pid = run_once(conn, fetcher, [nov_meeting(documents=[])]).new[0]
    alice = add_user(conn, "alice@example.org")
    conn.commit()
    as_user(conn, alice)
    assert conn.execute("select status from posting_status where id = %s", (pid,)).fetchone()[0] == "new"
    conn.execute("insert into reviews (posting_id, note) values (%s, 'looks fine')", (pid,))
    conn.execute("insert into keywords (term) values ('Acme')")
    assert conn.execute("select count(*) from matches m join keywords k on k.id = m.keyword_id "
                        "where k.term = 'Acme'").fetchone()[0] == 1
    conn.execute("update user_prefs set email_mode = 'daily' where user_id = %s", (alice,))
    assert conn.execute("select status, last_reviewed_by_email from posting_status where id = %s",
                        (pid,)).fetchone() == ("reviewed", "alice@example.org")


def test_cannot_review_as_someone_else(conn, fetcher):
    mark_succeeded_before(conn)
    pid = run_once(conn, fetcher, [nov_meeting(documents=[])]).new[0]
    alice, bob = add_user(conn, "alice@example.org"), add_user(conn, "bob@example.org")
    conn.commit()
    as_user(conn, alice)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("insert into reviews (posting_id, user_id) values (%s, %s)", (pid, bob))


def test_cannot_change_someone_elses_prefs_or_scraper_data(conn):
    alice, bob = add_user(conn, "alice@example.org"), add_user(conn, "bob@example.org")
    conn.commit()
    as_user(conn, alice)
    conn.execute("update user_prefs set email_mode = 'immediate' where user_id = %s", (bob,))
    conn.execute("update agencies set name = 'x'")
    conn.execute("reset role")
    assert conn.execute("select email_mode from user_prefs where user_id = %s", (bob,)).fetchone()[0] == "none"
    assert conn.execute("select count(*) from agencies where name = 'x'").fetchone()[0] == 0
