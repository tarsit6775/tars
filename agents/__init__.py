"""
╔══════════════════════════════════════════╗
║       TARS — Multi-Agent System          ║
╚══════════════════════════════════════════╝

Specialist agents, each with their own LLM loop,
tools, and autonomy. Orchestrated by the Brain.

Agents:
  - BrowserAgent   — Web browsing, forms, web apps
  - CoderAgent     — Code, terminal, files, git, deploy
  - SystemAgent    — Mac control, apps, automation
  - ResearchAgent  — Deep multi-source research
  - FileAgent      — File management, compression, search

Escalation chain:
  Agent stuck → Brain retries/reroutes → iMessage user
"""

from agents.browser_agent import BrowserAgent
from agents.coder_agent import CoderAgent
from agents.system_agent import SystemAgent
from agents.research_agent import ResearchAgent
from agents.file_agent import FileAgent
from agents.comms import AgentComms, agent_comms

AGENT_REGISTRY = {
    "browser": BrowserAgent,
    "coder": CoderAgent,
    "system": SystemAgent,
    "research": ResearchAgent,
    "file": FileAgent,
}

__all__ = [
    "BrowserAgent",
    "CoderAgent",
    "SystemAgent",
    "ResearchAgent",
    "FileAgent",
    "AgentComms",
    "agent_comms",
    "AGENT_REGISTRY",
]
