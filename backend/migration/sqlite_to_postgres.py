import argparse
from sqlalchemy import create_engine, String, ForeignKey, Integer, select, URL
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator
import os
import sys
from dotenv import load_dotenv
from datetime import datetime, timezone
from pathlib import Path

import re

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from db.models import Attempt as TargetAttempt, Question as TargetQuestion

load_dotenv()

SRCPATH_DB = os.getenv("SRC_DB")

engine = create_engine(URL.create("sqlite", database=SRCPATH_DB))
SQLSession = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class UnixMilliseconds(TypeDecorator[datetime]):
    """Read/write Unix timestamps stored as integer milliseconds in SQLite."""

    impl = Integer
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return int(value.timestamp() * 1000)

    def process_result_value(self, value: int | None, dialect):
        if value is None:
            return None
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    color: Mapped[str] = mapped_column(String, nullable=False)
    entries: Mapped[list["Entry"]] = relationship(back_populates="category")


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    date: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str] = mapped_column(String, nullable=False)

    category_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        UnixMilliseconds(),
        nullable=False,
    )

    category: Mapped[Category | None] = relationship(back_populates="entries")


db = SQLSession()

QUESTION_HEADER = re.compile(r"^#\s*(\d+)\s+(.+?)\s*$")
METADATA_LINE = re.compile(
    r"^\s*(Topic|Labels|Source|Difficulty|Proficiency):\s*(.*?)\s*$",
    re.IGNORECASE,
)


def parse_notes(notes: str) -> list[dict]:
    """Split one legacy entry into its individual LeetCode question records."""
    parsed = []
    chunks = re.split(r"(?m)(?=^#\s*\d+\s+)", notes.strip())

    for chunk in chunks:
        if not chunk.strip():
            continue

        lines = chunk.strip().splitlines()
        header = QUESTION_HEADER.match(lines[0].strip())
        if header is None:
            raise ValueError(f"Unrecognized LeetCode note heading: {lines[0]!r}")

        fields = {}
        body_lines = []
        for line in lines[1:]:
            field = METADATA_LINE.match(line)
            key = field.group(1).lower() if field else None
            if key in {"topic", "labels", "source", "difficulty", "proficiency"}:
                fields[key] = field.group(2).strip()
            elif line.strip():
                body_lines.append(line.rstrip())

        if fields.get("topic"):
            fields["topic"] = fields["topic"].split(",", 1)[0].strip()

        freeform_notes = "\n".join(body_lines).strip()

        parsed.append(
            {
                "leetcode_id": header.group(1),
                "name": header.group(2).strip(),
                "topic": fields.get("topic") or None,
                "difficulty": fields.get("difficulty"),
                "proficiency": fields.get("proficiency"),
                "source": fields.get("source"),
                "labels": fields.get("labels"),
                "body": freeform_notes,
            }
        )

    return parsed


def build_target_questions(source_entries: list[Entry]) -> list[TargetQuestion]:
    """Build Question/Attempt ORM objects without writing them to PostgreSQL."""
    grouped = {}

    # The query supplies newest entries first. Use the newest non-empty topic
    # when topic classifications differ between attempts.
    for source_entry in source_entries:
        for record in parse_notes(source_entry.notes):
            leetcode_id = record["leetcode_id"]
            group = grouped.setdefault(
                leetcode_id,
                {
                    "name": f"#{leetcode_id} {record['name']}",
                    "topic": None,
                    "source": None,
                    "labels": None,
                    "difficulty": record["difficulty"],
                    "attempts": [],
                },
            )

            if group["name"] != f"#{leetcode_id} {record['name']}":
                raise ValueError(f"Conflicting names for LeetCode #{leetcode_id}")
            if record["topic"] and not group["topic"]:
                group["topic"] = record["topic"]
            for field in ("source", "labels"):
                if record[field] and group[field] and record[field] != group[field]:
                    raise ValueError(
                        f"Conflicting {field} for LeetCode #{leetcode_id}"
                    )
                if record[field] and not group[field]:
                    group[field] = record[field]
            if group["difficulty"] != record["difficulty"]:
                raise ValueError(f"Conflicting difficulty for LeetCode #{leetcode_id}")
            if not record["proficiency"]:
                raise ValueError(f"Missing proficiency for LeetCode #{leetcode_id}")

            group["attempts"].append(
                TargetAttempt(
                    body=record["body"],
                    proficiency=record["proficiency"],
                    created_at=source_entry.created_at,
                )
            )

    questions = []
    for leetcode_id, group in grouped.items():
        if not group["topic"]:
            raise ValueError(f"Missing topic for LeetCode #{leetcode_id}")
        questions.append(
            TargetQuestion(
                name=group["name"],
                topic=group["topic"],
                difficulty=group["difficulty"],
                source=group["source"],
                labels=group["labels"],
                attempts=group["attempts"],
            )
        )

    return questions


source_entries = db.scalars(
    select(Entry)
    .where(Entry.category_id == "cat-leetcode")
    .order_by(Entry.created_at.desc())
).all()

target_questions = build_target_questions(source_entries)
attempt_count = sum(len(question.attempts) for question in target_questions)
print(
    f"Prepared {len(target_questions)} questions and {attempt_count} attempts. "
)
db.close()


def write_to_postgres(questions: list[TargetQuestion]) -> None:
    """Insert the complete import atomically; refuse an accidental rerun."""
    from db.connect import SessionLocal as TargetSessionLocal

    with TargetSessionLocal.begin() as target_db:
        existing_question_id = target_db.scalar(
            select(TargetQuestion.id).limit(1)
        )
        if existing_question_id is not None:
            raise RuntimeError(
                "The PostgreSQL questions table is not empty; refusing to "
                "insert duplicate migration data."
            )

        # Adding parent objects with their related attempts lets the ORM assign
        # generated question IDs and populate attempts.question_id.
        target_db.add_all(questions)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate LeetCode data to PostgreSQL")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the prepared questions and attempts to PostgreSQL",
    )
    args = parser.parse_args()
    
    if args.apply:
        write_to_postgres(target_questions)
        print("PostgreSQL import committed successfully.")
    else:
        print("Dry run only. Pass --apply to write to PostgreSQL.")
