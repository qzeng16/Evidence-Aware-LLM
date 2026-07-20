"""Self-contained browser interface for the verification API."""

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

  <style>
    :root {
      color-scheme: dark;
      --background: #070b14;
      --surface: rgba(17, 24, 39, 0.86);
      --surface-strong: #111827;
      --border: rgba(148, 163, 184, 0.22);
      --text: #f8fafc;
      --muted: #a7b0c0;
      --accent: #8b5cf6;
      --accent-light: #c4b5fd;
      --success: #34d399;
      --danger: #fb7185;
      --warning: #fbbf24;
      --shadow: 0 28px 90px rgba(0, 0, 0, 0.38);
    }

    * {
      box-sizing: border-box;
    }

    body {
      min-height: 100vh;
      margin: 0;
      font-family:
        Inter,
        ui-sans-serif,
        system-ui,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
      color: var(--text);
      background:
        radial-gradient(
          circle at 12% 12%,
          rgba(124, 58, 237, 0.26),
          transparent 34%
        ),
        radial-gradient(
          circle at 88% 18%,
          rgba(14, 165, 233, 0.18),
          transparent 30%
        ),
        var(--background);
    }

    a {
      color: inherit;
    }

    button,
    textarea {
      font: inherit;
    }

    .shell {
      width: min(1120px, calc(100% - 32px));
      margin: 0 auto;
      padding: 28px 0 48px;
    }

    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
      margin-bottom: 72px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      font-weight: 750;
      letter-spacing: -0.02em;
    }

    .brand-mark {
      display: grid;
      width: 38px;
      height: 38px;
      place-items: center;
      border: 1px solid rgba(196, 181, 253, 0.36);
      border-radius: 12px;
      background: rgba(124, 58, 237, 0.16);
      color: var(--accent-light);
    }

    .nav {
      display: flex;
      gap: 18px;
      color: var(--muted);
      font-size: 0.94rem;
    }

    .nav a {
      text-decoration: none;
    }

    .nav a:hover {
      color: var(--text);
    }

    .hero {
      max-width: 820px;
      margin-bottom: 38px;
    }

    .eyebrow {
      margin: 0 0 16px;
      color: var(--accent-light);
      font-size: 0.8rem;
      font-weight: 750;
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }

    h1 {
      max-width: 780px;
      margin: 0;
      font-size: clamp(2.6rem, 7vw, 5.7rem);
      line-height: 0.98;
      letter-spacing: -0.065em;
    }

    .subtitle {
      max-width: 680px;
      margin: 24px 0 0;
      color: var(--muted);
      font-size: clamp(1rem, 2vw, 1.2rem);
      line-height: 1.7;
    }

    .status-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 24px;
    }

    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 34px;
      padding: 0 13px;
      border: 1px solid var(--border);
      border-radius: 999px;
      background: rgba(15, 23, 42, 0.55);
      color: var(--muted);
      font-size: 0.84rem;
    }

    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--warning);
      box-shadow: 0 0 18px currentColor;
    }

    .status-dot.ready {
      background: var(--success);
    }

    .panel {
      border: 1px solid var(--border);
      border-radius: 24px;
      background: var(--surface);
      box-shadow: var(--shadow);
      backdrop-filter: blur(18px);
    }

    .form-panel {
      padding: clamp(20px, 4vw, 34px);
    }

    label {
      display: block;
      margin-bottom: 11px;
      font-size: 0.94rem;
      font-weight: 700;
    }

    textarea {
      width: 100%;
      min-height: 150px;
      resize: vertical;
      padding: 18px;
      border: 1px solid var(--border);
      border-radius: 16px;
      outline: none;
      background: rgba(2, 6, 23, 0.68);
      color: var(--text);
      line-height: 1.6;
      transition:
        border-color 160ms ease,
        box-shadow 160ms ease;
    }

    textarea:focus {
      border-color: rgba(139, 92, 246, 0.78);
      box-shadow: 0 0 0 4px rgba(139, 92, 246, 0.14);
    }

    textarea::placeholder {
      color: #6b7280;
    }

    .examples {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 14px 0 22px;
    }

    .example-button {
      padding: 8px 11px;
      border: 1px solid var(--border);
      border-radius: 10px;
      background: transparent;
      color: var(--muted);
      cursor: pointer;
    }

    .example-button:hover {
      border-color: rgba(196, 181, 253, 0.52);
      color: var(--text);
    }

    .actions {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
    }

    .hint {
      margin: 0;
      color: var(--muted);
      font-size: 0.84rem;
    }

    .primary-button {
      min-width: 150px;
      min-height: 48px;
      padding: 0 22px;
      border: 0;
      border-radius: 13px;
      background:
        linear-gradient(
          135deg,
          #7c3aed,
          #4f46e5
        );
      color: white;
      font-weight: 750;
      cursor: pointer;
      box-shadow: 0 14px 34px rgba(79, 70, 229, 0.3);
    }

    .primary-button:disabled {
      cursor: wait;
      opacity: 0.65;
    }

    .error {
      margin-top: 18px;
      padding: 14px 16px;
      border: 1px solid rgba(251, 113, 133, 0.4);
      border-radius: 12px;
      background: rgba(159, 18, 57, 0.15);
      color: #fecdd3;
      line-height: 1.55;
    }

    .result {
      display: grid;
      gap: 20px;
      margin-top: 24px;
    }

    .result-summary {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 24px;
      padding: clamp(22px, 4vw, 34px);
    }

    .label-badge {
      display: inline-flex;
      align-items: center;
      min-height: 34px;
      padding: 0 13px;
      border-radius: 999px;
      font-size: 0.84rem;
      font-weight: 800;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }

    .label-supported {
      background: rgba(16, 185, 129, 0.14);
      color: #6ee7b7;
    }

    .label-refuted {
      background: rgba(244, 63, 94, 0.14);
      color: #fda4af;
    }

    .label-uncertain {
      background: rgba(245, 158, 11, 0.14);
      color: #fcd34d;
    }

    .result h2 {
      margin: 18px 0 10px;
      font-size: clamp(1.4rem, 3vw, 2rem);
      letter-spacing: -0.03em;
    }

    .reason {
      margin: 0;
      color: var(--muted);
      line-height: 1.7;
      white-space: pre-wrap;
    }

    .confidence {
      display: grid;
      width: 132px;
      height: 132px;
      place-items: center;
      align-self: center;
      border: 1px solid var(--border);
      border-radius: 50%;
      background: rgba(2, 6, 23, 0.48);
    }

    .confidence-value {
      font-size: 1.7rem;
      font-weight: 800;
      letter-spacing: -0.04em;
    }

    .confidence-label {
      color: var(--muted);
      font-size: 0.75rem;
      text-transform: uppercase;
    }

    .evidence-panel {
      padding: clamp(22px, 4vw, 34px);
    }

    .section-heading {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 18px;
    }

    .section-heading h3 {
      margin: 0;
      font-size: 1.2rem;
    }

    .section-heading span {
      color: var(--muted);
      font-size: 0.84rem;
    }

    .evidence-list {
      display: grid;
      gap: 12px;
    }

    .evidence-card {
      padding: 17px;
      border: 1px solid var(--border);
      border-radius: 15px;
      background: rgba(2, 6, 23, 0.42);
    }

    .evidence-card h4 {
      margin: 0 0 8px;
      font-size: 0.96rem;
    }

    .evidence-card p {
      margin: 0;
      color: var(--muted);
      line-height: 1.65;
      white-space: pre-wrap;
    }

    .evidence-meta {
      margin-top: 11px;
      color: #818cf8;
      font-size: 0.78rem;
    }

    details {
      margin-top: 18px;
      color: var(--muted);
    }

    summary {
      cursor: pointer;
    }

    pre {
      max-height: 360px;
      overflow: auto;
      padding: 16px;
      border-radius: 12px;
      background: #020617;
      color: #cbd5e1;
      font-size: 0.78rem;
      line-height: 1.55;
      white-space: pre-wrap;
      word-break: break-word;
    }

    footer {
      display: flex;
      justify-content: space-between;
      gap: 20px;
      margin-top: 34px;
      color: var(--muted);
      font-size: 0.82rem;
    }

    [hidden] {
      display: none !important;
    }

    @media (max-width: 700px) {
      .topbar {
        align-items: flex-start;
        margin-bottom: 52px;
      }

      .nav {
        flex-direction: column;
        gap: 7px;
        text-align: right;
      }

      .actions,
      footer {
        align-items: stretch;
        flex-direction: column;
      }

      .primary-button {
        width: 100%;
      }

      .result-summary {
        grid-template-columns: 1fr;
      }

      .confidence {
        width: 112px;
        height: 112px;
      }
    }
  </style>
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

  <script>
    const form = document.getElementById("verify-form");
    const claimInput = document.getElementById("claim");
    const submitButton = document.getElementById("submit-button");
    const errorMessage = document.getElementById("error-message");
    const resultSection = document.getElementById("result");
    const resultLabel = document.getElementById("result-label");
    const resultTitle = document.getElementById("result-title");
    const resultReason = document.getElementById("result-reason");
    const confidenceValue =
      document.getElementById("confidence-value");
    const matchedIds = document.getElementById("matched-ids");
    const evidenceCount =
      document.getElementById("evidence-count");
    const evidenceList =
      document.getElementById("evidence-list");
    const rawResponse =
      document.getElementById("raw-response");

    function setBusy(isBusy) {
      submitButton.disabled = isBusy;
      submitButton.textContent = isBusy
        ? "Verifying..."
        : "Verify claim";
    }

    function showError(message) {
      errorMessage.textContent = message;
      errorMessage.hidden = false;
    }

    function clearError() {
      errorMessage.hidden = true;
      errorMessage.textContent = "";
    }

    async function requestJson(path, options = {}) {
      const response = await fetch(path, options);
      const text = await response.text();

      let body;

      try {
        body = text ? JSON.parse(text) : {};
      } catch {
        body = { detail: text || "Invalid server response." };
      }

      if (!response.ok) {
        const detail =
          body.detail ||
          body.message ||
          `Request failed with HTTP ${response.status}.`;

        throw new Error(
          typeof detail === "string"
            ? detail
            : JSON.stringify(detail)
        );
      }

      return body;
    }

    function normalizeConfidence(value) {
      const number = Number(value);

      if (!Number.isFinite(number)) {
        return null;
      }

      const percentage = number <= 1
        ? number * 100
        : number;

      return Math.max(0, Math.min(100, percentage));
    }

    function resultClass(label) {
      const normalized = String(label).toLowerCase();

      if (normalized === "supported") {
        return "label-supported";
      }

      if (normalized === "refuted") {
        return "label-refuted";
      }

      return "label-uncertain";
    }

    function getEvidence(response, verification) {
      const data = response.data || {};

      const candidates = [
        data.evidence,
        data.retrieved_evidence,
        verification.evidence,
      ];

      return candidates.find(Array.isArray) || [];
    }

    function evidenceText(item) {
      return (
        item.text ||
        item.content ||
        item.passage ||
        item.snippet ||
        "No evidence text was returned."
      );
    }

    function renderEvidence(items) {
      evidenceList.replaceChildren();
      evidenceCount.textContent =
        `${items.length} item${items.length === 1 ? "" : "s"}`;

      if (items.length === 0) {
        const empty = document.createElement("div");
        empty.className = "evidence-card";

        const text = document.createElement("p");
        text.textContent =
          "No detailed evidence records were returned for this result.";

        empty.appendChild(text);
        evidenceList.appendChild(empty);
        return;
      }

      items.forEach((item, index) => {
        const card = document.createElement("article");
        card.className = "evidence-card";

        const title = document.createElement("h4");
        title.textContent =
          item.title ||
          item.evidence_id ||
          `Evidence ${index + 1}`;

        const text = document.createElement("p");
        text.textContent = evidenceText(item);

        card.appendChild(title);
        card.appendChild(text);

        const metadata = [];

        if (item.evidence_id) {
          metadata.push(`ID: ${item.evidence_id}`);
        }

        if (item.source) {
          metadata.push(`Source: ${item.source}`);
        }

        if (item.score !== undefined) {
          metadata.push(`Score: ${item.score}`);
        }

        if (metadata.length > 0) {
          const meta = document.createElement("div");
          meta.className = "evidence-meta";
          meta.textContent = metadata.join(" · ");
          card.appendChild(meta);
        }

        evidenceList.appendChild(card);
      });
    }

    function renderResult(response) {
      const data = response.data || {};
      const verification = data.verification || {};
      const metadata = response.metadata || {};

      const label = verification.label || "Uncertain";
      const confidence =
        normalizeConfidence(verification.confidence);

      resultLabel.textContent = label;
      resultLabel.className =
        `label-badge ${resultClass(label)}`;

      resultTitle.textContent =
        `${label} by ${verification.verifier_type || "active"} verifier`;

      resultReason.textContent =
        verification.rationale ||
        verification.reason ||
        verification.explanation ||
        verification.decision_reason ||
        "The verifier returned no additional explanation.";

      confidenceValue.textContent =
        confidence === null
          ? "N/A"
          : `${confidence.toFixed(1)}%`;

      const ids =
        verification.matched_evidence_ids || [];

      matchedIds.textContent = ids.length > 0
        ? `Matched evidence: ${ids.join(", ")}`
        : `Verifier mode: ${
            metadata.active_verifier_mode ||
            verification.verifier_type ||
            "unknown"
          }`;

      renderEvidence(getEvidence(response, verification));

      rawResponse.textContent = JSON.stringify(
        response,
        null,
        2
      );

      resultSection.hidden = false;
      resultSection.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }

    async function loadHealth() {
      const statusText =
        document.getElementById("service-status");
      const statusDot =
        document.getElementById("status-dot");
      const mode =
        document.getElementById("verifier-mode");

      try {
        const health = await requestJson("/health");

        statusText.textContent =
          health.status === "ready"
            ? "API ready"
            : health.status || "API available";

        statusDot.classList.add("ready");

        mode.textContent =
          health.verifier_mode ||
          health.active_verifier_mode ||
          "unknown";
      } catch {
        statusText.textContent = "API status unavailable";
        mode.textContent = "unknown";
      }
    }

    document.querySelectorAll("[data-claim]").forEach(
      (button) => {
        button.addEventListener("click", () => {
          claimInput.value = button.dataset.claim;
          claimInput.focus();
        });
      }
    );

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      clearError();

      const claim = claimInput.value.trim();

      if (!claim) {
        showError("Enter a claim before running verification.");
        return;
      }

      setBusy(true);

      try {
        const response = await requestJson("/verify", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ claim }),
        });

        renderResult(response);
      } catch (error) {
        showError(
          error instanceof Error
            ? error.message
            : "Verification failed."
        );
      } finally {
        setBusy(false);
      }
    });

    loadHealth();
  </script>
</body>
</html>
"""
