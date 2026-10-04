import pytest

from app.models.content import ContentItem
from app.models.enums import ContentStatus
from app.services.content.service import ContentService, InvalidTransitionError


def _item(status: ContentStatus) -> ContentItem:
    return ContentItem(workspace_id=None, status=status)


def test_draft_cannot_jump_directly_to_published():
    service = ContentService(session=None, ai_service=None)
    item = _item(ContentStatus.DRAFT)
    with pytest.raises(InvalidTransitionError):
        service.assert_transition(item, ContentStatus.PUBLISHED)


def test_valid_chain_draft_to_published():
    service = ContentService(session=None, ai_service=None)
    item = _item(ContentStatus.DRAFT)

    service.assert_transition(item, ContentStatus.PENDING_APPROVAL)
    item.status = ContentStatus.PENDING_APPROVAL

    service.assert_transition(item, ContentStatus.APPROVED)
    item.status = ContentStatus.APPROVED

    service.assert_transition(item, ContentStatus.SCHEDULED)
    item.status = ContentStatus.SCHEDULED

    service.assert_transition(item, ContentStatus.PUBLISHING)
    item.status = ContentStatus.PUBLISHING

    service.assert_transition(item, ContentStatus.PUBLISHED)


def test_archived_is_terminal():
    service = ContentService(session=None, ai_service=None)
    item = _item(ContentStatus.ARCHIVED)
    with pytest.raises(InvalidTransitionError):
        service.assert_transition(item, ContentStatus.DRAFT)


def test_partially_published_can_resume_publishing_for_retries():
    service = ContentService(session=None, ai_service=None)
    item = _item(ContentStatus.PARTIALLY_PUBLISHED)
    service.assert_transition(item, ContentStatus.PUBLISHING)
