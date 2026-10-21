import os

import pytest


def test_duplicate_submission_is_ignored(tmp_path, monkeypatch):
    db_path = tmp_path / "reports.db"
    monkeypatch.setenv("DB_PATH", str(db_path))

    # db.py reads DB_PATH at import time, so reload it after setting the test path.
    import importlib
    import db
    db = importlib.reload(db)

    db.init_db()
    key = "test-duplicate-submission"

    first_id, first_created = db.create_report(
        user_id=100,
        user_name="Test User",
        category="آزمایشی",
        description="duplicate protection",
        latitude=34.30,
        longitude=48.82,
        photo_file_id="",
        submission_key=key,
    )

    second_id, second_created = db.create_report(
        user_id=100,
        user_name="Test User",
        category="آزمایشی",
        description="duplicate protection",
        latitude=34.30,
        longitude=48.82,
        photo_file_id="",
        submission_key=key,
    )

    assert first_created is True
    assert second_created is False
    assert second_id == first_id
