from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, and_
from sqlalchemy.orm import Session, selectinload
from pydantic import BaseModel, AwareDatetime

from datetime import timedelta

from typing import Literal, Annotated

from db.connect import SessionLocal
from db.models import Attempt, Question

router = APIRouter()

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()

def _serialize_attempt(attempt: Attempt) -> dict:
    return {
        "id": attempt.id,
        "question_id": attempt.question_id,
        "body": attempt.body,
        "proficiency": attempt.proficiency,
        "created_at": attempt.created_at,
    }

@router.get("/{question_id}/attempts")
def get_attempts(question_id: int, db: Session = Depends(get_db)):
    attempts = db.scalars(
        select(Attempt)
        .where(Attempt.question_id == question_id)
        .order_by(Attempt.created_at.desc())
    ).all()

    return [_serialize_attempt(attempt) for attempt in attempts]

@router.get("/topics")
def unique_topics(db: Session = Depends(get_db)):
    topics = db.scalars(
        select(Question.topic)
        .distinct()
        .order_by(Question.topic)
    ).all()
    return topics


class SearchRequest(BaseModel):
    # question db
    name: str | None = None
    topic: str | None = None
    difficulty: Literal["Easy", "Medium", "Hard"] | None = None

    # attempt db
    proficiency: Literal["Excellent", "Good", "Poor"] | None = None
    created_at: AwareDatetime | None = None


@router.get("/search")
def search_question(search_request: Annotated[SearchRequest, Query()], db: Session=Depends(get_db)):
    search_stmt = select(Question).options(selectinload(Question.attempts))

    if search_request.name is not None:
        search_stmt = search_stmt.where(Question.name.ilike(f"%{search_request.name}%"))
    if search_request.topic is not None:
        search_stmt = search_stmt.where(Question.topic == search_request.topic)
    if search_request.difficulty is not None:
        search_stmt = search_stmt.where(Question.difficulty == search_request.difficulty)

    if search_request.proficiency:
        latest_proficiency = (
            select(Attempt.proficiency)
            .where(Attempt.question_id == Question.id)
            .order_by(Attempt.created_at.desc(), Attempt.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        search_stmt = search_stmt.where(latest_proficiency == search_request.proficiency)

    if search_request.created_at is not None:
        day_start = search_request.created_at.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        next_day = day_start + timedelta(days=1)

        search_stmt = search_stmt.where(Question.attempts.any(
            and_(Attempt.created_at >= day_start, 
                Attempt.created_at < next_day)
        ))

    questions = db.scalars(search_stmt.order_by(Question.id)).all()

    return questions

@router.get("/all")
def get_all_questions(db: Session = Depends(get_db)):
    questions = db.scalars(
        select(Question)
        .options(selectinload(Question.attempts))
        .order_by(Question.id)
    ).all()

    return [
        {
            "id": question.id,
            "name": question.name,
            "topic": question.topic,
            "difficulty": question.difficulty,
            "attempts": [
                _serialize_attempt(attempt) for attempt in question.attempts
            ],
        }
        for question in questions
    ]

class QuestionRequest(BaseModel):
    # question table
    name: str
    topic: str
    difficulty: Literal["Easy", "Medium", "Hard"]

    # attempt table
    body: str
    proficiency: str


@router.post("/new/question", status_code=201)
def add_new_question(question_request: QuestionRequest, db: Session = Depends(get_db)):
    # atomic transaction
    with db.begin():
        question = Question(
            name=question_request.name,
            topic=question_request.topic,
            difficulty=question_request.difficulty,
        )

        question.attempts.append(
            Attempt(
                question_id=question.id,
                body=question_request.body,
                proficiency=question_request.proficiency,
            )
        )

        db.add(question)
        db.flush() # Inserts both rows and populates their generated IDs

    return {"question_id": question.id, "attempt_id": question.attempts[0].id}