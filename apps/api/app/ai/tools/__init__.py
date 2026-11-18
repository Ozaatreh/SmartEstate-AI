"""AI tool registry and the registered tools (Phase 6C)."""

from __future__ import annotations

from functools import lru_cache

from app.ai.tools.registry import Tool, ToolContext, ToolOutcome, ToolRegistry, ToolResult

__all__ = ["Tool", "ToolContext", "ToolOutcome", "ToolRegistry", "ToolResult", "default_registry"]


@lru_cache
def default_registry() -> ToolRegistry:
    from app.ai.tools.internal import INTERNAL_TOOLS
    from app.ai.tools.public import PUBLIC_TOOLS

    return ToolRegistry([*INTERNAL_TOOLS, *PUBLIC_TOOLS])
