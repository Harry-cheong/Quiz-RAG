from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile
from sqlalchemy import select, and_, insert
from sqlalchemy.orm import Session, selectinload
from pydantic import BaseModel, AwareDatetime
import csv
import io
from pathlib import Path

from datetime import timedelta

from typing import Literal, Annotated

from db.connect import SessionLocal
from db.models import Attempt, Question, QuestionList, QuestionListItem

from auth.dependencies import get_user

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
def get_attempts(question_id: int, db: Session = Depends(get_db), user_id: int = Depends(get_user)):
    attempts = db.scalars(
        select(Attempt)
        .where(
            and_(
                Attempt.question_id == question_id,
                Attempt.user_id == user_id
            )
        )
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
    difficulty: str | None = None

    # attempt db
    proficiency: Literal["Excellent", "Good", "Poor"] | None = None
    created_at: AwareDatetime | None = None


@router.get("/search")
def search_question(search_request: Annotated[SearchRequest, Query()], db: Session=Depends(get_db), user_id: int = Depends(get_user)):
    search_stmt = select(Question).options(
        selectinload(Question.attempts.and_(Attempt.user_id == user_id))
    )
    if search_request.name is not None:
        search_stmt = search_stmt.where(Question.name.ilike(f"%{search_request.name}%"))
    if search_request.topic is not None:
        search_stmt = search_stmt.where(Question.topic == search_request.topic)
    if search_request.difficulty is not None:
        search_stmt = search_stmt.where(Question.difficulty == search_request.difficulty)

    if search_request.proficiency:
        latest_proficiency = (
            select(Attempt.proficiency)
            .where(
                Attempt.question_id == Question.id,
                Attempt.user_id == user_id,
            )
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
                Attempt.created_at < next_day,
                Attempt.user_id == user_id)
        ))

    questions = db.scalars(search_stmt.order_by(Question.id)).all()

    return questions

@router.get("/all")
def get_all_questions(db: Session = Depends(get_db), user_id: int = Depends(get_user)):
    questions = db.scalars(
        select(Question)
        .options(selectinload(Question.attempts.and_(Attempt.user_id == user_id)))
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
def add_new_question(question_request: QuestionRequest, db: Session = Depends(get_db), user_id: int = Depends(get_user)):
    # atomic transaction
    with db.begin():
        question = Question(
            name=question_request.name,
            topic=question_request.topic,
            difficulty=question_request.difficulty,
        )

        question.attempts.append(
            Attempt(
                user_id=user_id,
                question_id=question.id,
                body=question_request.body,
                proficiency=question_request.proficiency,
            )
        )

        db.add(question)
        db.flush() # Inserts both rows and populates their generated IDs

    return {"question_id": question.id, "attempt_id": question.attempts[0].id}

@router.post("/new/list")
async def add_list(list_name: str, file: UploadFile = File(...), db: Session = Depends(get_db), user_id: int = Depends(get_user)):
    if not file.filename or Path(file.filename).suffix.lower() != ".csv":
        raise HTTPException(status_code=415, detail="Only CSV files are supported")

    contents = await file.read()
    rows = csv.DictReader(io.StringIO(contents.decode("utf-8")))

    try:
        questions = [
            {
                "name": f"#{row['ID']} {row['Title']}",
                "difficulty": row["Difficulty"]
            } for row in rows
        ]
    except:
        raise HTTPException(status_code=500, detail="Invalid Table Column Names")

    # Deduplicate names 
    names = list(dict.fromkeys(q["name"] for q in questions))

    with db.begin():
        existing_questions = db.scalars(select(Question.name).where(Question.name.in_(names))).all()
        questions_by_name = {q.name: q for q in existing_questions}

        # add new questions
        for q in questions:
            if q["name"] not in questions_by_name:
                question = Question(
                    name=q["name"],
                    difficulty=q["difficulty"],
                )
                db.add(question)
                questions_by_name[q["name"]] = question
                
        # add new list
        new_list = QuestionList(
            user_id = user_id,
            name=list_name,
        )
        db.add(new_list)

        db.flush() # assign new IDs

        # add list items
        db.add_all(
            [QuestionListItem(
                user_id=user_id,
                list_id=new_list.id,
                question_id=questions_by_name[name].id
            ) for name in names]
        )

    return {"count": len(questions), "questions": questions}

@router.get("/mylists")
def get_my_list(db: Session = Depends(get_db), user_id: int = Depends(get_user)):
    questions_lists = db.scalars(select(QuestionList).where(QuestionList.user_id==user_id)).all()

    return [
        {
            "name": l.name,
            "id": l.id,
        }
        for l in questions_lists
    ]

@router.get("/list/{id}")
def get_list(id: int, db: Session = Depends(get_db), user_id: int = Depends(get_user)):
    question_ids = db.scalars(
        select(QuestionListItem.question_id)
        .where(
            and_(
                QuestionListItem.list_id == id,
                QuestionListItem.user_id == user_id,
            )
        )
        .order_by(QuestionListItem.question_id)
    ).all()

    questions = db.scalars(select(Question).where(Question.id.in_(question_ids))).all()

    return [
        {
            "id": question.id,
            "name": question.name,
            "topic": question.topic,
            "difficulty": question.difficulty,
        }
        for question in questions
    ]

    
