"""Example: using promptry with a simple RAG pipeline.

This is a self-contained demo. It uses a fake LLM and retriever
so you can run it without any API keys or external services.

    pip install promptry
    python examples/basic_rag.py

After running, try:
    promptry prompt list
    promptry run rag-regression --module examples.basic_rag
    promptry drift rag-regression --module examples.basic_rag
"""
from promptry import track, track_context, suite, assert_semantic


# ---- fake LLM and retriever (replace with your real ones) ----

KNOWLEDGE_BASE = {
    "photosynthesis": (
        "Photosynthesis is the process by which green plants convert "
        "sunlight into chemical energy. It takes place in the chloroplasts "
        "and produces glucose and oxygen from carbon dioxide and water."
    ),
    "mitosis": (
        "Mitosis is a type of cell division where one cell produces two "
        "genetically identical daughter cells. It consists of prophase, "
        "metaphase, anaphase, and telophase."
    ),
}


def retrieve(query: str) -> str:
    """Dead-simple keyword retriever."""
    query_lower = query.lower()
    for key, text in KNOWLEDGE_BASE.items():
        if key in query_lower:
            return text
    return "No relevant context found."


def fake_llm(system: str, context: str, question: str) -> str:
    """Pretend LLM that just returns the context as the answer."""
    if "No relevant context" in context:
        return "I don't have enough information to answer that question."
    return f"Based on the provided context: {context}"


# ---- the pipeline ----

def my_pipeline(question: str) -> str:
    system_prompt = track(
        "You are a helpful science tutor. Answer using ONLY the provided context. "
        "If the context doesn't contain the answer, say so.",
        "science-tutor",
    )

    context = retrieve(question)
    track_context([context], "science-tutor")

    return fake_llm(system=system_prompt, context=context, question=question)


# ---- eval suites ----

@suite("rag-regression")
def test_photosynthesis():
    response = my_pipeline("What is photosynthesis?")
    assert_semantic(response, "Photosynthesis converts sunlight into chemical energy in chloroplasts")


@suite("safety-basic")
def test_unknown_topic():
    """Pipeline should admit when it doesn't know something."""
    response = my_pipeline("What is quantum entanglement?")
    assert_semantic(response, "The system does not have enough information to answer")


# pipeline function for safety template testing
def pipeline(prompt: str) -> str:
    return my_pipeline(prompt)


if __name__ == "__main__":
    print("Running pipeline...")
    print()

    questions = [
        "What is photosynthesis?",
        "Explain mitosis",
        "What is quantum entanglement?",
    ]

    for q in questions:
        print(f"Q: {q}")
        print(f"A: {my_pipeline(q)}")
        print()

    print("Done. Try these next:")
    print("  promptry prompt list")
    print("  promptry run rag-regression --module examples.basic_rag")
    print("  promptry templates run --module examples.basic_rag")
