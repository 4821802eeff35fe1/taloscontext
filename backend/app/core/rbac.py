from app.models.enums import WorkspaceRole

_RANK = {
    WorkspaceRole.VIEWER: 0,
    WorkspaceRole.APPROVER: 1,
    WorkspaceRole.EDITOR: 2,
    WorkspaceRole.ADMIN: 3,
    WorkspaceRole.OWNER: 4,
}


class PermissionDeniedError(Exception):
    pass


def require_role(actual: WorkspaceRole, minimum: WorkspaceRole) -> None:
    """Raises if `actual` does not meet `minimum`. Always called server-side —
    the frontend role gating in the UI is cosmetic only (SECURITY.md).
    """
    if _RANK[actual] < _RANK[minimum]:
        raise PermissionDeniedError(
            f"Role {actual.value} does not meet required role {minimum.value}"
        )


CAN_EDIT_CONTENT = WorkspaceRole.EDITOR
CAN_APPROVE_CONTENT = WorkspaceRole.APPROVER
CAN_MANAGE_TELEGRAM = WorkspaceRole.ADMIN
CAN_MANAGE_SETTINGS = WorkspaceRole.ADMIN
CAN_MANAGE_MEMBERS = WorkspaceRole.OWNER
