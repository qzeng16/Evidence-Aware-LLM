"""Evidence-grounded LLM verifier implementation."""

from typing import Any, Dict, List

import layer0_verifier as core_verifier

from app.llm_clients import LLMClient
from app.llm_judge_contract import (
    LLM_JUDGE_JSON_SCHEMA,
)
from app.llm_judge_parser import (
    parse_llm_judge_response,
)
from app.llm_judge_prompt import (
    build_llm_judge_messages,
)
from app.verification_result import (
    VerificationResult,
    VerifierType,
)
from app.verifiers.base import VerificationRun


class LLMVerifier:
    """Verify claims using retrieved evidence and an LLM judge."""

    verifier_type = VerifierType.LLM

    def __init__(
        self,
        evidence_db: List[Dict[str, Any]],
        model: Any,
        evidence_embeddings: Any,
        client: LLMClient,
        initial_top_k: int = 4,
        final_top_k: int = 2,
        min_score: float = 0.20,
    ) -> None:
        """Store retrieval and LLM client dependencies."""

        self._evidence_db = evidence_db
        self._model = model
        self._evidence_embeddings = (
            evidence_embeddings
        )
        self._client = client
        self._initial_top_k = initial_top_k
        self._final_top_k = final_top_k
        self._min_score = min_score

    def _retrieve_evidence(
        self,
        claim: str,
    ) -> List[Dict[str, Any]]:
        """Retrieve evidence for one claim."""

        return core_verifier.search_evidence(
            claim=claim,
            evidence_list=self._evidence_db,
            model=self._model,
            evidence_embeddings=(
                self._evidence_embeddings
            ),
            initial_top_k=self._initial_top_k,
            final_top_k=self._final_top_k,
            min_score=self._min_score,
        )

    def verify(
        self,
        claim: str,
    ) -> VerificationRun:
        """Verify a claim through the evidence-grounded LLM judge."""

        evidence_results = self._retrieve_evidence(
            claim
        )

        if not evidence_results:
            reason = (
                "No relevant evidence was retrieved "
                "for the LLM judge."
            )

            verification_result = VerificationResult(
                label="Uncertain",
                confidence=0.3,
                reason=reason,
                verifier_type=self.verifier_type,
                matched_evidence_ids=(),
                matched_rule=None,
                abstention_reason=reason,
            )

            return VerificationRun(
                claim=claim,
                result=verification_result,
                evidence=(),
            )

        messages = build_llm_judge_messages(
            claim=claim,
            evidence_items=evidence_results,
        )

        client_response = self._client.generate(
            messages=messages,
            response_schema=(
                LLM_JUDGE_JSON_SCHEMA
            ),
        )

        available_evidence_ids = [
            evidence.get(
                "evidence_id",
                "",
            )
            for evidence in evidence_results
        ]

        judge_output = parse_llm_judge_response(
            raw_response=client_response.text,
            available_evidence_ids=(
                available_evidence_ids
            ),
        )

        verification_result = (
            judge_output.to_verification_result()
        )

        return VerificationRun(
            claim=claim,
            result=verification_result,
            evidence=tuple(evidence_results),
        )
