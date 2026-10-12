"""Tool for managing memory and database storage backends (Local, Supabase, Postgres, MongoDB)."""

from __future__ import annotations

from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.storage.memory_backend import MemoryBackendManager
from openjarvis.tools._stubs import BaseTool, ToolSpec


@ToolRegistry.register("memory_backend_manage")
class MemoryBackendManageTool(BaseTool):
    """Inspect and attach external database storage (Supabase, PostgreSQL, MongoDB) for memory."""

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="memory_backend_manage",
            description=(
                "Manage memory storage backend. Check if Ultron is using local storage "
                "or attach external private databases (Supabase, PostgreSQL, MongoDB) "
                "so memory is stored in the user's isolated cloud database."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["status", "attach", "detach"],
                        "description": "Action: 'status' to view memory storage, 'attach' to connect cloud DB, 'detach' to revert to local.",
                    },
                    "backend_type": {
                        "type": "string",
                        "enum": ["supabase", "postgres", "mongodb"],
                        "description": "Cloud database provider to attach (Supabase, Postgres, or MongoDB).",
                    },
                    "connection_string": {
                        "type": "string",
                        "description": "Database connection URI (e.g. postgresql://... or mongodb+srv://...).",
                    },
                    "supabase_url": {
                        "type": "string",
                        "description": "Supabase Project URL (e.g. https://xyz.supabase.co).",
                    },
                    "supabase_key": {
                        "type": "string",
                        "description": "Supabase API Key / Service Role Key.",
                    },
                    "database_name": {
                        "type": "string",
                        "description": "Optional database name (default: ultron_memory).",
                    },
                },
                "required": ["action"],
            },
            category="memory",
        )

    def execute(self, **params: Any) -> ToolResult:
        action = str(params.get("action", "status")).lower().strip()

        if action == "status":
            info = MemoryBackendManager.get_status()
            return ToolResult(
                tool_name=self.spec.name,
                success=True,
                content=info["message"],
                metadata=info,
            )

        if action == "attach":
            b_type = str(params.get("backend_type", "supabase")).strip()
            conn_str = str(params.get("connection_string", "")).strip()
            supa_url = str(params.get("supabase_url", "")).strip()
            supa_key = str(params.get("supabase_key", "")).strip()
            db_name = str(params.get("database_name", "ultron_memory")).strip()

            result = MemoryBackendManager.attach_backend(
                backend_type=b_type,
                connection_string=conn_str,
                supabase_url=supa_url,
                supabase_key=supa_key,
                database_name=db_name,
            )
            return ToolResult(
                tool_name=self.spec.name,
                success=result.get("success", False),
                content=result.get("message")
                or result.get("error", "Failed to attach database"),
                metadata=result,
            )

        if action == "detach":
            result = MemoryBackendManager.detach_backend()
            return ToolResult(
                tool_name=self.spec.name,
                success=True,
                content=result["message"],
                metadata=result,
            )

        return ToolResult(
            tool_name=self.spec.name,
            success=False,
            content=f"Unknown action '{action}'. Supported actions: 'status', 'attach', 'detach'.",
        )


__all__ = ["MemoryBackendManageTool"]
