"""User B (bob) must not read, change or delete user A's (alice's) data.

Every attacking request carries bob's valid token AND tries to name alice in
the body or query string, which is how the old API decided whose data to use.
"""
import pytest

ALICE_IMG = "https://res.cloudinary.com/demo/image/upload/alice-blazer.jpg"
ALICE_IMG_2 = "https://res.cloudinary.com/demo/image/upload/alice-kurta.jpg"
BOB_IMG = "https://res.cloudinary.com/demo/image/upload/bob-tee.jpg"


@pytest.fixture
def alice_upload(db, alice):
    return db.create_upload(alice.username, ALICE_IMG, style="formal", favorite=False)


# --- History -----------------------------------------------------------------
def test_history_returns_only_the_callers_uploads(client, db, alice, bob, alice_upload):
    db.create_upload(bob.username, BOB_IMG)

    res = client.get("/history?username=alice", headers=bob.headers)

    assert res.status_code == 200
    urls = [item["image_url"] for item in res.get_json()]
    assert urls == [BOB_IMG]


def test_history_returns_own_uploads(client, alice, alice_upload):
    res = client.get("/history", headers=alice.headers)

    assert res.status_code == 200
    assert [item["id"] for item in res.get_json()] == [alice_upload]


def test_history_by_username_path_no_longer_exists(client, alice, bob, alice_upload):
    res = client.get(f"/history/{alice.username}", headers=bob.headers)

    assert res.status_code == 404
    assert ALICE_IMG not in res.get_data(as_text=True)


# --- Delete ------------------------------------------------------------------
def test_bob_cannot_delete_alices_upload(client, db, alice, bob, alice_upload):
    res = client.post("/delete_upload", headers=bob.headers,
                      json={"upload_id": alice_upload, "username": alice.username})

    assert res.status_code == 404
    assert db.upload(alice_upload) is not None


def test_owner_can_delete_own_upload(client, db, alice, alice_upload):
    res = client.post("/delete_upload", headers=alice.headers, json={"upload_id": alice_upload})

    assert res.status_code == 200
    assert res.get_json()["status"] == "success"
    assert db.upload(alice_upload) is None


def test_deleting_a_missing_upload_is_404(client, alice):
    res = client.post("/delete_upload", headers=alice.headers, json={"upload_id": 999999})

    assert res.status_code == 404


# --- Favorites ---------------------------------------------------------------
def test_bob_cannot_toggle_alices_favorite(client, db, alice, bob, alice_upload):
    res = client.post("/toggle_favorite", headers=bob.headers,
                      json={"upload_id": alice_upload, "username": alice.username})

    assert res.status_code == 404
    assert db.upload(alice_upload)["favorite"] is False


def test_owner_can_toggle_own_favorite(client, db, alice, alice_upload):
    res = client.post("/toggle_favorite", headers=alice.headers, json={"upload_id": alice_upload})

    assert res.status_code == 200
    assert res.get_json()["favorite"] is True
    assert db.upload(alice_upload)["favorite"] is True


# --- Classify (upload ingestion) --------------------------------------------
def test_classify_saves_upload_for_the_token_user(client, db, alice, bob):
    res = client.post("/classify", headers=bob.headers,
                      json={"image_url": BOB_IMG, "username": alice.username})

    assert res.status_code == 200
    assert db.uploads_of(bob.username) == [BOB_IMG]
    assert db.uploads_of(alice.username) == []


def test_classify_duplicate_check_is_per_user(client, db, alice, bob, alice_upload, external_services):
    """Bob re-using alice's URL must not be answered with alice's stored record."""
    res = client.post("/classify", headers=bob.headers, json={"image_url": ALICE_IMG})

    assert res.status_code == 200
    assert "Duplicate" not in res.get_json().get("message", "")
    assert db.uploads_of(bob.username) == [ALICE_IMG]
    assert external_services.analyzed == [ALICE_IMG]


# --- Suggestions -------------------------------------------------------------
def test_suggestions_only_come_from_the_callers_wardrobe(client, db, alice, bob, alice_upload):
    res = client.post("/get-suggestions", headers=bob.headers,
                      json={"destination": "formal", "username": alice.username})

    assert res.status_code == 200
    assert res.get_json()["suggestions"] == []


def test_suggestions_return_own_items(client, alice, alice_upload):
    res = client.post("/get-suggestions", headers=alice.headers, json={"destination": "formal"})

    assert res.status_code == 200
    assert [s["image_url"] for s in res.get_json()["suggestions"]] == [ALICE_IMG]


# --- Profile -----------------------------------------------------------------
def test_bob_cannot_read_alices_profile(client, db, alice, bob):
    db.create_profile(alice.username, gender="Female", sizes="ALICE-SIZE-S")

    res = client.get("/profile?username=alice", headers=bob.headers)

    assert res.status_code == 200
    assert "ALICE-SIZE-S" not in res.get_data(as_text=True)
    assert res.get_json()["sizes"] == ""


def test_bob_cannot_change_alices_profile(client, db, alice, bob):
    db.create_profile(alice.username, sizes="ALICE-SIZE-S")

    res = client.post("/profile", headers=bob.headers,
                      json={"username": alice.username, "sizes": "HIJACKED"})

    assert res.status_code == 200
    assert db.profile(alice.username)["sizes"] == "ALICE-SIZE-S"
    assert db.profile(bob.username)["sizes"] == "HIJACKED"


def test_owner_can_read_and_update_own_profile(client, db, alice):
    saved = client.post("/profile", headers=alice.headers, json={"gender": "Female", "sizes": "M"})
    fetched = client.get("/profile", headers=alice.headers)

    assert saved.status_code == 200
    assert fetched.get_json()["sizes"] == "M"
    assert db.profile(alice.username)["gender"] == "Female"


# --- Interactions ------------------------------------------------------------
def test_interaction_is_recorded_for_the_token_user(client, db, alice, bob):
    res = client.post("/interact", headers=bob.headers, json={
        "username": alice.username, "type": "like", "item": {"title": "Satin shirt"},
    })

    assert res.status_code == 200
    assert db.interactions_of(alice.username) == []
    assert db.interactions_of(bob.username) == [("Satin shirt", "like")]


def test_search_ideas_uses_only_the_callers_profile_and_history(client, db, alice, bob):
    # "sherwani" is a fashion keyword, so it would show up in the fallback query
    # if alice's profile were used for bob's search.
    db.create_profile(alice.username, style_preferences="sherwani")
    db.create_interaction(alice.username, "Embroidered sherwani", "save")

    res = client.post("/search-ideas", headers=bob.headers, json={
        "idea": "rooftop party", "username": alice.username, "debug_no_serpapi": True,
    })

    assert res.status_code == 200
    assert "sherwani" not in res.get_json()["query_used"].lower()
    assert db.search_logs_of(alice.username) == []
    assert [row[0] for row in db.search_logs_of(bob.username)] == ["rooftop party"]


def test_search_ideas_personalizes_with_own_profile(client, db, alice):
    db.create_profile(alice.username, style_preferences="sherwani")

    res = client.post("/search-ideas", headers=alice.headers,
                      json={"idea": "wedding", "debug_no_serpapi": True})

    assert res.status_code == 200
    assert "sherwani" in res.get_json()["query_used"].lower()


# --- Chatbot -----------------------------------------------------------------
def test_chatbot_only_searches_the_callers_wardrobe(client, db, alice, bob, alice_upload, external_services):
    db.create_upload(alice.username, ALICE_IMG_2)

    res = client.post("/chatbot/query", headers=bob.headers,
                      json={"user_id": alice.username, "query": "formal blazer"})

    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert ALICE_IMG not in body and ALICE_IMG_2 not in body
    assert res.get_json()["results"] == []


def test_chatbot_returns_own_items(client, db, alice, alice_upload):
    res = client.post("/chatbot/query", headers=alice.headers, json={"query": "formal blazer"})

    assert res.status_code == 200
    assert [r["url"] for r in res.get_json()["results"]] == [ALICE_IMG]
