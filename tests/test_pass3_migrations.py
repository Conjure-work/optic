"""Round three's migrations (23 to 27) are additive over a database that already holds readers' data.

This is the check run before the evaluation copy is redeployed in place: a database is built at migration 22, filled
with rows in every table round three touches, then migrated; every value that was there must read back unchanged,
every new column must be empty or its default, and nothing may be dropped. Rollback to the Pass 2 head stays valid
only while this holds (the Pass 2 code never reads the new columns or tables).
"""

import sqlite3

import pytest

from app import db as accounts_db

ROUND_THREE = (23, 24, 25, 26, 27)


def _dump(conn, table):
    cols = [r[1] for r in conn.execute("PRAGMA table_info({})".format(table))]
    rows = conn.execute("SELECT * FROM {} ORDER BY rowid".format(table)).fetchall()
    return cols, [tuple(r) for r in rows]


@pytest.fixture
def at_22(tmp_path, monkeypatch):
    monkeypatch.setattr(accounts_db, "DB_PATH", str(tmp_path / "accounts.db"))
    full = list(accounts_db.MIGRATIONS)
    monkeypatch.setattr(accounts_db, "MIGRATIONS", [m for m in full if m[0] <= 22])
    accounts_db.migrate()
    now = accounts_db.utcnow()
    with accounts_db.cursor(write=True) as c:
        for uid in ("u1", "u2"):
            c.execute("INSERT INTO users (id, email, first_name, created_at, updated_at) VALUES (?,?,?,?,?)",
                      (uid, uid + "@example.test", uid, now, now))
            c.execute("INSERT INTO user_preferences (user_id, updated_at, knowledge_level) VALUES (?,?,?)",
                      (uid, now, "advanced"))
            c.execute("INSERT INTO watchlists (id, user_id, name, position, created_at, updated_at) "
                      "VALUES (?,?,?,?,?,?)", ("w-" + uid, uid, "Main", 0, now, now))
            c.execute("INSERT INTO watchlist_items (id, watchlist_id, symbol, created_at) VALUES (?,?,?,?)",
                      ("i-" + uid, "w-" + uid, "AAPL", now))
            c.execute("INSERT INTO saved_research (id, user_id, title, symbol, content, created_at, updated_at) "
                      "VALUES (?,?,?,?,?,?,?)", ("r-" + uid, uid, "Note", "MSFT", "text", now, now))
    monkeypatch.setattr(accounts_db, "MIGRATIONS", full)
    return accounts_db


def test_round_three_migrations_are_numbered_23_to_27_and_follow_22():
    versions = [m[0] for m in accounts_db.MIGRATIONS]
    assert versions == list(range(1, 30))      # 28 and 29 are the audit round's cancel_at and cancel_synced_at columns
    assert tuple(versions[-7:-2]) == ROUND_THREE


def test_round_three_migrations_never_drop_or_rebuild_anything():
    for version, _name, statements in accounts_db.MIGRATIONS:
        if version not in ROUND_THREE:
            continue
        for sql in statements:
            head = " ".join(sql.split()).upper()
            assert not head.startswith(("DROP", "DELETE")), (version, sql)
            assert "RENAME" not in head, (version, sql)
            if head.startswith("ALTER TABLE"):
                assert " ADD COLUMN " in head, (version, sql)
            if head.startswith("UPDATE"):
                # the only update allowed is filling the new owner column from the row's own user
                assert "SET OWNER_ID = USER_ID WHERE OWNER_ID IS NULL" in head, (version, sql)


def test_migrating_from_22_keeps_every_existing_value(at_22):
    db = at_22
    tables = ("users", "user_preferences", "watchlists", "watchlist_items", "saved_research")
    with sqlite3.connect(db.DB_PATH) as conn:
        before = {t: _dump(conn, t) for t in tables}
    ran = db.migrate()
    assert ran == list(ROUND_THREE) + [28, 29]
    with sqlite3.connect(db.DB_PATH) as conn:
        for t in tables:
            cols_b, rows_b = before[t]
            cols_a, rows_a = _dump(conn, t)
            assert cols_a[:len(cols_b)] == cols_b, t          # old columns kept, in order
            assert len(rows_a) == len(rows_b), t
            for old, new in zip(rows_b, rows_a):
                assert new[:len(old)] == old, t                # every old value unchanged


def test_owner_shape_is_set_to_each_rows_own_user(at_22):
    db = at_22
    db.migrate()
    for table in ("watchlists", "saved_research"):
        rows = db.rows("SELECT user_id, owner_kind, owner_id FROM {}".format(table))
        assert rows and all(r["owner_kind"] == "user" and r["owner_id"] == r["user_id"] for r in rows), table


def test_new_preference_columns_start_empty(at_22):
    db = at_22
    db.migrate()
    for r in db.rows("SELECT favourite_intervals, milo_stance, level_quiz, alert_email, knowledge_level "
                     "FROM user_preferences"):
        assert r["favourite_intervals"] is None and r["milo_stance"] is None
        assert r["level_quiz"] is None and r["alert_email"] is None
        assert r["knowledge_level"] == "advanced"


def test_new_tables_cascade_with_the_account(accounts):
    now = accounts.utcnow()
    accounts.execute("INSERT INTO users (id, email, created_at, updated_at) VALUES ('u9','u9@example.test',?,?)",
                     (now, now))
    accounts.execute("INSERT INTO chart_layouts (id, user_id, name, count, slots, created_at, updated_at) "
                     "VALUES ('c1','u9','Two',2,'[]',?,?)", (now, now))
    accounts.execute("INSERT INTO watch_delivery (hit_id, user_id, sent_at) VALUES ('h1','u9',?)", (now,))
    accounts.execute("DELETE FROM users WHERE id='u9'")
    assert accounts.rows("SELECT * FROM chart_layouts") == []
    assert accounts.rows("SELECT * FROM watch_delivery") == []


def _user(accounts, uid="p1"):
    now = accounts.utcnow()
    accounts.execute("INSERT INTO users (id, email, created_at, updated_at) VALUES (?,?,?,?)",
                     (uid, uid + "@example.test", now, now))
    return uid


def test_round_three_preferences_store_only_what_a_page_can_read(accounts):
    from app.auth import store
    uid = _user(accounts)
    assert store.round_three_preferences(uid) == {"favourite_intervals": None, "milo_stance": None,
                                                  "level_quiz": None, "alert_email": False}
    out = store.set_round_three_preferences(uid, {
        "favourite_intervals": ["5m", "1h", "1d", "bogus", "1h"], "milo_stance": "stoic",
        "level_quiz": {"shown": True, "suggested": "beginner", "outcome": "accepted", "answers": ["secret"]},
        "alert_email": True})
    assert out["favourite_intervals"] == ["5m", "1h", "1d"]
    assert out["milo_stance"] == "stoic" and out["alert_email"] is True
    assert out["level_quiz"]["suggested"] == "beginner" and "answers" not in out["level_quiz"]
    # unknown values are dropped, never stored
    out = store.set_round_three_preferences(uid, {"milo_stance": "bullish", "alert_email": "yes",
                                                  "level_quiz": {"suggested": "guru"}})
    assert out["milo_stance"] == "stoic" and out["alert_email"] is True and out["level_quiz"]["outcome"] == "accepted"


def test_migration_28_adds_subscriptions_cancel_at_on_a_database_at_27_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(accounts_db, "DB_PATH", str(tmp_path / "accounts.db"))
    full = list(accounts_db.MIGRATIONS)
    monkeypatch.setattr(accounts_db, "MIGRATIONS", [m for m in full if m[0] <= 27])
    accounts_db.migrate()
    with sqlite3.connect(accounts_db.DB_PATH) as c:
        assert "cancel_at" not in [r[1] for r in c.execute("PRAGMA table_info(subscriptions)")]
    monkeypatch.setattr(accounts_db, "MIGRATIONS", full)
    assert accounts_db.migrate() == [28, 29]
    assert accounts_db.migrate() == []
    with sqlite3.connect(accounts_db.DB_PATH) as c:
        assert "cancel_at" in [r[1] for r in c.execute("PRAGMA table_info(subscriptions)")]


def test_migration_29_adds_only_cancel_synced_at_and_leaves_existing_rows_null(tmp_path, monkeypatch):
    monkeypatch.setattr(accounts_db, "DB_PATH", str(tmp_path / "accounts.db"))
    full = list(accounts_db.MIGRATIONS)
    monkeypatch.setattr(accounts_db, "MIGRATIONS", [m for m in full if m[0] <= 28])
    accounts_db.migrate()
    with sqlite3.connect(accounts_db.DB_PATH) as c:
        c.execute("INSERT INTO users (id, email, created_at, updated_at) VALUES ('u1','a@example.com','t','t')")
        c.execute("INSERT INTO subscriptions (id, user_id, plan, status, created_at, updated_at) "
                  "VALUES ('s1','u1','pro','active','t','t')")
    monkeypatch.setattr(accounts_db, "MIGRATIONS", full)
    assert accounts_db.migrate() == [29]
    assert accounts_db.migrate() == []
    assert accounts_db.MIGRATIONS[-1] == (29, "subscription_cancel_synced",
                                          ["ALTER TABLE subscriptions ADD COLUMN cancel_synced_at TEXT"])
    with sqlite3.connect(accounts_db.DB_PATH) as c:
        assert c.execute("SELECT cancel_synced_at FROM subscriptions WHERE id='s1'").fetchone() == (None,)
