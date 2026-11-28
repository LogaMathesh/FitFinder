"""Login/signup issue a JWT; protected routes reject missing or bad tokens."""
import datetime
import hashlib
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from authlib.integrations.base_client.errors import OAuthError
from flask import redirect

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


def install_fake_google(app, auth_module, monkeypatch, *, userinfo=None, error=None):
    app.config.update({
        "GOOGLE_CLIENT_ID": "test-client-id",
        "GOOGLE_CLIENT_SECRET": "test-client-secret",
        "GOOGLE_REDIRECT_URI": "http://localhost:5000/auth/google/callback",
        "SECRET_KEY": "test-only-flask-session-secret-0123456789",
    })

    class FakeGoogle:
        def authorize_redirect(self, redirect_uri):
            if error:
                raise error
            assert redirect_uri == app.config["GOOGLE_REDIRECT_URI"]
            return redirect("https://accounts.google.com/")

        def authorize_access_token(self):
            if error:
                raise error
            return {"userinfo": userinfo}

    monkeypatch.setattr(auth_module.oauth, "google", FakeGoogle(), raising=False)


def oauth_fragment_values(response):
    return parse_qs(urlsplit(response.headers["Location"]).fragment)


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
    assert body["onboarding_required"] is True
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


def test_google_login_requires_configured_credentials(client):
    response = client.get("/auth/google")

    assert response.status_code == 302
    assert oauth_fragment_values(response) == {"oauth_error": ["not_configured"]}


def test_google_signup_redirects_errors_to_signup(client):
    response = client.get("/auth/google?next=signup")

    assert response.status_code == 302
    assert response.headers["Location"].startswith(
        f'{client.application.config["FRONTEND_URL"].rstrip("/")}/signup#'
    )
    assert oauth_fragment_values(response) == {"oauth_error": ["not_configured"]}


def test_google_login_uses_configured_callback_uri(client, app, app_modules, monkeypatch):
    install_fake_google(app, app_modules.auth, monkeypatch)

    response = client.get("/auth/google")

    assert response.status_code == 302
    assert response.headers["Location"] == "https://accounts.google.com/"


def test_google_login_redirects_when_provider_start_fails(
    client, app, app_modules, monkeypatch
):
    install_fake_google(
        app, app_modules.auth, monkeypatch,
        error=OAuthError(error="provider_unavailable"),
    )

    response = client.get("/auth/google")

    assert response.status_code == 302
    assert oauth_fragment_values(response) == {"oauth_error": ["google_auth_failed"]}


def test_google_callback_creates_account_and_exchanges_single_use_code(
    client, app, app_modules, monkeypatch, db
):
    install_fake_google(
        app, app_modules.auth, monkeypatch,
        userinfo={
            "sub": "google-user-123",
            "email": "new.user@example.com",
            "email_verified": True,
        },
    )

    callback = client.get("/auth/google/callback")
    values = oauth_fragment_values(callback)

    assert callback.status_code == 302
    assert set(values) == {"oauth_code"}
    code = values["oauth_code"][0]
    assert callback.headers["Cache-Control"] == "no-store"
    assert callback.headers["Referrer-Policy"] == "no-referrer"
    assert db.query("SELECT code_hash FROM oauth_login_codes") == [
        (hashlib.sha256(code.encode("utf-8")).hexdigest(),)
    ]
    assert db.query(
        "SELECT username, email, google_sub, password_hash FROM users"
    ) == [("new.user@example.com", "new.user@example.com", "google-user-123", None)]

    exchange = client.post("/auth/google/exchange", json={"code": code})

    assert exchange.status_code == 200
    body = exchange.get_json()
    claims = decode(body["token"])
    assert body["user"] == "new.user@example.com"
    assert body["onboarding_required"] is True
    assert claims["sub"] == str(db.query("SELECT id FROM users")[0][0])
    assert claims["username"] == body["user"]
    assert exchange.headers["Cache-Control"] == "no-store"
    assert client.get("/history", headers={"Authorization": f"Bearer {body['token']}"}).status_code == 200
    assert client.post("/login", json={
        "username": body["user"], "password": DEFAULT_PASSWORD,
    }).status_code == 401

    replay = client.post("/auth/google/exchange", json={"code": code})
    assert replay.status_code == 400


def test_google_callback_links_existing_username_email_account(
    client, app, app_modules, monkeypatch, db
):
    email = "alice@example.com"
    user_id = db.create_user(email)
    install_fake_google(
        app, app_modules.auth, monkeypatch,
        userinfo={"sub": "google-alice", "email": email, "email_verified": True},
    )

    callback = client.get("/auth/google/callback")
    code = oauth_fragment_values(callback)["oauth_code"][0]
    exchange = client.post("/auth/google/exchange", json={"code": code})

    assert exchange.status_code == 200
    assert exchange.get_json()["onboarding_required"] is False
    assert decode(exchange.get_json()["token"])["sub"] == str(user_id)
    assert db.query("SELECT email, google_sub FROM users WHERE id = %s", (user_id,)) == [
        (email, "google-alice")
    ]


def test_google_callback_rejects_unverified_email(
    client, app, app_modules, monkeypatch, db
):
    install_fake_google(
        app, app_modules.auth, monkeypatch,
        userinfo={"sub": "unverified-user", "email": "person@example.com", "email_verified": False},
    )

    callback = client.get("/auth/google/callback")

    assert oauth_fragment_values(callback) == {"oauth_error": ["google_auth_failed"]}
    assert db.query("SELECT id FROM users") == []


def test_google_callback_rejects_email_linked_to_another_google_subject(
    client, app, app_modules, monkeypatch, db
):
    email = "existing@example.com"
    user_id = db.create_user(email)
    db.query(
        "UPDATE users SET email = %s, google_sub = %s WHERE id = %s",
        (email, "already-linked-sub", user_id),
    )
    install_fake_google(
        app, app_modules.auth, monkeypatch,
        userinfo={"sub": "different-sub", "email": email, "email_verified": True},
    )

    callback = client.get("/auth/google/callback")

    assert oauth_fragment_values(callback) == {"oauth_error": ["account_conflict"]}
    assert db.query("SELECT google_sub FROM users WHERE id = %s", (user_id,)) == [
        ("already-linked-sub",)
    ]


def test_google_callback_handles_authlib_state_or_provider_errors(
    client, app, app_modules, monkeypatch
):
    install_fake_google(
        app, app_modules.auth, monkeypatch,
        error=OAuthError(error="invalid_state"),
    )

    callback = client.get("/auth/google/callback")

    assert oauth_fragment_values(callback) == {"oauth_error": ["google_auth_failed"]}


def test_google_callback_rejects_missing_oauth_state(client, app, app_modules):
    app.config.update({
        "GOOGLE_CLIENT_ID": "test-client-id",
        "GOOGLE_CLIENT_SECRET": "test-client-secret",
        "GOOGLE_REDIRECT_URI": "http://localhost:5000/auth/google/callback",
        "SECRET_KEY": "test-only-flask-session-secret-0123456789",
    })
    app_modules.auth.init_oauth(app)

    callback = client.get("/auth/google/callback?code=must-not-be-used")

    assert oauth_fragment_values(callback) == {"oauth_error": ["google_auth_failed"]}


@pytest.mark.parametrize("body", [{}, {"code": 123}, {"code": ""}, {"code": "x" * 129}])
def test_google_code_exchange_rejects_invalid_input(client, body):
    response = client.post("/auth/google/exchange", json=body)

    assert response.status_code == 400
    assert "token" not in response.get_json()


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
