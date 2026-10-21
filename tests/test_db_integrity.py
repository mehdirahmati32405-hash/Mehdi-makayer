import os

# Keep CI/local test databases away from the production database.
os.environ.setdefault("DB_PATH", "/tmp/test_reports.db")

import db


def test_duplicate_submission_is_ignored():
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
