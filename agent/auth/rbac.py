"""
Monitor_v2 — RBAC Engine
Load rbac.yaml → validate user quyền cho command.
"""

import os
from functools import lru_cache
from typing import Optional

import structlog
import yaml

log = structlog.get_logger()

RBAC_PATH = os.getenv("RBAC_CONFIG_PATH", "/app/config/rbac.yaml")


@lru_cache(maxsize=1)
def _load_config() -> dict:
    with open(RBAC_PATH) as f:
        return yaml.safe_load(f)


def reload_config():
    """Gọi khi file rbac.yaml thay đổi để clear cache."""
    _load_config.cache_clear()
    log.info("rbac.config.reloaded")


def get_user(telegram_id: str) -> Optional[dict]:
    config = _load_config()
    for user in config.get("users", []):
        if str(user["telegram_id"]) == str(telegram_id):
            return user
    return None


def get_allowed_commands(telegram_id: str) -> set[str]:
    user = get_user(telegram_id)
    if not user:
        return set()

    config = _load_config()
    # roles in rbac.yaml are stored as a mapping: role_name -> role_data.
    roles_map = {}
    for role_name, role_data in config.get("roles", {}).items():
        roles_map[role_name] = role_data

    allowed = set()
    for role_name in user.get("roles", []):
        role = roles_map.get(role_name, {})
        cmds = role.get("allowed_commands", [])
        if "*" in cmds:
            allowed.add("*")
        else:
            allowed.update(cmds)

    return allowed


def get_requires_approval(telegram_id: str) -> set[str]:
    user = get_user(telegram_id)
    if not user:
        return set()

    config = _load_config()
    roles_map = {k: v for k, v in config.get("roles", {}).items()}

    approval_required = set()
    for role_name in user.get("roles", []):
        role = roles_map.get(role_name, {})
        approval_required.update(role.get("requires_approval", []))

    return approval_required


def can_approve(telegram_id: str) -> bool:
    user = get_user(telegram_id)
    if not user:
        return False

    config = _load_config()
    roles_map = {k: v for k, v in config.get("roles", {}).items()}

    for role_name in user.get("roles", []):
        role = roles_map.get(role_name, {})
        if role.get("can_approve", False):
            return True
    return False


def is_command_allowed(telegram_id: str, command: str) -> bool:
    allowed = get_allowed_commands(telegram_id)
    return "*" in allowed or command in allowed


def check_access(telegram_id: str, command: str) -> dict:
    """
    Returns:
        {"allowed": bool, "needs_approval": bool, "reason": str}
    """
    user = get_user(telegram_id)
    if not user:
        return {"allowed": False, "needs_approval": False, "reason": "User không tồn tại trong RBAC config"}

    if not is_command_allowed(telegram_id, command):
        return {"allowed": False, "needs_approval": False, "reason": f"Role của bạn không có quyền chạy `{command}`"}

    needs_approval = command in get_requires_approval(telegram_id)
    return {
        "allowed": True,
        "needs_approval": needs_approval,
        "reason": "ok",
    }


def get_approvers() -> list[dict]:
    """Trả về list user có quyền approve."""
    config = _load_config()
    return [u for u in config.get("users", []) if can_approve(u["telegram_id"])]
