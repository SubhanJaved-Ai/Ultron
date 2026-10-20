"""ChannelBridge — unified orchestrator for multi-channel messaging."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from openjarvis.channels._stubs import BaseChannel, ChannelStatus
from openjarvis.core.events import EventBus, EventType
from openjarvis.server.session_store import SessionStore

logger = logging.getLogger(__name__)

_DEFAULT_MAX_LENGTH = 4000
_SMS_MAX_LENGTH = 1600

_HELP_TEXT = """\
Available commands:
/agents — list running agents
/agent <id> status — agent state and current task
/agent <id> <message> — send a message to an agent
/agent <id> pause — pause an agent
/agent <id> resume — resume an agent
/subagents — list autonomous subagents and their progress
/subagent <id> — inspect subagent status and findings
/subagent <id> kill — terminate a subagent
/notify <channel> — set where to receive notifications
/sessions — list your active sessions
/more — get the rest of a truncated response
/help — show this message\
"""

# Events the bridge subscribes to for notifications
_NOTIFICATION_EVENTS = [
    EventType.AGENT_TICK_END,
    EventType.AGENT_TICK_ERROR,
    EventType.AGENT_BUDGET_EXCEEDED,
    EventType.SCHEDULER_TASK_END,
]


class ChannelBridge:
    """Orchestrates incoming messages across multiple channel adapters.

    Provides backward-compatible ``send()``/``status()``/``list_channels()``
    so it can replace the old single-channel bridge in ``app.state``.
    """

    def __init__(
        self,
        channels: Dict[str, BaseChannel],
        session_store: SessionStore,
        bus: EventBus,
        system: Any = None,
        agent_manager: Any = None,
        deep_research_agent: Any = None,
    ) -> None:
        self._channels = channels
        self._session_store = session_store
        self._bus = bus
        self._system = system
        self._agent_manager = agent_manager
        self._deep_research_agent = deep_research_agent
        self._notification_timestamps: Dict[str, float] = {}
        self._subscribe_notifications()

    # --------------------------------------------------------------
    # Backward-compatible BaseChannel interface
    # --------------------------------------------------------------

    def connect(self) -> None:
        for ch in self._channels.values():
            ch.connect()

    def disconnect(self) -> None:
        for ch in self._channels.values():
            ch.disconnect()

    def list_channels(self) -> List[str]:
        result: List[str] = []
        for ch in self._channels.values():
            result.extend(ch.list_channels())
        return result

    def status(self) -> ChannelStatus:
        statuses = [ch.status() for ch in self._channels.values()]
        if not statuses:
            return ChannelStatus.DISCONNECTED
        if any(s == ChannelStatus.CONNECTED for s in statuses):
            return ChannelStatus.CONNECTED
        if all(s == ChannelStatus.ERROR for s in statuses):
            return ChannelStatus.ERROR
        return ChannelStatus.DISCONNECTED

    def send(
        self,
        channel: str,
        content: str,
        *,
        conversation_id: str = "",
        metadata: Dict[str, Any] | None = None,
    ) -> bool:
        for ch in self._channels.values():
            if channel in ch.list_channels():
                return ch.send(
                    channel,
                    content,
                    conversation_id=conversation_id,
                    metadata=metadata,
                )
        logger.warning("No adapter found for channel %s", channel)
        return False

    # --------------------------------------------------------------
    # Incoming message handling
    # --------------------------------------------------------------

    def handle_incoming(
        self,
        sender_id: str,
        content: str,
        channel_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        max_length: int = _DEFAULT_MAX_LENGTH,
    ) -> str:
        self._session_store.get_or_create(sender_id, channel_type)

        # Command routing
        stripped = content.strip()
        if stripped.startswith("/"):
            result = self._handle_command(sender_id, stripped, channel_type)
            if result is not None:
                return result

        # Regular chat — route to JarvisSystem.ask()
        return self._handle_chat(sender_id, stripped, channel_type, max_length)

    # --------------------------------------------------------------
    # Command parsing
    # --------------------------------------------------------------

    def _handle_command(
        self,
        sender_id: str,
        content: str,
        channel_type: str,
    ) -> Optional[str]:
        parts = content.split(None, 2)
        cmd = parts[0].lower()

        if cmd == "/help":
            return _HELP_TEXT

        if cmd == "/more":
            return self._handle_more(sender_id, channel_type)

        if cmd == "/notify" and len(parts) >= 2:
            pref = parts[1]
            self._session_store.set_notification_preference(
                sender_id, channel_type, pref
            )
            return f"Notifications will be sent to {pref}."

        if cmd == "/sessions":
            return self._handle_sessions(sender_id)

        if cmd == "/agents":
            return self._handle_agents_list()

        if cmd == "/subagents":
            return self._handle_subagents_list()

        if cmd == "/subagent" and len(parts) >= 2:
            subagent_id = parts[1]
            rest = parts[2] if len(parts) > 2 else "status"
            return self._handle_subagent_command(subagent_id, rest)

        if cmd == "/pipeline" and len(parts) >= 2:
            return self._handle_pipeline_command(
                parts[1], parts[2] if len(parts) > 2 else ""
            )

        if cmd == "/blackboard":
            swarm_id = parts[1] if len(parts) >= 2 else "default"
            return self._handle_blackboard_command(swarm_id)

        if cmd == "/agent" and len(parts) >= 2:
            agent_id = parts[1]
            rest = parts[2] if len(parts) > 2 else "status"
            return self._handle_agent_command(agent_id, rest)

        # Unknown command — fall through to chat
        return None

    def _handle_more(self, sender_id: str, channel_type: str) -> str:
        session = self._session_store.get_or_create(sender_id, channel_type)
        pending = session.get("pending_response")
        if pending:
            self._session_store.clear_pending_response(sender_id, channel_type)
            return pending
        return "No pending response."

    def _handle_agents_list(self) -> str:
        if not self._agent_manager:
            return "No agent manager configured."
        agents = self._agent_manager.list_agents()
        if not agents:
            return "No agents currently running."
        lines = []
        for a in agents:
            name = a.get("name", a.get("agent_id", "unknown"))
            status = a.get("status", "unknown")
            lines.append(f"  {name} — {status}")
        return "Running agents:\n" + "\n".join(lines)

    def _handle_agent_command(self, agent_id: str, action: str) -> str:
        if not self._agent_manager:
            return "No agent manager configured."
        action_lower = action.strip().lower()
        if action_lower == "status":
            state = self._agent_manager.get_agent(agent_id)
            if state is None:
                return f"Agent '{agent_id}' not found."
            name = state.get("name", agent_id)
            status = state.get("status", "unknown")
            return f"Agent '{name}': {status}"
        if action_lower == "pause":
            self._agent_manager.pause_agent(agent_id)
            return f"Agent '{agent_id}' paused."
        if action_lower == "resume":
            self._agent_manager.resume_agent(agent_id)
            return f"Agent '{agent_id}' resumed."
        # Treat as a message to the agent
        result = self._agent_manager.send_message(agent_id, action)
        return str(result) if result else f"Message sent to agent '{agent_id}'."

    def _handle_subagents_list(self) -> str:
        try:
            from openjarvis.agents.subagents import get_subagent_manager

            mgr = get_subagent_manager()
            subagents = mgr.list_subagents()
            if not subagents:
                return "No active or recent subagents found."
            lines = []
            for s in subagents:
                data = s.to_dict()
                dur = f" ({data.get('duration_seconds', 0)}s)" if s.started_at else ""
                lines.append(
                    f"  [{s.id}] {s.name} — {s.status}{dur}\n    Task: {s.task[:80]}"
                )
            return "Subagents:\n" + "\n".join(lines)
        except Exception as exc:
            return f"Error listing subagents: {exc}"

    def _handle_subagent_command(self, subagent_id: str, action: str) -> str:
        try:
            from openjarvis.agents.subagents import get_subagent_manager

            mgr = get_subagent_manager()
            record = mgr.get(subagent_id)
            if not record:
                return f"Subagent '{subagent_id}' not found."

            act = action.strip().lower()
            if act in ("kill", "stop"):
                mgr.kill(subagent_id)
                return f"Subagent '{subagent_id}' stopped."
            if act == "result":
                return (
                    record.result
                    or f"Subagent status is '{record.status}'. No results yet."
                )

            status_line = (
                f"Subagent [{record.id}] {record.name}\n"
                f"Status: {record.status}\n"
                f"Task: {record.task}"
            )
            if record.result:
                preview = record.result[:800]
                status_line += f"\n\nFindings:\n{preview}"
                if len(record.result) > 800:
                    status_line += (
                        "\n... (send '/subagent <id> result' for full output)"
                    )
            elif record.error:
                status_line += f"\nError: {record.error}"
            return status_line
        except Exception as exc:
            return f"Error inspecting subagent: {exc}"

    def _handle_blackboard_command(self, swarm_id: str) -> str:
        try:
            from openjarvis.agents.subagents import get_subagent_manager

            mgr = get_subagent_manager()
            bb = mgr.get_blackboard(swarm_id)
            return f"Swarm Blackboard [{swarm_id}]:\n" + bb.to_summary_text()
        except Exception as exc:
            return f"Error retrieving blackboard: {exc}"

    def _handle_pipeline_command(self, first_arg: str, rest: str) -> str:
        try:
            from openjarvis.agents.subagents import get_subagent_manager

            mgr = get_subagent_manager()
            raw = f"{first_arg} {rest}".strip()
            if raw.startswith("["):
                stages = json.loads(raw)
            else:
                stages = [
                    {"name": "Researcher", "task": f"Research information on: {raw}"},
                    {
                        "name": "Analyst",
                        "task": (
                            "Synthesize findings and create a concise summary:\n\n"
                            "{previous_result}"
                        ),
                    },
                ]
            result = mgr.execute_pipeline(stages)
            return (
                f"Pipeline '{result.pipeline_name}' [{result.status}]:\n"
                f"Stages completed: {result.stages_completed}/{result.total_stages}\n\n"
                f"{result.final_output[:900]}"
            )
        except Exception as exc:
            return f"Error running pipeline: {exc}"

    # --------------------------------------------------------------
    # Chat handling
    # --------------------------------------------------------------

    def _handle_sessions(self, sender_id: str) -> str:
        targets = self._session_store.get_notification_targets()
        user_sessions = [t for t in targets if t["sender_id"] == sender_id]
        if not user_sessions:
            return "No active sessions with notification preferences."
        lines = []
        for s in user_sessions:
            lines.append(
                f"  {s['channel_type']} -> "
                f"notifications: {s['preferred_notification_channel']}"
            )
        return "Your sessions:\n" + "\n".join(lines)

    def _handle_chat(
        self,
        sender_id: str,
        content: str,
        channel_type: str,
        max_length: int,
    ) -> str:
        self._session_store.append_message(sender_id, channel_type, "user", content)

        # Build context from conversation history
        session = self._session_store.get_or_create(sender_id, channel_type)
        history = session.get("conversation_history", [])
        context_lines = []
        for msg in history[:-1]:  # exclude the message we just appended
            context_lines.append(f"{msg['role']}: {msg['content']}")
        context_str = "\n".join(context_lines)

        query = content
        if context_str:
            query = (
                f"Previous conversation:\n{context_str}\n\nCurrent message: {content}"
            )

        # Try DeepResearchAgent first
        if self._deep_research_agent is not None:
            try:
                result = self._deep_research_agent.run(content)
                response_text = result.content or "No results found."
            except Exception as exc:
                logger.error("DeepResearch agent failed: %s", exc)
                response_text = f"Research error: {exc}"
        elif self._system is not None:
            try:
                result = self._system.ask(query)
                response_text = result.get("content", str(result))
            except Exception:
                logger.exception("Error in JarvisSystem.ask()")
                error_msg = (
                    "Sorry, I couldn't process that right now. Try again in a moment."
                )
                self._session_store.append_message(
                    sender_id, channel_type, "assistant", error_msg
                )
                return error_msg
        else:
            error_msg = (
                "Sorry, I couldn't process that right now. Try again in a moment."
            )
            self._session_store.append_message(
                sender_id, channel_type, "assistant", error_msg
            )
            return error_msg

        # Format and possibly truncate
        formatted = self._format_response(
            sender_id, channel_type, response_text, max_length
        )
        self._session_store.append_message(
            sender_id, channel_type, "assistant", response_text
        )
        return formatted

    def _format_response(
        self,
        sender_id: str,
        channel_type: str,
        response: str,
        max_length: int,
    ) -> str:
        if len(response) <= max_length:
            return response
        # Truncate and store full response for /more retrieval
        truncation_notice = "\n\n... (reply /more for full response)"
        cut_at = max_length - len(truncation_notice)
        truncated = response[:cut_at] + truncation_notice
        self._session_store.set_pending_response(sender_id, channel_type, response)
        return truncated

    # --------------------------------------------------------------
    # Notifications
    # --------------------------------------------------------------

    def _subscribe_notifications(self) -> None:
        for event_type in _NOTIFICATION_EVENTS:
            self._bus.subscribe(event_type, self._on_notification_event)

    def _on_notification_event(self, event) -> None:  # noqa: ANN001
        event_key = str(event.event_type)
        now = time.time()

        # Rate limit: max 1 per event type per 5 minutes
        last = self._notification_timestamps.get(event_key, 0)
        if now - last < 300:
            return
        self._notification_timestamps[event_key] = now

        message = self._format_notification(event)
        if not message:
            return

        targets = self._session_store.get_notification_targets()
        for target in targets:
            pref_channel = target["preferred_notification_channel"]
            sender_id = target["sender_id"]
            self._send_notification(pref_channel, sender_id, message)

    def _format_notification(  # noqa: ANN201
        self,
        event,  # noqa: ANN001
    ) -> Optional[str]:
        data = event.data or {}
        name = data.get("agent_name", data.get("name", "unknown"))

        if event.event_type == EventType.AGENT_TICK_END:
            summary = data.get("summary", data.get("result", ""))
            return f"Agent '{name}' finished: {summary}" if summary else None
        if event.event_type == EventType.AGENT_TICK_ERROR:
            error = data.get("error", "unknown error")
            return f"Agent '{name}' error: {error}"
        if event.event_type == EventType.AGENT_BUDGET_EXCEEDED:
            return f"Agent '{name}' hit budget limit."
        if event.event_type == EventType.SCHEDULER_TASK_END:
            if data.get("success", True):
                return f"Scheduled task '{name}' completed."
            error = data.get("error", "unknown error")
            return f"Scheduled task '{name}' failed: {error}"
        return None

    def _send_notification(
        self,
        channel_type: str,
        sender_id: str,
        message: str,
    ) -> None:
        ch = self._channels.get(channel_type)
        if ch is None:
            logger.warning(
                "No adapter for notification channel %s",
                channel_type,
            )
            return
        try:
            ch.send(sender_id, message)
        except Exception:
            logger.exception("Failed to send notification to %s", channel_type)
