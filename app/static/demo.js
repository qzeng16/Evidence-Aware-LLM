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
