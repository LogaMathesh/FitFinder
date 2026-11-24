"""Login/signup issue a JWT; protected routes reject missing or bad tokens."""
import datetime

import jwt
import pytest

from conftest import DEFAULT_PASSWORD, TEST_JWT_SECRET

# Every route that reads or writes user data, plus the admin-only routes.
PROTECTED_ROUTES = [
    ("GET", "/history", None),
    ("POST", "/classify", {"image_url": "https://res.cloudinary.com/demo/image/upload/a.jpg"}),
    ("POST", "/delete_upload", {"upload_id": 1}),
    ("POST", "/toggle_favorite", {"upload_id": 1}),
    ("POST", "/get-suggestions", {"destination": "formal"}),
    ("GET", "/profile", None),
    ("POST", "/profile", {"gender": "Female"}),
    ("POST", "/interact", {"type": "like", "item": {"title": "Blazer"}}),
    ("POST", "/search-ideas", {"idea": "rooftop party", "debug_no_serpapi": True}),
    ("POST", "/chatbot/query", {"query": "something formal"}),
    ("GET", "/check-duplicates", None),
    ("POST", "/clean-duplicates", None),
    ("POST", "/index-existing-images", {"username": "alice"}),
]
ROUTE_IDS = [f"{method} {path}" for method, path, _ in PROTECTED_ROUTES]


def call(client, method, path, body=None, headers=None):
    return client.open(path, method=method, json=body, headers=headers or {})


def decode(token):
    return jwt.decode(token, TEST_JWT_SECRET, algorithms=["HS256"])


# --- Token issuance ---------------------------------------------------------
def test_login_returns_short_lived_hs256_token(client, db):
    user_id = db.create_user("alice")

    res = client.post("/login", json={"username": "alice", "password": DEFAULT_PASSWORD})

    assert res.status_code == 200
    body = res.get_json()
    assert body["user"] == "alice"
    assert jwt.get_unverified_header(body["token"])["alg"] == "HS256"
    claims = decode(body["token"])
    assert claims["sub"] == str(user_id)
    assert claims["username"] == "alice"
    lifetime = claims["exp"] - claims["iat"]
    assert 0 < lifetime <= 60 * 60, "token expiry must be short (at most 60 minutes here)"


def test_signup_returns_token_for_new_user(client, db):
    res = client.post("/signup", json={"username": "carol", "password": DEFAULT_PASSWORD})

    assert res.status_code == 200
    body = res.get_json()
    assert body["user"] == "carol"
    claims = decode(body["token"])
    assert claims["username"] == "carol"
    assert claims["sub"] == str(db.query("SELECT id FROM users WHERE username = 'carol'")[0][0])


def test_token_from_login_is_accepted_by_a_protected_route(client, db):
    db.create_user("alice")
    token = client.post("/login", json={"username": "alice", "password": DEFAULT_PASSWORD}).get_json()["token"]

    res = client.get("/history", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200
    assert res.get_json() == []


def test_login_with_wrong_password_is_401_without_token(client, db):
    db.create_user("alice")

    res = client.post("/login", json={"username": "alice", "password": "wrong"})

    assert res.status_code == 401
    assert "token" not in res.get_json()


def test_login_for_unknown_user_is_401(client, db):
    res = client.post("/login", json={"username": "nobody", "password": "whatever"})

    assert res.status_code == 401


# --- Missing or invalid tokens ----------------------------------------------
@pytest.mark.parametrize("method,path,body", PROTECTED_ROUTES, ids=ROUTE_IDS)
def test_protected_route_without_token_is_401(client, alice, method, path, body):
    res = call(client, method, path, body)

    assert res.status_code == 401


@pytest.mark.parametrize("method,path,body", PROTECTED_ROUTES, ids=ROUTE_IDS)
def test_username_in_body_or_query_is_not_a_credential(client, alice, method, path, body):
    """The old contract: identity sent by the client. It must no longer work."""
    spoofed = dict(body or {}, username="alice", user_id="alice")
    query_path = f"{path}?username=alice"

    res = call(client, method, query_path, spoofed if method == "POST" else None)

    assert res.status_code == 401


def bad_tokens(alice, make_token, unsigned_token):
    return {
        "garbage": "not-a-jwt",
        "wrong secret": make_token(alice.id, alice.username, secret="some-other-secret-0123456789abcdef"),
        "expired": make_token(alice.id, alice.username, expires_in=datetime.timedelta(seconds=-5)),
        "alg none": unsigned_token(alice.id, alice.username),
        "HS512 not HS256": make_token(alice.id, alice.username, algorithm="HS512"),
        "no exp claim": make_token(alice.id, alice.username, drop=("exp",)),
        "no sub claim": make_token(alice.id, alice.username, drop=("sub",)),
        "no username claim": make_token(alice.id, alice.username, drop=("username",)),
        "non-numeric sub": make_token("alice", alice.username),
    }


@pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")  # HS512 case
@pytest.mark.parametrize("kind", [
    "garbage", "wrong secret", "expired", "alg none", "HS512 not HS256",
    "no exp claim", "no sub claim", "no username claim", "non-numeric sub",
])
def test_invalid_token_is_401(client, alice, make_token, unsigned_token, kind):
    token = bad_tokens(alice, make_token, unsigned_token)[kind]

    res = client.get("/history", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 401


def test_token_without_bearer_scheme_is_401(client, alice):
    res = client.get("/history", headers={"Authorization": alice.token})

    assert res.status_code == 401


def test_token_in_query_string_is_not_accepted(client, alice):
    res = client.get(f"/history?token={alice.token}")

    assert res.status_code == 401


def test_cors_preflight_does_not_require_a_token(client):
    res = client.options("/profile", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Authorization, Content-Type",
    })

    assert res.status_code == 200
    assert "authorization" in res.headers.get("Access-Control-Allow-Headers", "").lower()


def test_public_status_route_needs_no_token(client):
    assert client.get("/chatbot/status").status_code == 200


# --- Signup/login status codes ---------------------------------------------
def test_duplicate_signup_is_409_without_database_details(client, db):
    db.create_user("alice")

    res = client.post("/signup", json={"username": "alice", "password": DEFAULT_PASSWORD})

    assert res.status_code == 409
    text = res.get_data(as_text=True).lower()
    assert "duplicate key" not in text
    assert "unique" not in text


@pytest.mark.parametrize("body", [
    {},
    {"username": "dave"},
    {"password": DEFAULT_PASSWORD},
    {"username": "", "password": DEFAULT_PASSWORD},
    {"username": "dave", "password": ""},
    {"username": 123, "password": DEFAULT_PASSWORD},
    {"username": "dave", "password": ["not", "a", "string"]},
    {"username": "d" * 256, "password": DEFAULT_PASSWORD},
], ids=["empty", "no password", "no username", "blank username", "blank password",
        "numeric username", "list password", "username too long"])
@pytest.mark.parametrize("path", ["/signup", "/login"])
def test_signup_and_login_reject_bad_input_with_400(client, db, path, body):
    res = client.post(path, json=body)

    assert res.status_code == 400


@pytest.mark.parametrize("path", ["/signup", "/login"])
def test_signup_and_login_reject_non_json_body_with_400(client, db, path):
    res = client.post(path, data="username=alice", content_type="application/x-www-form-urlencoded")

    assert res.status_code == 400
