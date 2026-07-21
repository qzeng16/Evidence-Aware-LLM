"""Browser interface shell for the verification API."""

DEMO_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta
    name="viewport"
    content="width=device-width, initial-scale=1"
  >
  <meta
    name="description"
    content="Evidence-aware claim verification with transparent evidence and confidence."
  >
  <title>Evidence-Aware Claim Verification</title>

  <link rel="stylesheet" href="/assets/demo.css">
</head>

<body>
  <main class="shell">
    <header class="topbar">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true">EA</span>
        <span>Evidence-Aware LLM</span>
      </div>

      <nav class="nav" aria-label="Project links">
        <a href="/docs">API Docs</a>
        <a href="/health">Health</a>
        <a
          href="https://github.com/qzeng16/Evidence-Aware-LLM"
          target="_blank"
          rel="noopener noreferrer"
        >
          GitHub
        </a>
      </nav>
    </header>

    <section class="hero">
      <p class="eyebrow">Claim verification with traceable evidence</p>

      <h1>Verify claims, not just answers.</h1>

      <p class="subtitle">
        Submit a factual claim to retrieve relevant evidence and classify
        it as Supported, Refuted, or Uncertain. Every result includes a
        confidence score and the evidence used to reach the decision.
      </p>

      <div class="status-row">
        <span class="status-pill">
          <span
            id="status-dot"
            class="status-dot"
            aria-hidden="true"
          ></span>
          <span id="service-status">Checking API status</span>
        </span>

        <span class="status-pill">
          Mode:
          <strong id="verifier-mode">loading</strong>
        </span>

        <span class="status-pill">Docker + FastAPI</span>
      </div>
    </section>

    <section class="panel form-panel">
      <form id="verify-form">
        <label for="claim">Claim to verify</label>

        <textarea
          id="claim"
          name="claim"
          maxlength="3000"
          required
          placeholder="Example: Retrieval augmented generation can improve factual reliability."
        ></textarea>

        <div class="examples" aria-label="Example claims">
          <button
            class="example-button"
            type="button"
            data-claim="Retrieval augmented generation can improve factual reliability."
          >
            RAG reliability
          </button>

          <button
            class="example-button"
            type="button"
            data-claim="Large language models are always reliable on small biased datasets."
          >
            Biased datasets
          </button>

          <button
            class="example-button"
            type="button"
            data-claim="Large language models can generate unsupported scientific claims."
          >
            Hallucination risk
          </button>
        </div>

        <div class="actions">
          <p class="hint">
            Public demo uses the deterministic rule-based verifier.
          </p>

          <button
            id="submit-button"
            class="primary-button"
            type="submit"
          >
            Verify claim
          </button>
        </div>
      </form>

      <div
        id="error-message"
        class="error"
        role="alert"
        hidden
      ></div>
    </section>

    <section
      id="result"
      class="result"
      aria-live="polite"
      hidden
    >
      <article class="panel result-summary">
        <div>
          <span
            id="result-label"
            class="label-badge"
          ></span>

          <h2 id="result-title"></h2>

          <p id="result-reason" class="reason"></p>

          <p id="matched-ids" class="evidence-meta"></p>
        </div>

        <div class="confidence">
          <div>
            <div
              id="confidence-value"
              class="confidence-value"
            ></div>
            <div class="confidence-label">confidence</div>
          </div>
        </div>
      </article>

      <article class="panel evidence-panel">
        <div class="section-heading">
          <h3>Retrieved evidence</h3>
          <span id="evidence-count"></span>
        </div>

        <div id="evidence-list" class="evidence-list"></div>

        <details>
          <summary>View raw API response</summary>
          <pre id="raw-response"></pre>
        </details>
      </article>
    </section>

    <footer>
      <span>Evidence-Aware Claim Verification API</span>
      <span>Supported · Refuted · Uncertain</span>
    </footer>
  </main>

  <script src="/assets/demo.js" defer></script>
</body>
</html>
"""
