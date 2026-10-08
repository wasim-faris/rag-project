import { useState } from "react";

const EXAMPLE_QUESTIONS = [
  "Where is the office located?",
  "What are the working hours?",
  "How many casual leaves do employees get?",
  "What documents are required for driver onboarding?",
];
const NO_CONTEXT = "No relevant information found.";

function finalAnswer(value) {
  if (typeof value !== "string" || !value.trim()) return "";
  if (/^(?:no answer returned|the model did not provide a final answer)\.?$/i.test(value.trim())) {
    return "";
  }

  const sentences = value
    .replace(/^\s*(?:final answer|answer)\s*:\s*/i, "")
    .split(/(?<=[.!?])\s+|\n+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean)
    .filter(
      (sentence) =>
        !/^(?:the user is asking|the question is asking|the context states|so the answer should be|i need to|let me think|analysis\s*:|reasoning\s*:|chain of thought\s*:)/i.test(
          sentence,
        ),
    );

  return sentences.join(" ");
}

function isLimitation(answer) {
  return /don['’]t have enough information|do not have enough information|unable to (?:determine|answer)|cannot determine|can['’]t determine|not enough information|don['’]t know/i.test(
    answer,
  );
}

function App() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const contextAvailable = Boolean(
    result?.retrieved_context &&
      result.retrieved_context !== NO_CONTEXT,
  );
  const withoutAnswer = result ? finalAnswer(result.without_context) : "";
  const withAnswer = result ? finalAnswer(result.with_context) : "";
  const withAnswerAvailable = Boolean(withAnswer);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!question.trim() || isLoading) return;

    setIsLoading(true);
    setError("");
    setResult(null);

    try {
      // React makes one request; Django handles retrieval and both AI calls.
      const response = await fetch("/api/ask/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question.trim() }),
      });
      let data = {};
      try {
        data = await response.json();
      } catch {
        data = {};
      }
      if (!response.ok) {
        console.error("[RAG demo] API request failed", {
          status: response.status,
          body: data,
        });
        if (response.status === 429) {
          setError("OpenRouter rate limit reached (HTTP 429). Please wait before trying again.");
        } else if (data.content_empty) {
          setError(
            `OpenRouter returned an empty final answer (HTTP ${data.http_status ?? response.status}; model: ${data.model || "unknown"}; finish_reason: ${data.finish_reason || "unknown"}; content_empty: true).`,
          );
        } else {
          setError(data.error || `OpenRouter request failed (HTTP ${response.status}).`);
        }
        return;
      }
      if (!finalAnswer(data?.without_context) || !finalAnswer(data?.with_context)) {
        console.error("[RAG demo] OpenRouter returned an incomplete comparison", data);
        setError("OpenRouter returned an empty answer. No comparison output was added.");
        return;
      }
      setResult(data && typeof data === "object" ? data : {});
    } catch (requestError) {
      console.error("[RAG demo] Request error", requestError);
      setError("We couldn't reach the AI service. Check your connection and try again.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="page-shell">
      <header className="page-header">
        <h1>Simple RAG AI Demo</h1>
        <p className="intro">Compare AI answers with and without retrieved external context.</p>
      </header>

      <section className="ask-section" aria-labelledby="question-heading">
        <h2 id="question-heading">Ask a question about TechNova</h2>
        <form onSubmit={handleSubmit}>
          <label className="visually-hidden" htmlFor="question-input">
            Your question
          </label>
          <textarea
            id="question-input"
            rows="2"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="How many casual leaves do employees get?"
          />
          <div className="submit-row">
            <span className="api-note">One question · two answer conditions</span>
            <button type="submit" disabled={isLoading || !question.trim()}>
              {isLoading ? <><span className="spinner" aria-hidden="true" /> Asking AI...</> : "Ask AI"}
            </button>
          </div>
        </form>

        <div className="examples">
          <h3>Example questions</h3>
          <div className="example-list">
            {EXAMPLE_QUESTIONS.map((example) => (
              <button
                className="example-button"
                key={example}
                type="button"
                onClick={() => setQuestion(example)}
              >
                {example}
              </button>
            ))}
          </div>
        </div>
        {error && (
          <div className="error-card" role="alert">
            <strong>Request not completed</strong>
            <span>{error}</span>
          </div>
        )}
      </section>

      {isLoading && (
        <div className="loading-state" role="status" aria-live="polite">
          <span className="spinner" aria-hidden="true" /> Retrieving context and generating both answers...
        </div>
      )}

      {result && (
        <section className="results" aria-live="polite">
          <article className={`step-card retrieval-card ${contextAvailable ? "is-relevant" : "is-empty"}`}>
            <div className="step-heading">
              <span className="step-number">01</span>
              <div>
                <p className="eyebrow">Step 1 · Retrieval</p>
                <h2>Retrieved Context</h2>
              </div>
            </div>
            <div className="context-output">
              {contextAvailable ? result.retrieved_context : "No relevant information was found for this question."}
            </div>
            <div className="retrieval-meta">
              <span>Relevance Score: <strong>{Number.isFinite(result.relevance_score) ? result.relevance_score : "Not provided"}</strong></span>
              <span className={`context-status ${contextAvailable ? "is-used" : "is-not-used"}`}>
                Context Used: {contextAvailable ? "Yes" : "No"}
              </span>
            </div>
          </article>

          <div className="answer-grid">
            <article className="step-card answer-section no-context-card">
              <div className="step-heading">
                <span className="step-number">02</span>
                <div>
                  <p className="eyebrow">Step 2 · Without context</p>
                  <h2>Question Only</h2>
                </div>
              </div>
              <p className="answer-caption">Answer Without Context</p>
              <p className="answer-text">{withoutAnswer}</p>
              <span className="answer-badge is-limited">No external context</span>
            </article>
            <article className={`step-card answer-section grounded-answer ${contextAvailable ? "" : "is-unavailable"}`}>
              <div className="step-heading">
                <span className="step-number">03</span>
                <div>
                  <p className="eyebrow">Step 3 · With context</p>
                  <h2>Context + Question</h2>
                </div>
              </div>
              <p className="answer-caption">Answer With Context</p>
              <p className="answer-text">{withAnswer}</p>
              <span className={`answer-badge ${contextAvailable && withAnswerAvailable ? "is-grounded" : "is-unavailable-badge"}`}>
                {contextAvailable && withAnswerAvailable
                  ? "Answer grounded in retrieved context"
                  : "No relevant context available"}
              </span>
            </article>
          </div>

          <section className="analysis-section" aria-labelledby="analysis-heading">
            <div className="analysis-heading">
              <div>
                <p className="eyebrow">Answer comparison</p>
                <h2 id="analysis-heading">Accuracy Analysis</h2>
              </div>
              <span className="analysis-note">Based on this request</span>
            </div>
            <div className="analysis-grid">
              <div className="analysis-item analysis-without">
                <strong>Without Context</strong>
                <span>{isLimitation(withoutAnswer)
                  ? "Unable to provide company-specific information"
                  : "Answer generated without company-specific context"}</span>
              </div>
              <div className="analysis-item analysis-with">
                <strong>With Context</strong>
                <span>{contextAvailable && withAnswerAvailable
                  ? "Retrieved information was available to support the answer"
                  : contextAvailable
                    ? "Retrieved information was available, but no final answer was returned"
                    : "No relevant information was retrieved for a grounded answer"}</span>
              </div>
              <div className="analysis-item analysis-improvement">
                <strong>Improvement</strong>
                <span>{contextAvailable && withAnswerAvailable
                  ? isLimitation(withoutAnswer)
                    ? "Retrieved context supplied company information missing from the question-only answer."
                    : "The context-assisted answer can be checked against the retrieved source above."
                  : "This request did not produce both relevant context and a context-assisted answer."}</span>
              </div>
            </div>
          </section>
        </section>
      )}
      <footer><span className="footer-mark" aria-hidden="true">R</span> TechNova · Retrieval-augmented answer comparison</footer>
    </main>
  );
}

export default App;
