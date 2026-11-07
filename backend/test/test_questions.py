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

from api.questions import get_db, router  # noqa: E402
from db.models import Attempt, Base, Question, User, QuestionList, QuestionListItem  # noqa: E402
from auth.security import hash_password, verify_password, get_token
from auth.dependencies import get_user

# SQLite only autogenerates row IDs for an INTEGER PRIMARY KEY. The app uses
# BigInteger IDs for PostgreSQL, so render those as INTEGER in this test DB.
@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(_type, _compiler, **_kwargs):
    return "INTEGER"

TEST_USERNAME = "tester"
TEST_PWD = "password"
token = get_token("1", TEST_USERNAME)
headers = {"Authorization": f"Bearer {token}"}

class QuestionEndpointTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)

        app = FastAPI()
        app.include_router(router)

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
            # Add user
            test_user = User(
                id=1, username=TEST_USERNAME, hashed_pwd=hash_password(TEST_PWD)
            )
            db.add(test_user)

            # Add questions
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

            # Add Attempts
            db.add_all(
                [
                    Attempt(
                        id=1,
                        user_id=1,
                        question_id=1,
                        body="First solution",
                        proficiency="Poor",
                        created_at=datetime(2025, 1, 1, 10, tzinfo=timezone.utc),
                    ),
                    Attempt(
                        id=2,
                        user_id=1,
                        question_id=1,
                        body="Improved solution",
                        proficiency="Good",
                        created_at=datetime(2025, 1, 2, 10, tzinfo=timezone.utc),
                    ),
                    Attempt(
                        id=3,
                        user_id=1,
                        question_id=2,
                        body="Linked list solution",
                        proficiency="Poor",
                        created_at=datetime(2025, 1, 2, 12, tzinfo=timezone.utc),
                    ),
                ]
            )

            # Add a list
            my_list = QuestionList(
                id=1,
                user_id=1,
                name="Strong 10",
            )
            db.add(my_list)

            # Add list items
            db.add_all([
                QuestionListItem(
                    user_id=1,
                    list_id=1,
                    question_id=1,
                ),
                QuestionListItem(
                    user_id=1,
                    list_id=1,
                    question_id=2,
                )
            ])

    def test_topics_are_unique_and_sorted(self):
        response = self.client.get("/topics")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), ["Arrays", "Linked List"])

    def test_attempts_are_returned_newest_first(self):
        response = self.client.get("/1/attempts", headers=headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [attempt["body"] for attempt in response.json()],
            ["Improved solution", "First solution"],
        )

    def test_all_questions_include_attempts(self):
        response = self.client.get("/all", headers=headers)
        self.assertEqual(response.status_code, 200)
        questions = response.json()
        self.assertEqual([question["name"] for question in questions], [
            "Two Sum", "Add Two Numbers", "Binary Search"
        ])
        self.assertEqual(questions[0]["attempts"][0]["proficiency"], "Good")
        self.assertEqual(questions[2]["attempts"], [])

    def test_search_supports_question_filters(self):
        response = self.client.get(
            "search", params={"name": "sum", "difficulty": "Easy"},
            headers=headers
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([question["name"] for question in response.json()], ["Two Sum"])

    def test_search_proficiency_uses_latest_attempt(self):
        response = self.client.get(
            "/search", params={"proficiency": "Good"}, headers=headers
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([question["name"] for question in response.json()], ["Two Sum"])

    def test_search_can_filter_by_attempt_day(self):
        response = self.client.get(
            "/search", params={"created_at": "2025-01-02T00:00:00Z", "user_id": 1}, headers=headers
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [question["name"] for question in response.json()],
            ["Two Sum", "Add Two Numbers"],
        )

    def test_new_question_creates_question_and_first_attempt(self):
        response = self.client.post(
            "/new/question",
            json={
                "name": "Valid Parentheses",
                "topic": "Stack",
                "difficulty": "Easy",
                "body": "Use a stack to match brackets.",
                "proficiency": "Good",
            },
            headers=headers,
        )

        self.assertEqual(response.status_code, 201, response.text)
        created = response.json()
        self.assertGreater(created["question_id"], 0)
        self.assertGreater(created["attempt_id"], 0)

        stored = self.client.get(f"{created['question_id']}/attempts", headers=headers)
        self.assertEqual(stored.status_code, 200)
        self.assertEqual(stored.json()[0]["body"], "Use a stack to match brackets.")

    def test_upload_question_list_csv(self):
        csv_content = "ID,Title,Difficulty\n42,Trapping Rain Water,Hard\n"

        response = self.client.post(
            "/new/list",
            params={"list_name": "Array Problems"},
            files={
                "file": (
                    "questions.csv",
                    csv_content,
                    "text/csv",
                )
            },
            headers=headers,
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(
            response.json()["questions"][0]["name"],
            "#42 Trapping Rain Water",
        )

        lists = self.client.get("/mylists", headers=headers)
        self.assertEqual(lists.json()[0]["name"], "Array Problems")

    def test_list_items(self):
        response = self.client.get("/list/1", headers=headers)

        self.assertEqual(
            [question["name"] for question in response.json()],
            ["Two Sum", "Add Two Numbers"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
