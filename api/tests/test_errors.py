"""Bad input is 400, failures are never 200, and exception text never leaks."""
import psycopg
import pytest

from conftest import DEFAULT_PASSWORD, SENSITIVE

# (module whose get_connection fails, method, path, json body, needs token)
DB_FAILURE_CASES = [
    ("auth", "POST", "/signup", {"username": "zed", "password": DEFAULT_PASSWORD}, False),
    ("auth", "POST", "/login", {"username": "zed", "password": DEFAULT_PASSWORD}, False),
    ("uploads", "GET", "/history", None, True),
    ("uploads", "POST", "/classify", {"image_url": "https://res.cloudinary.com/demo/image/upload/x.jpg"}, True),
    ("uploads", "POST", "/delete_upload", {"upload_id": 1}, True),
    ("uploads", "POST", "/toggle_favorite", {"upload_id": 1}, True),
    ("uploads", "POST", "/get-suggestions", {"destination": "formal"}, True),
    ("profile", "GET", "/profile", None, True),
    ("profile", "POST", "/profile", {"gender": "Female"}, True),
    ("interactions", "POST", "/interact", {"type": "like", "item": {"title": "x"}}, True),
    ("idea_search", "POST", "/search-ideas", {"idea": "party", "debug_no_serpapi": True}, True),
    ("chatbot", "POST", "/chatbot/query", {"query": "formal"}, True),
]


@pytest.mark.parametrize("module,method,path,body,needs_token", DB_FAILURE_CASES,
                         ids=[f"{c[1]} {c[2]}" for c in DB_FAILURE_CASES])
def test_database_failure_is_500_without_exception_text(
        client, alice, monkeypatch, app_modules, module, method, path, body, needs_token):
    def broken_connection(*args, **kwargs):
        raise psycopg.OperationalError(SENSITIVE)

    monkeypatch.setattr(getattr(app_modules, module), "get_connection", broken_connection)

    res = client.open(path, method=method, json=body,
                      headers=alice.headers if needs_token else {})

    assert res.status_code == 500
    assert SENSITIVE not in res.get_data(as_text=True)


def test_delete_upload_failure_is_not_200(client, alice, monkeypatch, app_modules):
    def broken_connection(*args, **kwargs):
        raise psycopg.OperationalError(SENSITIVE)

    monkeypatch.setattr(app_modules.uploads, "get_connection", broken_connection)

    res = client.post("/delete_upload", headers=alice.headers, json={"upload_id": 1})

    assert res.status_code != 200
    assert res.get_json()["status"] == "error"


# (method, path, json body or raw string)
BAD_INPUT_CASES = [
    ("POST", "/delete_upload", {}),
    ("POST", "/delete_upload", {"upload_id": "abc"}),
    ("POST", "/delete_upload", {"upload_id": True}),
    ("POST", "/toggle_favorite", {}),
    ("POST", "/toggle_favorite", {"upload_id": [1]}),
    ("POST", "/classify", {}),
    ("POST", "/classify", {"image_url": 42}),
    ("POST", "/get-suggestions", {}),
    ("POST", "/interact", {"type": "like", "item": "not-an-object"}),
    ("POST", "/interact", {"type": "love", "item": {"title": "x"}}),
    ("POST", "/chatbot/query", {}),
    ("POST", "/chatbot/query", {"query": 7}),
    ("POST", "/search-ideas", {}),
    ("POST", "/search-ideas", {"idea": ["party"]}),
    ("POST", "/profile", {"gender": {"nested": True}}),
    ("POST", "/delete_upload", "not json"),
    ("POST", "/classify", "not json"),
    ("POST", "/profile", "not json"),
    ("POST", "/interact", "not json"),
    ("POST", "/chatbot/query", "not json"),
    ("POST", "/search-ideas", "not json"),
]


@pytest.mark.parametrize("method,path,body", BAD_INPUT_CASES,
                         ids=[f"{m} {p} {b!r}" for m, p, b in BAD_INPUT_CASES])
def test_bad_input_is_400(client, alice, method, path, body):
    if isinstance(body, str):
        res = client.open(path, method=method, data=body, content_type="text/plain",
                          headers=alice.headers)
    else:
        res = client.open(path, method=method, json=body, headers=alice.headers)

    assert res.status_code == 400


def test_shopping_provider_error_text_is_not_returned(client, alice, monkeypatch, app_modules):
    class FailingSearch:
        def __init__(self, params):
            pass

        def get_dict(self):
            return {"error": f"Invalid API key. {SENSITIVE}"}

    monkeypatch.setattr(app_modules.idea_search.Config, "SERPAPI_KEY", "test-key")
    monkeypatch.setattr(app_modules.idea_search, "GoogleSearch", FailingSearch)

    res = client.post("/search-ideas", headers=alice.headers, json={"idea": "party"})

    assert res.status_code == 502
    assert SENSITIVE not in res.get_data(as_text=True)
