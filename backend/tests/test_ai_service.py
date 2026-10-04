
import pytest

from app.models.enums import AIOperation
from app.services.ai.fake_provider import FakeAIProvider, FakeImageProvider
from app.services.ai.service import AIService


@pytest.mark.asyncio
async def test_generate_post_returns_valid_result_and_records_one_ai_request(db_session, workspace):
    service = AIService(db_session, FakeAIProvider(), FakeImageProvider())
    workspace_id = workspace.id

    result, cost = await service.generate_post(
        workspace_id=workspace_id, content_item_id=None, tone_context="", knowledge_context="",
        recent_topics="", user_instruction="Write a post about CTR tips",
    )

    assert result.schema_version == 1
    assert result.title
    assert result.telegram_html
    assert cost >= 0

    from sqlalchemy import select

    from app.models.cost import AIRequest

    rows = (await db_session.execute(select(AIRequest))).scalars().all()
    assert len(rows) == 1
    assert rows[0].operation == AIOperation.GENERATE_POST
