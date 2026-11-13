"""Role to permission mapping (F-ORG-02). Server side source of truth."""

from __future__ import annotations

ROLES = ("owner", "admin", "editor", "viewer")

_VIEWER = {"org:read", "forms:read", "responses:read", "analytics:read", "payments:read"}
_EDITOR = _VIEWER | {"forms:edit", "forms:publish", "responses:update", "responses:export", "folders:edit",
                     "tickets:scan"}
_ADMIN = _EDITOR | {"members:manage", "org:settings", "integrations:manage", "responses:delete",
                    "payments:manage", "audit:read", "trust:manage"}
_OWNER = _ADMIN | {"billing:manage", "org:delete", "owners:manage"}

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": frozenset(_VIEWER),
    "editor": frozenset(_EDITOR),
    "admin": frozenset(_ADMIN),
    "owner": frozenset(_OWNER),
}
ALL_PERMISSIONS = frozenset().union(*ROLE_PERMISSIONS.values())


def has_permission(role: str, permission: str, *, viewer_can_export: bool = False) -> bool:
    if permission == "responses:export" and role == "viewer":
        return viewer_can_export
    return permission in ROLE_PERMISSIONS.get(role, frozenset())
