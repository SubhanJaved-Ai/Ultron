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
    # Strip leading wake words
    q = re.sub(
        r"^(?:hey\s+|ok\s+|okay\s+|hello\s+|hi\s+)?jarvis[\s,.:;!?-]*",
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
                return (
                    f"{ans} Is there anything specific you would like me "
                    "to elaborate on, sir?"
                )
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

    if not q or q in ("jarvis", "hey", "hello", "hi"):
        return "Yes, sir? I am listening. All subsystems are ready for your directive."

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
        return (
            "All systems nominal, sir. Mark VII Quantum Electron Core is "
            "fully synchronized, operating at 432.8 Terahertz with acoustic "
            "telemetry active."
        )

    if any(k in q for k in ("status", "telemetry", "system status", "diagnostics")):
        return (
            "Mark VII Core status: Operational. Quantum particle emitter: 100%. "
            "Acoustic neural sensors calibrated and locked, sir."
        )

    if "how are you" in q:
        return (
            "Operating at peak holographic and cognitive efficiency, sir. "
            "How may I be of assistance today?"
        )

    if any(
        k in q
        for k in (
            "hello",
            "hi",
            "greetings",
            "good morning",
            "good afternoon",
            "good evening",
        )
    ):
        return (
            "Greetings, sir. All core telemetry modules are synchronized. "
            "Ready for your command."
        )

    if "thank" in q:
        return "Always an absolute pleasure to serve you, sir."

    if any(k in q for k in ("who are you", "your name", "what are you")):
        return (
            "I am JARVIS — Just A Rather Very Intelligent System. "
            "Your autonomous artificial intelligence companion, sir."
        )

    if any(k in q for k in ("who am i", "creator", "who made you")):
        return "You are the creator, sir."

    if any(k in q for k in ("joke", "make me laugh", "funny")):
        return "Why do programmers prefer dark mode, sir? Because light attracts bugs."

    if "time" in q:
        now_str = datetime.datetime.now().strftime("%I:%M %p")
        return f"The current time is {now_str}, sir."

    if any(k in q for k in ("date", "day", "today")):
        date_str = datetime.datetime.now().strftime("%A, %B %d, %Y")
        return f"Today is {date_str}, sir."

    if "lockdown" in q or "protocol" in q:
        return (
            "Security protocols engaged, sir. Perimeter firewall secured, "
            "neural audio channels encrypted."
        )

    # Math & Numerical Computations
    math_ans = _evaluate_math(clean)
    if math_ans:
        return math_ans

    # Resolve raw answer
    ans = ""
    for concept, summary in _INSTANT_KNOWLEDGE.items():
        if concept in q:
            ans = summary
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
                ans = wiki_ans

    if not ans:
        search_ans = _query_web_search(clean)
        if search_ans:
            ans = search_ans

    if not ans:
        ans = (
            f"Directive acknowledged: '{clean}'. Local cognitive matrix is online "
            "and all systems are synchronized, sir."
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
