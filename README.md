# Simple RAG AI Demo

A small learning project showing how a React page can send a question to a Django REST API, retrieve matching company facts from a text file, and compare two OpenRouter answers.

It uses readable Python functions and keyword matching. It does not use embeddings, a vector database, or a RAG framework.

## How It Works

### External Data

`backend/rag/knowledge.txt` contains fictional TechNova company information stored outside the AI model.

### Retrieval

The backend normalizes the question and recognizes a small FAQ field such as company name, office, working hours, casual leave, or driver documents. It then counts overlaps between that field's keywords and cached lines from `knowledge.txt`. Generic terms such as `employees`, `company`, and `get` cannot create a match by themselves. At least two meaningful terms must overlap; otherwise retrieval returns `No relevant information found.` and the API skips OpenRouter. This is simple keyword retrieval, not semantic search.

### Prompts and Comparison

For questions with retrieved facts, the backend asks OpenRouter twice concurrently:

- **Without context:** The prompt contains the assistant instructions and only the user's question.
- **With context:** The prompt tells the AI to answer using only the retrieved information and includes `Context` followed by `Question`.

The API returns the retrieved context and both answers so the React page can display the comparison.

For questions with no matching facts, the backend does not send a context prompt to OpenRouter. It returns the knowledge-base refusal directly for the with-context answer.

### Free OpenRouter Model

`backend/.env` sets `OPENROUTER_MODEL=openrouter/free`. This is OpenRouter's Free Models Router, which automatically chooses an available free model for each request, so you do not need to select a provider model yourself. Its underlying model can vary as OpenRouter's free model pool changes. Free models can have stricter rate limits or temporary availability limits, but this setting does not route to a paid model.

The Python code reads `OPENROUTER_MODEL` from `.env` and does not contain a model-specific default. To change models later, change that environment variable only.

### Accuracy Analysis

The page explains that a no-context answer may be generic, while a contextual answer can use company-specific facts. It does not claim a numerical accuracy score because the app does not evaluate model answers automatically.

## Architecture

```text
React UI
      ↓
Django REST API
      ↓
Retrieve from knowledge.txt
      ↓
Create prompt
      ↓
OpenRouter AI
      ↓
Return both answers
      ↓
React displays comparison
```

## Run the Backend

Open a terminal in the `backend` folder. Django loads `backend/.env` first, then the project-root `.env` (`simple-rag/.env`) if present. Values in the project-root file take precedence, so a current API key there replaces a stale backend copy. The configured model is `openrouter/free`; leave it as-is to use OpenRouter's free-model router, or change only `OPENROUTER_MODEL` if needed.

The `.env` file should have these settings:

```dotenv
OPENROUTER_API_KEY=your_api_key_here
OPENROUTER_MODEL=openrouter/free
```

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py runserver
```

The API endpoint is `POST http://127.0.0.1:8000/api/ask/` and expects JSON such as:

```json
{"question": "How many casual leaves do employees get?"}
```

The endpoint starts its two independent OpenRouter requests concurrently and returns both answers in one response. The browser makes only one request to the Django API. Exact repeat questions are cached in memory for the lifetime of the Django process. Backend logs show retrieval time, each OpenRouter request time, and total request time.

## Run the Frontend

In a second terminal, open the `frontend` folder:

```bash
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite. Vite forwards `/api` requests to the Django server on port `8000`.

## Project Structure

```text
backend/
├── manage.py
├── config/
│   ├── settings.py
│   └── urls.py
└── rag/
       ├── ai.py
       ├── knowledge.txt
       ├── retrieval.py
       ├── urls.py
       └── views.py

frontend/
└── src/
       ├── App.css
       ├── App.jsx
       └── main.jsx
```
# rag-project
