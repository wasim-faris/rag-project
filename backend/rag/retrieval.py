import re
from pathlib import Path


KNOWLEDGE_FILE = Path(__file__).with_name("knowledge.txt")
KNOWLEDGE_LINES = tuple(
    line.strip()
    for line in KNOWLEDGE_FILE.read_text(encoding="utf-8").splitlines()
    if line.strip()
)
NO_RELEVANT_CONTEXT = "No relevant information found."

# These common words do not help identify which company fact the user needs.
STOP_WORDS = {
    "a", "an", "and", "are", "can", "company", "do", "does", "employee",
    "employees", "for", "from", "get", "how", "i", "is", "it", "many",
    "me", "of", "on", "the", "their", "to", "what", "where", "which",
    "who", "with",
}

# Recognize common question wording, then search only the matching fact keywords.
# The answer itself always comes from KNOWLEDGE_LINES, not from this mapping.
FAQ_FIELDS = {
    "company_name": {
        "phrases": (
            "company name", "what company", "which company", "company is this",
            "organization name", "name of company", "name of the company",
        ),
        "keywords": {"company", "technova"},
    },
    "office": {
        "phrases": ("office", "office location", "office located"),
        "keywords": {"office", "location", "located", "kannur", "kerala"},
    },
    "working_hours": {
        "phrases": (
            "working hours", "work hours", "office hours", "work schedule",
            "when does the company work", "when does company work",
        ),
        "keywords": {"working", "hours", "work", "monday", "friday"},
    },
    "casual_leave": {
        "phrases": ("casual leave", "casual leaves", "leave", "leaves"),
        "keywords": {"casual", "leave", "leaves"},
    },
    "driver_documents": {
        "phrases": (
            "driver onboarding", "onboarding documents", "required documents",
            "driver documents", "documents for driver", "documents required",
        ),
        "keywords": {
            "documents", "license", "aadhaar", "pan", "police", "clearance", "pcc",
        },
    },
}


def find_faq_field(question):
    """Identify a known FAQ topic from familiar words in the question."""
    normalized_question = " ".join(re.findall(r"[a-z0-9]+", question.lower()))
    for field_name, field in FAQ_FIELDS.items():
        if any(phrase in normalized_question for phrase in field["phrases"]):
            return field_name
    return None


def retrieve_context_with_score(question):
    # First identify the question topic; a shared generic word is never enough.
    field_name = find_faq_field(question)
    if field_name is None:
        return NO_RELEVANT_CONTEXT, 0

    field_keywords = FAQ_FIELDS[field_name]["keywords"]
    question_words = {
        word
        for word in re.findall(r"[a-z0-9]+", question.lower())
        if word not in STOP_WORDS
    }
    # Use question words plus field words, counting each word only once.
    meaningful_words = question_words | field_keywords

    # Score knowledge lines against the recognized field's small keyword set.
    scored_lines = []
    for line in KNOWLEDGE_LINES:
        line_words = set(re.findall(r"[a-z0-9]+", line.lower()))
        score = len(meaningful_words & line_words)
        if score >= 2:
            scored_lines.append((score, line))

    # Require at least one meaningful keyword; return a clear sentinel on no match.
    if not scored_lines:
        return NO_RELEVANT_CONTEXT, 0

    best_score = max(score for score, _ in scored_lines)
    scored_lines.sort(key=lambda item: item[0], reverse=True)
    selected_lines = {line for _, line in scored_lines[:4]}

    # If a selected knowledge line is a list continuation, include its heading.
    for line_index, line in enumerate(KNOWLEDGE_LINES):
        if line in selected_lines and line_index > 0 and KNOWLEDGE_LINES[line_index - 1].endswith(":"):
            selected_lines.add(KNOWLEDGE_LINES[line_index - 1])

    context = "\n".join(line for line in KNOWLEDGE_LINES if line in selected_lines)
    return context or NO_RELEVANT_CONTEXT, best_score


def retrieve_context(question):
    context, _score = retrieve_context_with_score(question)
    return context
