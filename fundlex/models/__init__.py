"""Model role configuration (primary vs independent review)."""
from .config import ModelRoleConfig, RoleConfigError, load_role_config
from .roles import RoleGateway, build_role_gateway, role_for_task

__all__ = ["ModelRoleConfig", "RoleConfigError", "load_role_config",
           "RoleGateway", "build_role_gateway", "role_for_task"]
