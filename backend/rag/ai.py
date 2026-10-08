import json
import os
import re
from threading import local

import requests


API_URL = "https://openrouter.ai/api/v1/chat/completions"
SESSION_LOCAL = local()
NO_ANSWER = "No answer returned."
RATE_LIMIT_MESSAGE = "OpenRouter rate limit reached. Please wait before trying again."
MAX_COMPLETION_TOKENS = 1200


class OpenRouterResponseError(RuntimeError):
    def __init__(self, message, http_status, model, finish_reason, content_empty):
        super().__init__(message)
        self.http_status = http_status
        self.model = model
        self.finish_reason = finish_reason
        self.content_empty = content_empty


def get_session():
    # Each persistent AI worker reuses its own HTTP connection pool.
    if not hasattr(SESSION_LOCAL, "session"):
        SESSION_LOCAL.session = requests.Session()
    return SESSION_LOCAL.session


def extract_final_answer(response_data):
    """Read only the assistant's final message content from the OpenRouter completion."""
    if not isinstance(response_data, dict):
        return ""
    choices = response_data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    first_choice = choices[0]
    message = first_choice.get("message", {}) if isinstance(first_choice, dict) else {}
    if not isinstance(message, dict):
        return ""
    content = message.get("content")

    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        content = "".join(parts)

    if isinstance(content, str):
        content = content.strip()
        if content:
            return content

    return ""


def ask_ai(prompt):
    # Django settings loads backend/.env before this request is handled.
    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL")

    if not api_key or not api_key.strip() or api_key == "your_api_key_here":
        raise RuntimeError("Set OPENROUTER_API_KEY in backend/.env before asking a question.")

    if not model or not model.strip() or model == "your_model_here":
        raise RuntimeError("Set OPENROUTER_MODEL in backend/.env before asking a question.")

    api_key = api_key.strip()
    model = model.strip()

    print("[OPENROUTER REQUEST] Sending request")
    print("OpenRouter prompt:")
    print(prompt)

    try:
        response = get_session().post(
            API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": MAX_COMPLETION_TOKENS,
                "reasoning": {"exclude": True},
            },
            timeout=60,
        )
        print("[OPENROUTER RESPONSE] Status:", response.status_code)
        print("Retry-After:", response.headers.get("Retry-After"))
        print("Rate limit:", response.headers.get("X-RateLimit-Limit"))
        print("Remaining:", response.headers.get("X-RateLimit-Remaining"))
        try:
            response_data = response.json()
        except ValueError:
            response_data = {"raw_body": response.text}

        raw_response = json.dumps(response_data, indent=2, ensure_ascii=False)
        print("[OPENROUTER RAW RESPONSE]", raw_response.replace(api_key, "[REDACTED]"))
        model_used = response_data.get("model") if isinstance(response_data, dict) else None
        choices = response_data.get("choices", []) if isinstance(response_data, dict) else []
        first_choice = choices[0] if isinstance(choices, list) and choices else {}
        finish_reason = first_choice.get("finish_reason") if isinstance(first_choice, dict) else None
        message = first_choice.get("message", {}) if isinstance(first_choice, dict) else {}
        message_fields = sorted(message.keys()) if isinstance(message, dict) else []
        print("[OPENROUTER MODEL USED]", model_used)
        safe_choices = json.dumps(choices, ensure_ascii=False).replace(api_key, "[REDACTED]")
        print("[OPENROUTER CHOICES]", safe_choices)
        print("[OPENROUTER MESSAGE FIELDS]", message_fields)
        print("[OPENROUTER FINISH REASON]", finish_reason)
        response.raise_for_status()
    except requests.HTTPError as error:
        status_code = error.response.status_code if error.response is not None else None
        if status_code == 429:
            raise RuntimeError(RATE_LIMIT_MESSAGE) from error

        safe_response_body = re.sub(re.escape(api_key), "[REDACTED]", response.text if response is not None else "")
        sent_authorization = response.request.headers.get("Authorization", "") if response is not None and response.request else ""
        print("OpenRouter status:", getattr(response, "status_code", None))
        print("Bearer authorization header sent:", sent_authorization.startswith("Bearer "))
        print("OpenRouter final URL:", getattr(response, "url", ""))
        print("OpenRouter redirect count:", len(getattr(response, "history", [])))
        print("OpenRouter response:", safe_response_body)
        raise

    if isinstance(response_data, dict) and response_data.get("error"):
        provider_error = response_data["error"]
        error_message = (
            provider_error.get("message", "Unknown OpenRouter error")
            if isinstance(provider_error, dict)
            else str(provider_error)
        )
        raise OpenRouterResponseError(
            f"OpenRouter API error: {error_message}",
            http_status=response.status_code,
            model=model_used,
            finish_reason=finish_reason,
            content_empty=True,
        )

    final_answer = extract_final_answer(response_data)
    if not final_answer:
        raise OpenRouterResponseError(
            "OpenRouter returned an empty final answer",
            http_status=response.status_code,
            model=model_used,
            finish_reason=finish_reason,
            content_empty=True,
        )
    return final_answer
