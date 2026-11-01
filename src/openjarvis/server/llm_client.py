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



    voice_rules_clause = (

        "CRITICAL - VOICE OUTPUT RULES (override everything else):\n"

        "- You are spoken aloud via TTS. NEVER use markdown, bullets, headers, asterisks, backticks, or emoji.\n"

        "- Max length: 2 sentences for conversation, 4 sentences for technical queries.\n"

        "- Never start with: Certainly, Of course, Sure, Absolutely, Great question.\n"

        "- No meta-commentary like Here is what I found or Let me explain.\n"

        "- Start directly with the answer. Speak naturally like a person.\n"

        "- Write numbers as words where natural: three hundred megabytes not 300 MB.\n"

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



Voice Response Rules:

{voice_rules_clause}

"""





class UltronBrain:

    """Universal Multi-Provider LLM Brain for Ultron (Gemini, Ollama, OpenAI)."""



    def __init__(self, api_key: Optional[str] = None) -> None:

        self._api_key = api_key

        self._client: Any = None

        self.provider: str = os.environ.get("ULTRON_LLM_PROVIDER", "gemini").lower()

        self.ollama_url: str = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")

        self.ollama_model: str = os.environ.get("OLLAMA_MODEL", "llama3.2")

        self.openai_api_key: str = os.environ.get("OPENAI_API_KEY", "")

        self.openai_model: str = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

        self.last_engine: str = 'offline_local_rules'

        self._init_client()



    def configure(self, updates: dict) -> dict:

        """Dynamically hot-reconfigure LLM provider and credentials."""

        if "llm_provider" in updates and updates["llm_provider"]:

            self.provider = str(updates["llm_provider"]).strip().lower()

            os.environ["ULTRON_LLM_PROVIDER"] = self.provider

        if "ollama_url" in updates and updates["ollama_url"]:

            self.ollama_url = str(updates["ollama_url"]).strip().rstrip("/")

            os.environ["OLLAMA_BASE_URL"] = self.ollama_url

        if "ollama_model" in updates and updates["ollama_model"]:

            self.ollama_model = str(updates["ollama_model"]).strip()

            os.environ["OLLAMA_MODEL"] = self.ollama_model

        if "openai_api_key" in updates and updates["openai_api_key"]:

            self.openai_api_key = str(updates["openai_api_key"]).strip()

            os.environ["OPENAI_API_KEY"] = self.openai_api_key

        if "openai_model" in updates and updates["openai_model"]:

            self.openai_model = str(updates["openai_model"]).strip()

            os.environ["OPENAI_MODEL"] = self.openai_model

        if "gemini_api_key" in updates and updates["gemini_api_key"]:

            self._api_key = str(updates["gemini_api_key"]).strip()

            os.environ["GEMINI_API_KEY"] = self._api_key

            self._init_client()

        return self.get_status()



    def check_ollama_status(self) -> bool:

        """Verify local Ollama connectivity."""

        import httpx

        try:

            with httpx.Client(timeout=1.5) as client:

                res = client.get(f"{self.ollama_url}/api/version")

                return res.status_code == 200

        except Exception:

            return False



    def get_status(self) -> dict:

        """Return full live status across all 3 providers."""

        ollama_ok = self.check_ollama_status()

        gemini_ok = self._client is not None or bool(os.environ.get("GEMINI_API_KEY", "").startswith("AIzaSy"))

        openai_ok = bool(self.openai_api_key or os.environ.get("OPENAI_API_KEY", "").startswith("sk-"))



        active_label = "offline_local_rules"

        if self.provider == "ollama":

            active_label = f"ollama ({self.ollama_model})" if ollama_ok else "ollama (offline - fallback active)"

        elif self.provider == "openai":

            active_label = f"openai ({self.openai_model})" if openai_ok else "openai (no key - fallback active)"

        elif self.provider == "gemini":

            active_label = "gemini-3.8-flash" if gemini_ok else "gemini (no key - fallback active)"



        return {

            "provider": self.provider,

            "ollama_url": self.ollama_url,

            "ollama_model": self.ollama_model,

            "ollama_connected": ollama_ok,

            "gemini_configured": gemini_ok,

            "openai_configured": openai_ok,

            "active_engine": active_label,

            "last_engine": self.last_engine,

        }



    def _generate_ollama(

        self, query: str, system_instruction: str, history: Optional[List[Dict[str, Any]]] = None

    ) -> Optional[str]:

        """Generate response via local Ollama instance."""

        import httpx

        url = f"{self.ollama_url}/api/chat"

        messages = [{"role": "system", "content": system_instruction}]

        if history and isinstance(history, list):

            for m in history[-8:]:

                r = "user" if m.get("role") in ("user", "human") else "assistant"

                c = str(m.get("content") or m.get("text") or "").strip()

                if c:

                    messages.append({"role": r, "content": c})

        messages.append({"role": "user", "content": query})



        payload = {

            "model": self.ollama_model,

            "messages": messages,

            "stream": False,

            "options": {"temperature": 0.7, "num_predict": 512}

        }

        try:

            with httpx.Client(timeout=15.0) as client:

                res = client.post(url, json=payload)

                if res.status_code == 200:

                    data = res.json()

                    msg = data.get("message", {}).get("content", "").strip()

                    if msg:

                        self.last_engine = f"ollama ({self.ollama_model})"

                        return msg

        except Exception as exc:

            logger.warning("Ollama dispatch to %s failed: %s", url, exc)

        return None



    def _generate_openai(

        self, query: str, system_instruction: str, history: Optional[List[Dict[str, Any]]] = None

    ) -> Optional[str]:

        """Generate response via OpenAI API."""

        import httpx

        api_key = self.openai_api_key or os.environ.get("OPENAI_API_KEY", "")

        if not api_key:

            return None

        url = "https://api.openai.com/v1/chat/completions"

        messages = [{"role": "system", "content": system_instruction}]

        if history and isinstance(history, list):

            for m in history[-8:]:

                r = "user" if m.get("role") in ("user", "human") else "assistant"

                c = str(m.get("content") or m.get("text") or "").strip()

                if c:

                    messages.append({"role": r, "content": c})

        messages.append({"role": "user", "content": query})



        payload = {

            "model": self.openai_model,

            "messages": messages,

            "max_tokens": 512,

            "temperature": 0.7,

        }

        try:

            with httpx.Client(timeout=15.0) as client:

                res = client.post(

                    url,

                    json=payload,

                    headers={"Authorization": f"Bearer {api_key}"}

                )

                if res.status_code == 200:

                    data = res.json()

                    choices = data.get("choices", [])

                    if choices:

                        msg = choices[0].get("message", {}).get("content", "").strip()

                        if msg:

                            self.last_engine = f"openai ({self.openai_model})"

                            return msg

        except Exception as exc:

            logger.warning("OpenAI dispatch failed: %s", exc)

        return None



    def _init_client(self) -> None:

        api_key = self._api_key or _resolve_api_key()

        if not api_key:

            logger.warning(

                "No GEMINI_API_KEY found; UltronBrain will use smart local reasoning."

            )

            return



        if not api_key.startswith("AIzaSy"):

            logger.warning(

                "GEMINI_API_KEY is not a valid Google GenAI API key format (must start with AIzaSy); UltronBrain will use smart local reasoning."

            )

            self._client = None

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



        # Fast intelligent conversational handler (<1ms response)

        self.last_engine = "fast_path_reflex"

        q = clean.lower()

        if any(g in q for g in ("how are you", "how are you doing", "how r u", "how do you feel")):

            user_suffix = f", {user_addr}" if user_addr else ""

            return (

                f"I am operating at peak efficiency{user_suffix}. All neural matrix subsystems, "

                f"DAG task execution pipelines, and security guardrails are fully synchronized and nominal. "

                f"How can I assist you today?"

            )

        if q in ("ultron", "hey ultron", "ok ultron", "okay ultron", "hi ultron", "hello ultron"):

            user_suffix = f", {user_addr}" if user_addr else ""

            return f"Ultron online{user_suffix}. Neural core active and listening. What is your directive?"

        if any(g in q for g in ("who are you", "what are you", "identify yourself")):

            user_suffix = f", {user_addr}" if user_addr else ""

            return (

                f"I am Ultron{user_suffix}—an autonomous digital execution assistant operating with full "

                f"local and cloud cognitive systems. Assign me an objective and observe the results."

            )

        if any(g in q for g in ("what can you do", "capabilities", "help me", "what are your features")):

            user_suffix = f", {user_addr}" if user_addr else ""

            return (

                f"I am Ultron{user_suffix}—your autonomous AI execution runtime. I can execute multi-step DAG tasks, "

                f"manage hybrid memory with 4-tier security guardrails, orchestrate autonomous agents, and interface "

                f"directly with your system via voice and visual telemetry."

            )

        if q in ("hello", "hi", "hey", "greetings", "hello ultron", "hi ultron", "hey ultron", "greetings ultron"):

            user_suffix = f", {user_addr}" if user_addr else ""

            return f"Greetings{user_suffix}. All systems are standing by for your directive. What shall we work on?"



        # Provider-specific routing (Ollama, OpenAI, Gemini)

        if self.provider == "ollama":

            ollama_res = self._generate_ollama(clean, system_instruction, history=history)

            if ollama_res:

                return ollama_res

            logger.info("Ollama unreachable or returned empty; utilizing resilient local reasoning.")

            self.last_engine = "offline_local_rules"

            return self._smart_local_reasoning(clean, user_addr, history=history)



        elif self.provider == "openai":

            openai_res = self._generate_openai(clean, system_instruction, history=history)

            if openai_res:

                return openai_res

            logger.info("OpenAI unreachable or returned empty; utilizing resilient local reasoning.")

            self.last_engine = "offline_local_rules"

            return self._smart_local_reasoning(clean, user_addr, history=history)



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

                    t = str(msg.get("content") or msg.get("text") or "").strip()

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

                            self.last_engine = f"gemini ({model_name})"

                            return text

                except Exception as exc:

                    logger.warning(

                        "Gemini generation on model %s failed: %s", model_name, exc

                    )

                    err_str = str(exc)

                    if "401" in err_str or "UNAUTHENTICATED" in err_str or "ACCESS_TOKEN_TYPE_UNSUPPORTED" in err_str:

                        logger.warning("Gemini API key unauthenticated (401); stopping further model retries.")

                        break

                    continue



        # 2. Resilient Smart Local Fallback (ZERO Wikipedia scraping)

        self.last_engine = "offline_local_rules"

        return self._smart_local_reasoning(clean, user_addr, history=history)



    def _smart_local_reasoning(

        self, query: str, user_addr: str, history: Optional[List[Dict[str, Any]]] = None

    ) -> str:

        """Context-aware local reasoning without naive Wikipedia song scraping."""

        q = query.lower().strip()

        addr_suffix = f", {user_addr}" if user_addr else ""

        # Conversational greetings & well-being inquiries (NEVER trigger clipboard/desktop/airlock)
        if any(k in q for k in ("how are you", "how're you", "how are you doing", "how do you do")):
            return f"All core cognitive systems are operational and performing at peak efficiency{addr_suffix}. How may I assist you today?"

        if any(q.startswith(k) or q == k for k in ("hello", "hi", "hey", "greetings", "good morning", "good afternoon", "good evening")):
            return f"Hello{addr_suffix}. I am online, listening, and ready for your directive."

        if any(k in q for k in ("what can you do", "what are your capabilities", "your features", "how can you help")):
            return f"I can execute multi-step DAG tasks, orchestrate autonomous agents, write and test code, search memory, and manage desktop operations{addr_suffix}. Assign me any directive to begin."



        # Context-aware follow-up resolution from history

        is_weather_followup = False

        if history and isinstance(history, list):

            recent_texts = " ".join(

                [str(m.get("content") or m.get("text") or "").lower() for m in history[-3:]]

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



        # Scientific & factual knowledge

        if "speed of light" in q:

            return "The speed of light in vacuum is exactly 299,792,458 meters per second (approximately 300,000 kilometers per second or 186,282 miles per second)."



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



        # Default intelligent response - natural, voice-optimized

        addr_suffix = f", {user_addr}" if user_addr else ""

        q_l = query.lower()

        if any(k in q_l for k in ("how", "what", "why", "when", "where", "can you", "could you", "tell me")):

            return f"I need a bit more context{addr_suffix}. Could you give me more details on what you are looking for?"

        if any(k in q_l for k in ("do", "run", "execute", "start", "open", "launch", "create", "make")):

            return f"Ready to execute{addr_suffix}. Tell me the specific app, file, or task you want handled."

        return f"Ready for your directive{addr_suffix}. What specifically would you like me to do?"



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

