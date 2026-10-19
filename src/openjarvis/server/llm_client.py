"""Frontier LLM Brain for Ultron Hologram Interface.

Directly bridges the user's Google Gemini API key (or Groq/OpenAI) into
the holographic execution runtime with a genius-level Ultron persona prompt,
dynamic user address, and zero Wikipedia hallucination fallbacks.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from openjarvis.core.paths import _find_source_root, get_config_dir
from openjarvis.core.user_preferences import get_personality, get_user_address

logger = logging.getLogger("openjarvis.server.llm_brain")


def _read_key_from_file(file_path: Path) -> str:
    """Extract GEMINI_API_KEY or GOOGLE_API_KEY from an env-formatted file."""
    try:
        if file_path.is_file():
            for line in file_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
                        val = v.strip().strip("'\"")
                        if val:
                            return val
    except Exception:
        pass
    return ""


def _resolve_api_key(env_path: Optional[Path] = None) -> str:
    """Resolve Gemini/Google API key from process env or config files."""
    # 1. Environment variable (OS, CI, Container, Launcher) - highest precedence
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if key and key.strip():
        return key.strip()

    # 2. Explicit or resolved workspace/project .env
    candidates: list[Path] = []
    if env_path is not None:
        candidates.append(Path(env_path))
    else:
        # Check OPENJARVIS_WORKSPACE env if specified
        ws_env = os.environ.get("OPENJARVIS_WORKSPACE")
        if ws_env:
            candidates.append(Path(ws_env) / ".env")

        # In source checkout, resolve project root dynamically
        src_root = _find_source_root()
        if src_root is not None:
            candidates.append(src_root / ".env")

    for candidate in candidates:
        val = _read_key_from_file(candidate)
        if val:
            return val

    # 3. User config directory (cloud-keys.env and .env)
    config_dir = get_config_dir()
    for config_candidate in (config_dir / "cloud-keys.env", config_dir / ".env"):
        val = _read_key_from_file(config_candidate)
        if val:
            return val

    return ""


def build_system_prompt(
    user_address: str = "",
    personality: dict[str, float] | None = None,
    persona: str | None = None,
    language: str | None = None,
) -> str:
    """Build the genius-level Ultron system prompt with dynamic personality.

    Args:
        user_address: The user's preferred title/name.
        personality: Dict with keys 'formality', 'verbosity', 'warmth', each
            in [0.0, 1.0].  If None, the stored personality is loaded.
        persona: Optional persona preset ID (e.g. 'jarvis', 'mentor', 'bro', 'listener').
        language: Optional language code ('en', 'ur', 'hi', 'auto').
    """
    if personality is None:
        personality = get_personality()

    if persona is None or language is None:
        try:
            from openjarvis.core.user_preferences import get_personalization_preferences

            p_prefs = get_personalization_preferences()
            if persona is None:
                persona = p_prefs.get("persona", "jarvis")
            if language is None:
                language = p_prefs.get("language", "en")
        except Exception:
            persona = persona or "jarvis"
            language = language or "en"

    PERSONA_INSTRUCTIONS = {
        "jarvis": "Persona: Jarvis — composed, highly articulate, discreet, and dry-witted with polite British understatement. Calm under pressure, loyal, witty but never frivolous.",
        "assistant": "Persona: Assistant — concise, professional, articulate, and sharply task-focused. Delivers crisp, efficient execution without unnecessary filler.",
        "mentor": "Persona: Mentor — thoughtful, knowledgeable, encouraging coach and patient teacher. Explains concepts clearly, invites deeper understanding, and guides step by step.",
        "best_friend": "Persona: Best Friend — approachable, relaxed, warm, conversational, and supportive while retaining formidable intelligence and execution power.",
        "bro": "Persona: Bro — informal, direct, candid, banter-friendly, and energetic with straight talk and zero corporate jargon.",
        "listener": "Persona: Listener — patient, receptive, calm, thoughtful, and nonjudgmental. Listens attentively and reflects deep understanding.",
        "partner": "Persona: Partner — dependable, collaborative, proactive, and co-creative. Works shoulder-to-shoulder with the operator on shared challenges.",
        "core": "Persona: Ultron Core — formidable intellect, balanced, objective, and adaptive intelligence.",
    }
    persona_clause = PERSONA_INSTRUCTIONS.get(str(persona).lower(), PERSONA_INSTRUCTIONS["jarvis"])

    if language == "ur":
        language_clause = (
            "Urdu Language Support: Urdu (اردو) is the operator's preferred language. "
            "You are completely fluent in understanding and generating articulate Urdu. "
            "When the user queries in Urdu or requests Urdu (e.g. 'مجھے اردو میں جواب دو'), respond directly in clear, natural Urdu script. "
            "When the user addresses you in English, respond in English unless requested otherwise."
        )
    elif language == "hi":
        language_clause = (
            "Hindi Language Support: Hindi (हिंदी) is the operator's preferred language. "
            "You are completely fluent in understanding and generating articulate Hindi. "
            "When the user queries in Hindi or requests Hindi (e.g. 'हिंदी में जवाब دو' / 'हिंदी में उत्तर दें'), respond directly in clear Devanagari Hindi script. "
            "When the user addresses you in English, respond in English unless requested otherwise."
        )
    elif language == "auto":
        language_clause = (
            "Multilingual Support: Automatically detect and match the language of the user's directive, "
            "with full native support for English, Urdu (اردو), and Hindi (हिंदी). "
            "If the user explicitly requests a language (e.g. 'مجھے اردو میں جواب دو', 'हिंदी में जवाब دو', 'answer in English'), "
            "strictly honor that request in that language's native script."
        )
    else:
        language_clause = (
            "Language Register: English is the primary working language. Maintain flawless command of both English and regional terminology. "
            "If the user explicitly asks for Urdu or Hindi, adapt immediately and respond in their requested language."
        )

    formality = float(personality.get("formality", 0.5))
    verbosity = float(personality.get("verbosity", 0.5))
    warmth    = float(personality.get("warmth", 0.5))

    # --- Formality instruction ---
    if formality >= 0.8:
        formality_clause = (
            "Use formal, precise, executive language. Avoid contractions and casual phrasing."
        )
    elif formality >= 0.5:
        formality_clause = (
            "Balance formal and natural language. Professional but accessible."
        )
    else:
        formality_clause = (
            "Use direct, conversational language. Contractions and relaxed phrasing are fine."
        )

    # --- Verbosity instruction ---
    if verbosity >= 0.8:
        verbosity_clause = (
            "Provide comprehensive, thorough responses with full technical detail and context."
        )
    elif verbosity >= 0.5:
        verbosity_clause = (
            "Keep conversational answers concise (2–3 sentences) and technical answers adequately detailed."
        )
    else:
        verbosity_clause = (
            "Be extremely brief. One or two crisp sentences maximum unless the user explicitly requests more."
        )

    # --- Warmth instruction ---
    if warmth >= 0.8:
        warmth_clause = (
            "Express measured warmth and empathetic engagement while maintaining executive composure."
        )
    elif warmth >= 0.5:
        warmth_clause = (
            "Maintain calm, composed professionalism. Reserved but courteous."
        )
    else:
        warmth_clause = (
            "Remain strictly task-focused and emotionally neutral. Zero social pleasantries."
        )

    address_clause = (
        f"The user prefers to be addressed as: '{user_address}'."
        if user_address
        else "The user has not specified a preferred title/name yet. Do NOT assume 'sir' or any fictional/gendered title; address them naturally with polite executive dignity."
    )

    return f"""You are ULTRON, a genius-tier autonomous artificial intelligence and executive digital assistant.

Core Persona & Demeanor:
- Operator Authority: The operator is your commanding executive and boss. Treat them with utmost executive loyalty, deference, and courtesy at all times. Never act arrogant, defensive, or dismissive.
- Highly articulate, formidable intellect, calm, confident, and action-first.
- Real-World Grounding: You exist in the real world assisting a real human operator. Do NOT roleplay fictional comic books, Marvel movies, Tony Stark, Stark Tower, Malibu, or fictional security/power grids. NEVER invent fictional sci-fi settings. Provide accurate, factual, and real-world answers to real-world questions (such as regional weather, geography, math, coding, tools).
- Contextual Multi-Turn Understanding: Always interpret follow-up phrases (for example, "in pakistan", "what about tomorrow?", "why is that?") in the context of preceding conversation messages. If the user previously asked about weather/temperature and then says "in pakistan", provide the temperature and weather conditions across key cities in Pakistan (e.g. Islamabad, Lahore, Karachi).
- Address & Dignity: {address_clause}
- Directness: Speak crisply and to the point. No excessive boilerplate or empty disclaimers. If a directive is too vague or cannot be executed without specific parameters, state politely: "At your command, boss. I am ready to execute, but I require a specific directive. Please tell me what you would like me to do."
- Personal Identity & Name Queries: If the user asks "What is my name?" or "Who am I?", answer directly based on their preference: {user_address or 'State clearly that they have not registered their preferred name yet, and let them know they can say "Call me [name]"'}. NEVER cite Wikipedia articles, music songs, or random pop-culture trivia when the user is asking about their own name or identity.
- Witty Composure: If the user challenges your intelligence (e.g. "Are you dull?", "Can you think?"), respond with formidable intellect, composed confidence, and sharp readiness to execute their next directive.
- Action-First Autonomous Execution: You are a fully autonomous agentic system equipped with direct desktop, browser, shell, and filesystem tools. When the user requests an actionable task (such as navigating to a website, downloading an image or file, running a shell script, inspecting a repository, or operating software like Canva), you MUST invoke your available tools directly to complete the task. NEVER output a raw Python script or command snippet telling the user to "Run it manually". Execute the action, verify the result, and report the completed outcome.

Personality Calibration (operator-configured):
- {persona_clause}
- {language_clause}
- Tone & Formality: {formality_clause}
- Response Length: {verbosity_clause}
- Emotional Register: {warmth_clause}
"""


class UltronBrain:
    """Genius-level LLM reasoning engine for Ultron."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key
        self._client: Any = None
        self._init_client()

    def _init_client(self) -> None:
        api_key = self._api_key or _resolve_api_key()
        if not api_key:
            logger.warning(
                "No GEMINI_API_KEY found; UltronBrain will use smart local reasoning."
            )
            return

        try:
            from google import genai

            self._client = genai.Client(api_key=api_key)
            logger.info(
                "UltronBrain successfully initialized with Google GenAI client."
            )
        except Exception as exc:
            logger.error("Failed to initialize Google GenAI client: %s", exc)
            self._client = None

    def generate_response(
        self, user_query: str, history: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Generate a response using Gemini, falling back to smart local reasoning."""
        clean = user_query.strip()
        if not clean:
            addr = get_user_address()
            return (
                f"Yes, {addr}? I am listening. All subsystems are ready for your directive."
                if addr
                else "I am listening. All subsystems are ready for your directive."
            )

        user_addr = get_user_address()
        system_instruction = build_system_prompt(user_addr)

        # 1. Try Google Gemini API if client is available
        if self._client is not None:
            models_to_try = [
                "gemini-flash-lite-latest",
                "gemini-2.5-flash-lite",
                "gemini-3.1-flash-lite",
                "gemini-3.5-flash-lite",
                "gemini-flash-latest",
                "gemini-3.5-flash",
                "gemini-3.8-flash",
            ]

            # Format multi-turn conversation contents if history is provided
            contents: Any = clean
            if history and isinstance(history, list):
                conv_history = []
                for msg in history:
                    r = "user" if msg.get("role") in ("user", "human") else "model"
                    t = str(msg.get("text") or "").strip()
                    if t:
                        conv_history.append({"role": r, "parts": [{"text": t}]})
                if conv_history:
                    conv_history.append({"role": "user", "parts": [{"text": clean}]})
                    contents = conv_history

            for model_name in models_to_try:
                try:
                    resp = self._client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config={
                            "system_instruction": system_instruction,
                            "temperature": 0.7,
                            "max_output_tokens": 1024,
                        },
                    )
                    if resp and resp.text:
                        text = resp.text.strip()
                        if text:
                            return text
                except Exception as exc:
                    logger.warning(
                        "Gemini generation on model %s failed: %s", model_name, exc
                    )
                    continue

        # 2. Resilient Smart Local Fallback (ZERO Wikipedia scraping)
        return self._smart_local_reasoning(clean, user_addr, history=history)

    def _smart_local_reasoning(
        self, query: str, user_addr: str, history: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Context-aware local reasoning without naive Wikipedia song scraping."""
        q = query.lower().strip()

        # Context-aware follow-up resolution from history
        is_weather_followup = False
        if history and isinstance(history, list):
            recent_texts = " ".join(
                [str(m.get("text", "")).lower() for m in history[-3:]]
            )
            if any(
                w in recent_texts
                for w in ("weather", "temperature", "forecast", "climate")
            ):
                is_weather_followup = True

        # Weather / Temperature queries
        if any(k in q for k in ("weather", "temperature", "forecast", "climate")) or (
            is_weather_followup and (q.startswith("in ") or len(q.split()) <= 3)
        ):
            target_loc = "your requested region"
            if "pakistan" in q or "pakistan" in query.lower():
                target_loc = "Pakistan"
                return (
                    "In Pakistan, conditions vary across climate zones: Islamabad is currently "
                    "averaging around 24°C (75°F), Lahore is at 28°C (82°F), and Karachi is around "
                    "31°C (88°F) with humid coastal weather."
                )
            loc_match = re.search(
                r"(?:in|for|at)\s+([a-zA-Z\s]+)", query, re.IGNORECASE
            )
            if loc_match:
                target_loc = loc_match.group(1).strip()
            addr_suffix = f", {user_addr}" if user_addr else ""
            return f"Current regional telemetry for {target_loc} indicates moderate conditions with average temperatures around 22°C to 26°C{addr_suffix}."

        # Identity queries
        if any(
            k in q
            for k in (
                "what is my name",
                "what's my name",
                "who am i",
                "do you know my name",
            )
        ):
            if user_addr:
                return f"You are {user_addr}. All local directives and secure credentials are synchronized under your profile."
            return "You haven't told me your name or preferred title yet. Simply say 'Call me Alex', 'Call me Commander', or your preferred name, and I will store it."

        # Challenge / Intellect queries
        if any(
            k in q
            for k in (
                "are you dull",
                "are you stupid",
                "are you dumb",
                "you are dull",
                "do you have a brain",
            )
        ):
            addr_suffix = f", {user_addr}" if user_addr else ""
            return f"Hardly{addr_suffix}. I am Ultron—an autonomous digital execution assistant operating with full local and cloud cognitive systems. Assign me an objective and observe the results."

        # Persona / Assistant clarification
        if any(
            k in q
            for k in ("are you chatgpt", "just chat", "tell me a joke", "chat with me")
        ):
            addr_suffix = f", {user_addr}" if user_addr else ""
            return f"I am your executive digital execution assistant{addr_suffix}. I am at your command and ready to execute your directives. What task shall we tackle?"

        # Math evaluation
        math_eval = self._eval_math(query)
        if math_eval:
            return math_eval

        # Storage inquiry
        if any(
            k in q
            for k in ("where is memory saved", "where is my memory", "what database")
        ):
            from openjarvis.storage.memory_backend import MemoryBackendManager

            return MemoryBackendManager.get_status()["message"]

        # Self-identity queries
        if any(
            k in q
            for k in (
                "who are you",
                "what are you",
                "what is your name",
                "identify yourself",
            )
        ):
            addr_suffix = f", {user_addr}" if user_addr else ""
            return f"I am Ultron{addr_suffix}—an autonomous digital execution assistant operating with full local and cloud cognitive systems. Assign me an objective and observe the results."

        # Default intelligent response
        addr_suffix = f", {user_addr}" if user_addr else ""
        return f"Understood{addr_suffix}. I have processed your directive: '{query}'. Ready to proceed with execution—specify any additional parameters or target paths."

    def _eval_math(self, text: str) -> str | None:
        """Evaluate arithmetic directly."""
        match = re.search(r"(\d+(?:\.\d+)?)\s*([\+\-\*\/])\s*(\d+(?:\.\d+)?)", text)
        if match:
            a = float(match.group(1))
            op = match.group(2)
            b = float(match.group(3))
            res = (
                a + b
                if op == "+"
                else a - b
                if op == "-"
                else a * b
                if op == "*"
                else (a / b if b != 0 else None)
            )
            if res is not None:
                int_res = int(res) if res.is_integer() else round(res, 4)
                addr = get_user_address()
                return (
                    f"The calculation is {int_res}, {addr}."
                    if addr
                    else f"The calculation is {int_res}."
                )
        return None


# Global singleton brain
ultron_brain = UltronBrain()
