from uuid import uuid4

import pytest
from pydantic import ValidationError

from twinops.rag.public_models import AssistantQueryRequest


def test_query_contract_trims_question_and_accepts_at_most_four_bounded_turns():
    request = AssistantQueryRequest.model_validate(
        {
            "question": "  Como verificar o rolamento?  ",
            "conversationId": str(uuid4()),
            "history": [
                {"question": f"q{index}", "answer": f"a{index}"}
                for index in range(4)
            ],
        }
    )

    assert request.question == "Como verificar o rolamento?"
    assert len(request.history) == 4


@pytest.mark.parametrize(
    "payload",
    [
        {"question": ""},
        {"question": " "},
        {"question": "x" * 501},
        {
            "question": "ok",
            "history": [
                {"question": "q", "answer": "a"} for _ in range(5)
            ],
        },
        {"question": "ok", "assessment": {"status": "alert"}},
        {
            "question": "ok",
            "history": [{"question": "q", "answer": "a", "evidence": []}],
        },
    ],
)
def test_query_contract_rejects_invalid_or_browser_supplied_authority(payload):
    with pytest.raises(ValidationError):
        AssistantQueryRequest.model_validate(payload)
