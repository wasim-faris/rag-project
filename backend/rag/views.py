from time import perf_counter

import requests
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .ai import OpenRouterResponseError, RATE_LIMIT_MESSAGE, ask_ai
from .retrieval import retrieve_context_with_score


ANSWER_CACHE = {}


def ask_ai_with_timing(prompt, label):
    started = perf_counter()
    try:
        return ask_ai(prompt)
    finally:
        print(f"{label}: {perf_counter() - started:.3f}s")


@api_view(["POST"])
def ask_question(request):
    print("[ASK API] Request received")
    question = request.data.get("question", "")
    if not isinstance(question, str) or not question.strip():
        return Response(
            {"error": "Please provide a question."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    question = question.strip()
    request_started = perf_counter()

    # Repeated questions can reuse the completed comparison immediately.
    if question in ANSWER_CACHE:
        print("Answer cache: hit")
        print(f"Total backend response: {perf_counter() - request_started:.3f}s")
        return Response(ANSWER_CACHE[question])

    retrieval_started = perf_counter()
    context, relevance_score = retrieve_context_with_score(question)
    print(f"Retrieval: {perf_counter() - retrieval_started:.3f}s")
    print("Question:", question)
    print("Retrieved context:", context)
    print("Relevance score:", relevance_score)

    try:
        with_prompt = (
            "You are a concise company FAQ assistant.\n\n"
            "Answer the question using ONLY the provided context.\n\n"
            "Return ONLY the final answer.\n"
            "Do not provide reasoning.\n"
            "Do not provide analysis.\n"
            "Do not show your thinking process.\n"
            "Do not explain the context.\n"
            "\nIf the answer is available in the context, answer directly.\n\n"
            "If the answer is not available in the context, return exactly:\n\n"
            '"I don\'t have that information in my knowledge base."\n\n'
            f"Context:\n{context}\n\n"
            f"Question:\n{question}\n\n"
            "Final answer:"
        )
        without_prompt = (
            "You are a concise FAQ assistant.\n\n"
            "Answer the question directly using your general knowledge.\n\n"
            "Return ONLY the final answer.\n\n"
            "Do not provide reasoning.\n"
            "Do not provide analysis.\n"
            "Do not show your thinking process.\n"
            "Do not explain how you reached the answer.\n"
            f"Question:\n{question}\n\n"
            "Final answer:"
        )
        print("[OPENROUTER REQUEST] WITHOUT CONTEXT")
        print("WITHOUT CONTEXT PROMPT:")
        print(without_prompt)
        without_context = ask_ai_with_timing(
            without_prompt, "Without-context OpenRouter request"
        )
        print("[OPENROUTER REQUEST] WITH CONTEXT")
        print("WITH CONTEXT PROMPT:")
        print(with_prompt)
        with_context = ask_ai_with_timing(with_prompt, "With-context OpenRouter request")
    except OpenRouterResponseError as error:
        print(f"Total backend response: {perf_counter() - request_started:.3f}s")
        return Response(
            {
                "error": str(error),
                "http_status": error.http_status,
                "model": error.model,
                "finish_reason": error.finish_reason,
                "content_empty": error.content_empty,
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except (RuntimeError, requests.RequestException, KeyError, IndexError) as error:
        print(f"Total backend response: {perf_counter() - request_started:.3f}s")
        if str(error) == RATE_LIMIT_MESSAGE:
            return Response({"error": RATE_LIMIT_MESSAGE}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        return Response({"error": str(error)}, status=status.HTTP_502_BAD_GATEWAY)

    print(f"Total backend response: {perf_counter() - request_started:.3f}s")
    result = {
        "question": question,
        "retrieved_context": context,
        "relevance_score": relevance_score,
        "without_context": without_context,
        "with_context": with_context,
    }
    ANSWER_CACHE[question] = result
    return Response(result)
