import pytest

VALID_PREFERENCES = {
    "style_aesthetics": ["Casual", "Streetwear"],
    "occasions": ["Everyday", "Travel"],
    "preferred_colors": ["Neutrals", "Earth tones"],
    "fit_priorities": ["Comfort"],
    "outfit_goals": ["Polished", "Versatile"],
}


def test_profile_preferences_round_trip_and_partial_update_preserves_existing_fields(
    client, db, alice
):
    client.post("/profile", headers=alice.headers, json={"gender": "Female", "sizes": "M"})

    saved = client.post(
        "/profile", headers=alice.headers, json={"preferences": VALID_PREFERENCES}
    )
    fetched = client.get("/profile", headers=alice.headers)

    assert saved.status_code == 200
    assert fetched.get_json()["preferences"] == VALID_PREFERENCES
    assert fetched.get_json()["gender"] == "Female"
    assert fetched.get_json()["sizes"] == "M"
    assert db.query(
        "SELECT onboarding_preferences FROM user_profiles WHERE username = %s",
        (alice.username,),
    )[0][0] == VALID_PREFERENCES


@pytest.mark.parametrize("preferences", [
    [],
    {"unknown": ["Casual"]},
    {"style_aesthetics": "Casual"},
    {"style_aesthetics": ["Not a supported style"]},
    {"style_aesthetics": ["Casual"] * 6},
    {"style_aesthetics": ["Casual", "Casual"]},
], ids=[
    "not-an-object", "unknown-field", "not-a-list", "unknown-option",
    "too-many-options", "duplicate-options",
])
def test_profile_rejects_invalid_preferences_without_saving(
    client, db, alice, preferences
):
    response = client.post(
        "/profile", headers=alice.headers, json={"preferences": preferences}
    )

    assert response.status_code == 400
    assert db.query("SELECT username FROM user_profiles") == []


def test_profile_rejects_non_object_request(client, alice):
    response = client.post(
        "/profile", headers=alice.headers, data="[]", content_type="application/json"
    )

    assert response.status_code == 400


def test_new_preferences_are_included_in_idea_search_personalization(client, db, alice):
    saved = client.post(
        "/profile",
        headers=alice.headers,
        json={"preferences": {"style_aesthetics": ["Casual"]}},
    )
    response = client.post(
        "/search-ideas",
        headers=alice.headers,
        json={"idea": "weekend", "debug_no_serpapi": True},
    )

    assert saved.status_code == 200
    assert response.status_code == 200
    assert "casual" in response.get_json()["query_used"].lower()


def test_profile_without_saved_answers_returns_empty_preferences(client, alice):
    response = client.get("/profile", headers=alice.headers)

    assert response.status_code == 200
    assert response.get_json()["preferences"] == {}
