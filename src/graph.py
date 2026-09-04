"""LangGraph: retrieve → grade_documents → transform_query / generate."""
from langgraph.graph import END, StateGraph, START

from .retrieve import get_retriever
from .generate import get_answer_chain, format_docs, get_answer, get_grader

from typing import Any, List
from typing_extensions import TypedDict
from functools import lru_cache

class GraphState(TypedDict):
    """State passed between LangGraph nodes."""
    question: str
    generation: str
    documents: List[Any]

workflow = StateGraph(GraphState)

def retrieve(state):
    """Fetch relevant chunks from Chroma. LangGraph owns this step, not Cursor."""
    print("---RETRIEVE---")
    question = state["question"]
    documents = get_retriever().invoke(question)
    return {"documents": documents, "question": question}

def generate(state):
    """Fill the prompt with retrieved context and call the chat model."""
    print("---GENERATE---")
    chain = get_answer_chain()
    question = state["question"]
    documents = state["documents"]
    generation = chain.invoke({
        "context": format_docs(documents),
        "question": question,
    })
    return {"documents": documents, "question": question, "generation": generation}

def grade_documents(state):
    print("---CHECK DOCUMENT RELEVANCE TO QUESTION---")
    question = state["question"]
    documents = state["documents"]

    # Score each doc
    filtered_docs = []
    for d in documents:
        score = get_grader().invoke(
            {"question": question, "document": d.page_content}
        )
        grade = score.binary_score
        print(d)
        if grade == "yes":
            print("---GRADE: DOCUMENT RELEVANT---")
            filtered_docs.append(d)
        else:
            print("---GRADE: DOCUMENT NOT RELEVANT---") # Remove documents if irrelevant
            continue
    return {"documents": filtered_docs, "question": question}

def answer(state):
    print("---ANSWER QUERY WITH GENERAL KNOWLEDGE---")
    question = state["question"]
    documents = state["documents"]

    generation = get_answer().invoke({"question": question})
    print(generation)
    return {"documents": documents, "question": question, "generation": generation}

def decide_to_generate(state):
    print("---ASSESS GRADED DOCUMENTS---")
    state["question"]
    filtered_documents = state["documents"]

    if not filtered_documents:
        # All documents have been filtered check_relevance
        # We will re-generate a new query
        print(
            "---DECISION: ALL DOCUMENTS ARE NOT RELEVANT TO QUESTION, ANSWER WITH GENERAL KNOWLEDGE---"
        )
        return "answer_query"
    else:
        # We have relevant documents, so generate answer
        print("---DECISION: GENERATE---")
        return "generate"

@lru_cache(maxsize=1)
def rag_workflow():
    workflow.add_node("retrieve", retrieve)
    workflow.add_node("grade_documents", grade_documents)
    workflow.add_node("answer_query", answer)
    workflow.add_node("generate", generate)

    workflow.add_edge(START, "retrieve")
    workflow.add_edge("retrieve", "grade_documents")
    workflow.add_conditional_edges(
        "grade_documents",
        decide_to_generate,
        {
            "answer_query": "answer_query",
            "generate": "generate",
        },
    )
    # Do not also edge retrieve → generate. That would run generate in parallel
    # with grade_documents, and both write `documents` in the same step.
    workflow.add_edge("answer_query", END)
    workflow.add_edge("generate", END)

    return workflow.compile()