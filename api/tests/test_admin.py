"""Maintenance routes are admin-only (ADMIN_USERNAMES) and fail closed."""
import pytest

IMG = "https://res.cloudinary.com/demo/image/upload/shared.jpg"
MAINTENANCE_ROUTES = [
    ("GET", "/check-duplicates", None),
    ("POST", "/clean-duplicates", None),
    ("POST", "/index-existing-images", {"username": "alice"}),
]
IDS = [f"{m} {p}" for m, p, _ in MAINTENANCE_ROUTES]


@pytest.fixture
def duplicate_rows(db, alice, bob):
    """The same image_path stored three times across two users."""
    return [
        db.create_upload(alice.username, IMG, md5_hash="a1"),
        db.create_upload(alice.username, IMG, md5_hash="a2"),
        db.create_upload(bob.username, IMG, md5_hash="b1"),
    ]


@pytest.mark.parametrize("method,path,body", MAINTENANCE_ROUTES, ids=IDS)
def test_regular_user_gets_403(client, bob, method, path, body):
    res = client.open(path, method=method, json=body, headers=bob.headers)

    assert res.status_code == 403


def test_regular_user_cannot_list_everyones_duplicates(client, bob, duplicate_rows):
    res = client.get("/check-duplicates", headers=bob.headers)

    assert res.status_code == 403
    assert IMG not in res.get_data(as_text=True)


def test_regular_user_cannot_delete_other_users_rows(client, db, bob, duplicate_rows):
    res = client.post("/clean-duplicates", headers=bob.headers)

    assert res.status_code == 403
    assert all(db.upload(upload_id) for upload_id in duplicate_rows)


def test_regular_user_cannot_trigger_gemini_backfill(client, db, alice, bob, external_services):
    db.create_upload(alice.username, IMG, analyzed=False)

    res = client.post("/index-existing-images", headers=bob.headers, json={"username": alice.username})

    assert res.status_code == 403
    assert external_services.analyzed == []


def test_admin_can_check_and_clean_duplicates(client, db, admin, duplicate_rows):
    checked = client.get("/check-duplicates", headers=admin.headers)
    cleaned = client.post("/clean-duplicates", headers=admin.headers)

    assert checked.status_code == 200
    assert checked.get_json()["duplicates"] == [{"image_path": IMG, "count": 3}]
    assert cleaned.status_code == 200
    assert [db.upload(i) is not None for i in duplicate_rows] == [False, False, True]


def test_admin_can_backfill_a_users_images(client, db, admin, alice, external_services):
    pending = db.create_upload(alice.username, IMG, analyzed=False)

    res = client.post("/index-existing-images", headers=admin.headers, json={"username": alice.username})

    assert res.status_code == 200
    assert res.get_json()["indexed_count"] == 1
    assert external_services.analyzed == [IMG]
    assert db.upload(pending)["gemini_metadata"] is not None


def test_backfill_requires_a_target_username(client, admin):
    res = client.post("/index-existing-images", headers=admin.headers, json={})

    assert res.status_code == 400


def test_backfill_failures_do_not_leak_exception_text(client, db, admin, alice, monkeypatch, app_modules):
    from conftest import SENSITIVE

    db.create_upload(alice.username, IMG, analyzed=False)

    def explode(image_url):
        raise RuntimeError(SENSITIVE)

    monkeypatch.setattr(app_modules.maintenance, "analyze_dress_image_url", explode)

    res = client.post("/index-existing-images", headers=admin.headers, json={"username": alice.username})

    assert res.status_code == 200
    assert res.get_json()["indexed_count"] == 0
    assert SENSITIVE not in res.get_data(as_text=True)


@pytest.mark.parametrize("method,path,body", MAINTENANCE_ROUTES, ids=IDS)
def test_no_admins_configured_means_nobody_is_admin(app, client, admin, method, path, body):
    app.config["ADMIN_USERNAMES"] = []

    res = client.open(path, method=method, json=body, headers=admin.headers)

    assert res.status_code == 403
