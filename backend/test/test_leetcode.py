"""Runnable API checks: ``python backend/test/test_leetcode.py``."""

import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Allow running this file directly from the repository root or backend directory.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# The endpoint module imports the production database factory at module load.
# This API test suite replaces it because every test supplies its own SQLite DB.
database_connect = types.ModuleType("db.connect")
database_connect.SessionLocal = lambda: None
sys.modules.setdefault("db.connect", database_connect)

from api.leetcode import get_db, router  # noqa: E402
from db.models import Attempt, Base, Question  # noqa: E402


# SQLite only autogenerates row IDs for an INTEGER PRIMARY KEY. The app uses
# BigInteger IDs for PostgreSQL, so render those as INTEGER in this test DB.
@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(_type, _compiler, **_kwargs):
    return "INTEGER"


class LeetCodeEndpointTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)

        app = FastAPI()
        app.include_router(router, prefix="/leetcode")

        def override_get_db():
            with self.session_factory() as db:
                yield db

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self._seed_database()

    def tearDown(self):
        self.client.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _seed_database(self):
        with self.session_factory.begin() as db:
            two_sum = Question(
                id=1, name="Two Sum", topic="Arrays", difficulty="Easy"
            )
            add_numbers = Question(
                id=2,
                name="Add Two Numbers",
                topic="Linked List",
                difficulty="Medium",
            )
            binary_search = Question(
                id=3,
                name="Binary Search",
                topic="Arrays",
                difficulty="Easy",
            )
            db.add_all([two_sum, add_numbers, binary_search])
            db.add_all(
                [
                    Attempt(
                        id=1,
                        question_id=1,
                        body="First solution",
                        proficiency="Poor",
                        created_at=datetime(2025, 1, 1, 10, tzinfo=timezone.utc),
                    ),
                    Attempt(
                        id=2,
                        question_id=1,
                        body="Improved solution",
                        proficiency="Good",
                        created_at=datetime(2025, 1, 2, 10, tzinfo=timezone.utc),
                    ),
                    Attempt(
                        id=3,
                        question_id=2,
                        body="Linked list solution",
                        proficiency="Poor",
                        created_at=datetime(2025, 1, 2, 12, tzinfo=timezone.utc),
                    ),
                ]
            )

    def test_topics_are_unique_and_sorted(self):
        response = self.client.get("/leetcode/topics")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), ["Arrays", "Linked List"])

    def test_attempts_are_returned_newest_first(self):
        response = self.client.get("/leetcode/1/attempts")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [attempt["body"] for attempt in response.json()],
            ["Improved solution", "First solution"],
        )

    def test_all_questions_include_attempts(self):
        response = self.client.get("/leetcode/all")

        self.assertEqual(response.status_code, 200)
        questions = response.json()
        self.assertEqual([question["name"] for question in questions], [
            "Two Sum", "Add Two Numbers", "Binary Search"
        ])
        self.assertEqual(questions[0]["attempts"][0]["proficiency"], "Good")
        self.assertEqual(questions[2]["attempts"], [])

    def test_search_supports_question_filters(self):
        response = self.client.get(
            "/leetcode/search", params={"name": "sum", "difficulty": "Easy"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([question["name"] for question in response.json()], ["Two Sum"])

    def test_search_proficiency_uses_latest_attempt(self):
        response = self.client.get(
            "/leetcode/search", params={"proficiency": "Good"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([question["name"] for question in response.json()], ["Two Sum"])

    def test_search_can_filter_by_attempt_day(self):
        response = self.client.get(
            "/leetcode/search", params={"created_at": "2025-01-02T00:00:00Z"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [question["name"] for question in response.json()],
            ["Two Sum", "Add Two Numbers"],
        )

    def test_new_question_creates_question_and_first_attempt(self):
        response = self.client.post(
            "/leetcode/new/question",
            json={
                "name": "Valid Parentheses",
                "topic": "Stack",
                "difficulty": "Easy",
                "body": "Use a stack to match brackets.",
                "proficiency": "Good",
            },
        )

        self.assertEqual(response.status_code, 201, response.text)
        created = response.json()
        self.assertGreater(created["question_id"], 0)
        self.assertGreater(created["attempt_id"], 0)

        stored = self.client.get(f"/leetcode/{created['question_id']}/attempts")
        self.assertEqual(stored.status_code, 200)
        self.assertEqual(stored.json()[0]["body"], "Use a stack to match brackets.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
