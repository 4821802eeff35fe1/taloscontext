import pytest

from app.core.rbac import (
    CAN_APPROVE_CONTENT,
    CAN_MANAGE_MEMBERS,
    PermissionDeniedError,
    require_role,
)
from app.models.enums import WorkspaceRole


def test_viewer_cannot_approve_content():
    with pytest.raises(PermissionDeniedError):
        require_role(WorkspaceRole.VIEWER, CAN_APPROVE_CONTENT)


def test_approver_can_approve_content():
    require_role(WorkspaceRole.APPROVER, CAN_APPROVE_CONTENT)


def test_owner_passes_every_check():
    require_role(WorkspaceRole.OWNER, CAN_MANAGE_MEMBERS)


def test_admin_cannot_manage_members():
    with pytest.raises(PermissionDeniedError):
        require_role(WorkspaceRole.ADMIN, CAN_MANAGE_MEMBERS)
