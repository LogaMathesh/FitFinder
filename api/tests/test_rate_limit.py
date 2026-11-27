"""Per-user rate limits on the paid endpoints, and the /usage endpoint."""
from concurrent.futures import ThreadPoolExecutor

import psycopg

from conftest import SENSITIVE

CHAT = ("/chatbot/query", {"query": "something formal"})
IDEA = ("/search-ideas", {"idea": "rooftop party", "debug_no_serpapi": True})


def call(client, user, endpoint):
    path, body = endpoint
    return client.post(path, headers=user.headers, json=body)


def used_rows(db, username, action):
    return db.query(
        "SELECT count(*) FROM api_usage WHERE username = %s AND action = %s",
        (username, action),
    )[0][0]


def test_chatbot_allows_five_then_429(client, alice):
    remaining = []
    for _ in range(5):
        res = call(client, alice, CHAT)
        assert res.status_code == 200
        remaining.append(res.get_json()["usage"]["remaining"])
    assert remaining == [4, 3, 2, 1, 0]

    res = call(client, alice, CHAT)
    assert res.status_code == 429
    body = res.get_json()
    assert body["error"] == "rate_limited"
    assert "5 chats" in body["message"]
    assert body["usage"] == {"limit": 5, "used": 5, "remaining": 0,
                             "reset_in_seconds": body["retry_after_seconds"]}
    assert 1700 < int(res.headers["Retry-After"]) <= 1800


def test_idea_search_allows_two_then_429(client, alice):
    for expected in (1, 0):
        res = call(client, alice, IDEA)
        assert res.status_code == 200
        assert res.get_json()["usage"]["remaining"] == expected

    res = call(client, alice, IDEA)
    assert res.status_code == 429
    assert "2 idea searches" in res.get_json()["message"]
    assert "Retry-After" in res.headers


def test_limit_does_not_record_rejected_calls(client, db, alice):
    for _ in range(3):
        call(client, alice, IDEA)
    assert used_rows(db, alice.username, "idea_search") == 2


def test_users_have_separate_limits(client, alice, bob):
    for _ in range(2):
        call(client, alice, IDEA)
    assert call(client, alice, IDEA).status_code == 429
    assert call(client, bob, IDEA).status_code == 200


def test_actions_have_separate_limits(client, alice):
    for _ in range(2):
        call(client, alice, IDEA)
    assert call(client, alice, IDEA).status_code == 429
    assert call(client, alice, CHAT).status_code == 200


def test_old_calls_leave_the_window(client, db, alice):
    for _ in range(2):
        call(client, alice, IDEA)
    assert call(client, alice, IDEA).status_code == 429

    db.query("UPDATE api_usage SET created_at = now() - interval '31 minutes'")

    res = call(client, alice, IDEA)
    assert res.status_code == 200
    assert res.get_json()["usage"]["remaining"] == 1


def test_bad_input_uses_no_credit(client, db, alice):
    assert client.post("/chatbot/query", headers=alice.headers, json={"query": "  "}).status_code == 400
    assert client.post("/search-ideas", headers=alice.headers, json={}).status_code == 400
    assert db.query("SELECT count(*) FROM api_usage")[0][0] == 0


def test_unauthenticated_call_uses_no_credit(client, db):
    path, body = CHAT
    assert client.post(path, json=body).status_code == 401
    assert db.query("SELECT count(*) FROM api_usage")[0][0] == 0


def test_server_error_is_refunded(client, db, alice, monkeypatch, app_modules):
    def broken_connection(*args, **kwargs):
        raise psycopg.OperationalError(SENSITIVE)

    monkeypatch.setattr(app_modules.chatbot, "get_connection", broken_connection)

    assert call(client, alice, CHAT).status_code == 500
    assert used_rows(db, alice.username, "chatbot") == 0


def test_limiter_failure_is_500_and_blocks_the_call(client, alice, monkeypatch, external_services):
    import rate_limit

    def broken_connection(*args, **kwargs):
        raise psycopg.OperationalError(SENSITIVE)

    monkeypatch.setattr(rate_limit, "get_connection", broken_connection)

    res = call(client, alice, CHAT)
    assert res.status_code == 500
    assert SENSITIVE not in res.get_data(as_text=True)
    assert external_services.matched == []


def test_concurrent_requests_cannot_exceed_the_limit(client, db, alice):
    with ThreadPoolExecutor(max_workers=6) as pool:
        statuses = list(pool.map(lambda _: call(client, alice, IDEA).status_code, range(6)))

    assert statuses.count(200) == 2
    assert statuses.count(429) == 4
    assert used_rows(db, alice.username, "idea_search") == 2


def test_limits_come_from_config(client, app, alice):
    app.config["IDEA_SEARCH_RATE_LIMIT"] = 1
    assert call(client, alice, IDEA).status_code == 200
    assert call(client, alice, IDEA).status_code == 429


# --- GET /usage -------------------------------------------------------------
def test_usage_starts_full(client, alice):
    res = client.get("/usage", headers=alice.headers)
    assert res.status_code == 200
    assert res.get_json() == {
        "chatbot": {"limit": 5, "used": 0, "remaining": 5, "reset_in_seconds": None},
        "idea_search": {"limit": 2, "used": 0, "remaining": 2, "reset_in_seconds": None},
    }


def test_usage_reflects_calls_and_uses_no_credit(client, db, alice):
    call(client, alice, CHAT)
    call(client, alice, CHAT)

    for _ in range(3):
        body = client.get("/usage", headers=alice.headers).get_json()

    assert body["chatbot"]["used"] == 2
    assert body["chatbot"]["remaining"] == 3
    assert 1700 < body["chatbot"]["reset_in_seconds"] <= 1800
    assert body["idea_search"]["remaining"] == 2
    assert used_rows(db, alice.username, "chatbot") == 2


def test_usage_is_per_user(client, alice, bob):
    call(client, alice, CHAT)
    assert client.get("/usage", headers=bob.headers).get_json()["chatbot"]["used"] == 0


def test_usage_requires_auth(client):
    assert client.get("/usage").status_code == 401
