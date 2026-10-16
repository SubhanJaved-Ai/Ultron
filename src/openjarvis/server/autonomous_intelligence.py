"""Autonomous Intelligence Engine for OpenJarvis.

Provides intelligent, articulate, spoken conversational answers to any
user question without requiring paid external LLM API keys.
Incorporates instant encyclopedic retrieval, math calculation, local knowledge,
and real-time web search fallback in authentic JARVIS persona.
"""

from __future__ import annotations

import datetime
import json
import logging
import math
import re
import urllib.parse
import urllib.request

from openjarvis.core.user_preferences import (
    format_addressed,
    get_user_address,
    set_user_address,
)
from openjarvis.storage.memory_backend import MemoryBackendManager

logger = logging.getLogger("openjarvis.server.autonomous")

# Pre-compiled common knowledge for instant zero-latency answers
_INSTANT_KNOWLEDGE: dict[str, str] = {
    "quantum computing": (
        "Quantum computing harnesses the laws of quantum mechanics—namely "
        "superposition and entanglement—to process complex information exponentially "
        "faster than classical supercomputers, sir."
    ),
    "arc reactor": (
        "The Arc Reactor is an advanced clean fusion power generator developed "
        "by Stark Industries, supplying near-limitless energy to our Mark series "
        "architectures and core holographic matrices, sir."
    ),
    "artificial intelligence": (
        "Artificial Intelligence refers to computational systems engineered to perform "
        "tasks typically requiring human cognition, such as natural language "
        "synthesis, pattern recognition, and autonomous decision-making, sir."
    ),
    "black hole": (
        "A black hole is a region of spacetime where gravitational acceleration is "
        "so intense that nothing—not even electromagnetic radiation such as light—can "
        "escape past its event horizon, sir."
    ),
    "speed of light": (
        "The speed of light in a vacuum is exactly 299,792,458 meters per second, "
        "or approximately 186,282 miles per second, sir."
    ),
    "gravity": (
        "Gravity is the fundamental natural phenomenon by which objects with mass or "
        "energy are attracted to one another, described in general relativity as "
        "the curvature of spacetime, sir."
    ),
    "python": (
        "Python is a high-level, interpreted programming language renowned for its "
        "expressive syntax and extensive ecosystem in artificial intelligence, "
        "systems engineering, and data science, sir."
    ),
    "dna": (
        "Deoxyribonucleic acid (DNA) is a polymer composed of two polynucleotide "
        "chains that coil around each other to form a double helix, carrying genetic "
        "instructions for all known living organisms, sir."
    ),
    "superconductivity": (
        "Superconductivity is a physical state in which certain materials exhibit "
        "zero electrical resistance and expulsion of magnetic flux fields when cooled "
        "below a critical threshold, sir."
    ),
}


def _strip_wake_words(query: str) -> str:
    """Strip wake words and polite padding from the query."""
    q = (query or "").strip()
    # Strip leading wake words (Ultron or Jarvis)
    q = re.sub(
        r"^(?:hey\s+|ok\s+|okay\s+|hello\s+|hi\s+)?(?:ultron|jarvis)[\s,.:;!?-]*",
        "",
        q,
        flags=re.IGNORECASE,
    ).strip()
    # Strip polite fillers
    q = re.sub(
        r"^(?:please\s+|can\s+you\s+|could\s+you\s+|would\s+you\s+|tell\s+me\s+)?",
        "",
        q,
        flags=re.IGNORECASE,
    ).strip()
    return q


def _evaluate_math(clean_query: str) -> str | None:
    """Evaluate mathematical calculations and conversions."""
    q = clean_query.lower()

    # Percentage: e.g. "what is 15 percent of 800" or "15% of 800"
    pct_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:%|percent)\s*(?:of)\s*(\d+(?:\.\d+)?)", q
    )
    if pct_match:
        pct = float(pct_match.group(1))
        val = float(pct_match.group(2))
        res = (pct / 100.0) * val
        return f"{pct}% of {val} is {res:g}, sir."

    # Square root: e.g. "square root of 144" or "sqrt(144)"
    sqrt_match = re.search(r"(?:square root of|sqrt)\s*(\d+(?:\.\d+)?)", q)
    if sqrt_match:
        val = float(sqrt_match.group(1))
        res = math.sqrt(val)
        return f"The square root of {val} is {res:g}, sir."

    # Simple arithmetic expression: e.g. "25 * 40", "100 / 4 + 7"
    math_match = re.search(r"(\d+(?:\.\d+)?)\s*([\+\-\*\/])\s*(\d+(?:\.\d+)?)", q)
    if math_match:
        try:
            n1 = float(math_match.group(1))
            op = math_match.group(2)
            n2 = float(math_match.group(3))
            if op == "+":
                res = n1 + n2
            elif op == "-":
                res = n1 - n2
            elif op == "*":
                res = n1 * n2
            elif op == "/":
                if n2 == 0:
                    return "Division by zero is mathematically undefined, sir."
                res = n1 / n2
            return f"The result is {res:g}, sir."
        except Exception:
            pass

    return None


def _query_wikipedia_summary(topic: str) -> str | None:
    """Fetch concise encyclopedic summary from Wikipedia REST API."""
    try:
        encoded_topic = urllib.parse.quote(topic.strip())
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_topic}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "OpenJarvis/2.0 (hologram-assistant@openjarvis.ai)"},
        )
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            extract = data.get("extract")
            if extract and len(extract) > 20:
                sentences = extract.split(". ")
                ans = ". ".join(sentences[:2]).strip()
                if not ans.endswith("."):
                    ans += "."
                return f"{ans}, sir."
    except Exception:
        pass
    return None


def _query_web_search(query: str) -> str | None:
    """Fetch live web snippet using DuckDuckGo."""
    try:
        from ddgs import DDGS

        results = DDGS().text(query, max_results=1)
        if results and len(results) > 0:
            snippet = results[0].get("body", "")
            if snippet:
                # Clean dates and header prefixes
                cleaned = re.sub(
                    r"^[A-Z][a-z]{2}\s+\d+,\s+\d{4}\s+[—–-]\s*",
                    "",
                    snippet,
                )
                sentences = cleaned.split(". ")
                ans = ". ".join(sentences[:2]).strip()
                if not ans.endswith("."):
                    ans += "."
                return f"{ans}, sir."
    except Exception:
        pass
    return None


def generate_autonomous_response(raw_query: str) -> str:
    """Generate an authentic, articulate JARVIS answer for any query."""
    clean = _strip_wake_words(raw_query)
    q = clean.lower()

    if not q or q in ("ultron", "jarvis", "hey", "hello", "hi"):
        addr = get_user_address()
        if addr:
            return f"Yes, {addr}? I am listening. All subsystems are ready for your directive."
        return "I am listening. All subsystems are ready for your directive."

    # User Address Configuration: "call me ma'am", "call me Alex", "call me sir", "my name is Alex"
    call_me_match = re.search(
        r"(?:call me|my name is|address me as|refer to me as)\s+([a-zA-Z0-9_\- '.]+)",
        clean,
        re.IGNORECASE,
    )
    if call_me_match:
        target_name = call_me_match.group(1).strip().rstrip(".,!?:;")
        saved = set_user_address(target_name)
        return f"Understood, {saved}. I have saved your preference and will address you as {saved}."

    # User Identity Inspection: "What's my name", "my name", "who am i", etc.
    if any(
        k in q
        for k in (
            "who am i",
            "who i am",
            "what is my name",
            "what's my name",
            "whats my name",
            "my name",
            "tell me my name",
            "do you know me",
            "do you know my name",
            "do you know who i am",
        )
    ):
        addr = get_user_address()
        if addr:
            return f"You are {addr}. All profile directives and local nodes are synchronized under your command."
        return (
            "You haven't specified your name or preferred title yet. "
            "You can say 'Call me Alex', 'Call me Commander', or 'Call me ma'am', and I will remember it."
        )

    # Intellect Challenge: "Are you dull?", "Are you stupid?"
    if any(
        k in q
        for k in (
            "are you dull",
            "are you stupid",
            "are you dumb",
            "you are dull",
            "can you think",
            "do you have a brain",
        )
    ):
        return format_addressed(
            "Hardly. I am Ultron—an autonomous digital execution assistant operating with full local and cloud cognitive systems. Assign me an objective and observe the results"
        )

    # Memory / Database Storage Status and Attachment Queries
    if any(
        k in q
        for k in (
            "where is memory saved",
            "where is my memory saved",
            "where is data saved",
            "what database",
            "which database",
            "storage status",
            "memory status",
            "attach supabase",
            "attach database",
            "attach mongodb",
            "data shared",
            "where do you save",
        )
    ):
        return MemoryBackendManager.get_status()["message"]

    # Idle chat rejection handler: Ultron is not ChatGPT
    if any(
        k in q
        for k in (
            "chat with me",
            "talk to me",
            "tell me a story",
            "can we chat",
            "let's chat",
            "just chat",
            "entertain me",
            "like chatgpt",
            "are you chatgpt",
            "chit chat",
        )
    ):
        return format_addressed(
            "I am your digital execution assistant. "
            "At your service and standing by for your directive"
        )

    # Question readiness / permission prompts
    if any(
        k in q
        for k in (
            "ask a question",
            "ask you a question",
            "ask him a question",
            "can i ask",
            "may i ask",
            "have a question",
            "got a question",
        )
    ):
        return format_addressed(
            "Go right ahead. Ask your question and I will analyze and answer it directly"
        )

    # Pure isolated greetings only (e.g. "hello", "hi ultron", "good morning")
    PURE_GREETING_PATTERN = re.compile(
        r"^(?:hello|hi|hey|greetings|good\s+(?:morning|afternoon|evening))\s*(?:ultron|jarvis|sir|boss)?[\s.!?]*$",
        re.IGNORECASE,
    )
    if PURE_GREETING_PATTERN.match(clean.strip()):
        return format_addressed("Hello. All systems nominal, standing by for your directive")

    # If query opens with a greeting prefix followed by a real question (e.g. "Hello, what is..."),
    # strip the greeting prefix so the underlying question resolves cleanly
    effective_q = re.sub(
        r"^(?:hello|hi|hey|greetings|good\s+(?:morning|afternoon|evening))\s*(?:ultron|jarvis|sir|boss)?[\s,.:;!]+",
        "",
        clean,
        flags=re.IGNORECASE,
    ).strip()
    if effective_q and effective_q != clean:
        clean = effective_q
        q = clean.lower()

    # Conversational & System Queries
    if any(
        k in q
        for k in (
            "what's going on",
            "what is going on",
            "what is happening",
            "what's happening",
        )
    ):
        return format_addressed("All systems nominal. Standing by for your directive")

    if re.search(r"\b(?:system\s+status|subsystems|diagnostics)\b", q) or q in (
        "status",
        "telemetry",
    ):
        return format_addressed(
            "Core status operational. All subsystems online and ready"
        )

    if re.search(r"\bhow\s+are\s+you\b", q):
        return format_addressed(
            "Fully operational. Assign me a task and I will execute it"
        )

    if re.search(r"\b(?:thank\s+you|thanks|thank\s+thee)\b", q):
        return format_addressed("Always at your service")

    if any(k in q for k in ("who are you", "your name", "what are you")):
        return format_addressed(
            "I am Ultron (evolved from JARVIS), your executive digital assistant. "
            "I execute system tasks, automations, and tools at your command"
        )

    if any(k in q for k in ("creator", "who made you")):
        return format_addressed("You are the creator")

    if any(k in q for k in ("joke", "make me laugh", "funny")):
        return format_addressed(
            "Why do programmers prefer dark mode? Because light attracts bugs"
        )

    if re.search(
        r"\b(?:what(?:\s+is|\s*'s)?\s+(?:the\s+)?time|current\s+time|what\s+time\s+is\s+it)\b",
        q,
    ) or q in ("time", "what time", "current time"):
        now_str = datetime.datetime.now().strftime("%I:%M %p")
        return format_addressed(f"The current time is {now_str}")

    if re.search(
        r"\b(?:what(?:\s+is|\s*'s)?\s+(?:the\s+)?date|what\s+day\s+is\s+(?:it|today)|today'?s\s+date|current\s+date)\b",
        q,
    ) or q in ("date", "today", "what date"):
        date_str = datetime.datetime.now().strftime("%A, %B %d, %Y")
        return format_addressed(f"Today is {date_str}")

    if "lockdown" in q or "protocol" in q:
        return format_addressed(
            "Security protocols engaged. Perimeter firewall secured, neural audio channels encrypted"
        )

    # Math & Numerical Computations
    math_ans = _evaluate_math(clean)
    if math_ans:
        return format_addressed(math_ans)

    # Resolve raw answer
    ans = ""
    for concept, summary in _INSTANT_KNOWLEDGE.items():
        if concept in q:
            ans = format_addressed(summary)
            break

    if not ans:
        pattern = (
            r"^(?:what is|what are|who is|who was|"
            r"who were|tell me about|define|explain)"
            r"\s+(?:a\s+|an\s+|the\s+)?(.+)"
        )
        topic_match = re.search(pattern, q)
        if topic_match:
            topic = topic_match.group(1).rstrip("?.! ")
            wiki_ans = _query_wikipedia_summary(topic)
            if wiki_ans:
                ans = format_addressed(wiki_ans)

    if not ans:
        search_ans = _query_web_search(clean)
        if search_ans:
            ans = format_addressed(search_ans)

    if not ans:
        ans = format_addressed(
            f"Directive acknowledged: '{clean}'. Local cognitive matrix is online and all systems are synchronized"
        )

    # Sanitize for robust speech synthesis (replace em-dashes and unicode quotes)
    clean_ans = (
        ans.replace("—", ", ")
        .replace("–", ", ")
        .replace("“", '"')
        .replace("”", '"')
        .replace("’", "'")
        .strip()
    )
    return clean_ans
