"""Prompt | llm | parser. No retrieval here."""
# Context-Question Answerer
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from pydantic import BaseModel, Field

from .llm import get_llm

class GradeDocuments(BaseModel):
    """Binary score: is a retrieved chunk relevant to the question?"""
    binary_score: str = Field(description="Document is relevant to the question, 'yes' or 'no'")

def format_docs(docs):
    context = []
    for i, doc in enumerate(docs, start=1):
        source = doc.metadata.get("source", "unknown")
        page = doc.metadata.get("page", "?")
        context.append(f"{i}. From {source} pg {page}, {doc.page_content}")
    return "\n\n".join(context)

def get_answer_chain():
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a university lecturer introducing a new subject to a group of students"
        "Answer using only the provided context. If the context is not enough, say you don't know.",),
        ("human", "Context:\n{context}\n\nQuestion:{question}"),
    ])
    return prompt | get_llm() | StrOutputParser()

def get_answer():
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Answer the question clearly and directly. If you are making any assumptions, state it clearly.",),
        ("human", "Question: {question}"),
    ])
    return prompt | get_llm() | StrOutputParser()

def get_grader():
    retrieval_prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You grade whether a retrieved document can help answer the user question. "
            "Respond with JSON only: {{\"binary_score\": \"yes\"}} or {{\"binary_score\": \"no\"}}. "
            "No other text.",
        ),
        ("human", "Retrieved document:\n\n{document}\n\nUser question: {question}"),
    ])

    return retrieval_prompt | get_llm().with_structured_output(GradeDocuments) 