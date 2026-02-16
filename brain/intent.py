"""
╔══════════════════════════════════════════════════════════════╗
║      TARS Brain v4 — Phase 2: Intent Classifier             ║
╠══════════════════════════════════════════════════════════════╣
║  Fast rule-based intent classification — ZERO LLM tokens.    ║
║                                                              ║
║  Runs BEFORE the Brain LLM call to:                          ║
║    1. Skip LLM calls for simple acknowledgments              ║
║    2. Pre-load the right context for the message type         ║
║    3. Set the right mode for the Brain's response             ║
║    4. Inject only relevant domain knowledge                   ║
║                                                              ║
║  Categories:                                                 ║
║    CONVERSATION  — casual chat, opinions, feelings           ║
║    QUICK_QUESTION — factual, answerable with a command       ║
║    TASK          — requires agent deployment / real work      ║
║    FOLLOW_UP     — references previous context               ║
║    CORRECTION    — modifying a previous request              ║
║    EMERGENCY     — urgent, act immediately                   ║
║    ACKNOWLEDGMENT — "ok", "sure", "go ahead"                 ║
║                                                              ║
║  Also detects DOMAIN HINTS for contextual prompt injection:  ║
║    flights, email, dev, browser, research, files, system     ║
╚══════════════════════════════════════════════════════════════╝
"""

import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class Intent:
    """Classified intent of a user message."""
    type: str           # CONVERSATION, QUICK_QUESTION, TASK, FOLLOW_UP, CORRECTION, EMERGENCY, ACKNOWLEDGMENT
    confidence: float   # 0.0 - 1.0
    detail: str = ""    # Sub-type or explanation
    needs_context: bool = False   # Whether to load thread context
    needs_memory: bool = False    # Whether to auto-recall memory
    domain_hints: List[str] = field(default_factory=list)  # Which domain knowledge to inject

    @property
    def is_actionable(self) -> bool:
        """Whether this intent requires the Brain to DO something (vs just respond)."""
        return self.type in ("TASK", "EMERGENCY", "CORRECTION")

    @property
    def is_conversational(self) -> bool:
        return self.type in ("CONVERSATION", "ACKNOWLEDGMENT")

    def __repr__(self):
        domains = f" domains={self.domain_hints}" if self.domain_hints else ""
        return f"Intent({self.type}, conf={self.confidence:.0%}, {self.detail}{domains})"


class IntentClassifier:
    """
    Fast intent classification without burning LLM tokens.
    
    Uses pattern matching + heuristics to classify messages BEFORE
    they reach the Brain LLM. This lets us:
    - Skip LLM entirely for "ok", "thanks", etc.
    - Pre-load relevant context (thread history, memory)
    - Inject only relevant domain knowledge into the prompt
    - Set the right response mode (chat vs autonomous execution)
    
    The classifier is deliberately conservative: when unsure,
    it lets the Brain decide (by classifying as CONVERSATION
    with low confidence, so the Brain gets full control).
    """

    # ═══════════════════════════════════════════════════
    #  Pattern Definitions
    # ═══════════════════════════════════════════════════

    # Emergency — highest priority, act NOW
    EMERGENCY_PATTERNS = [
        r"\b(stop|halt|kill|abort)\b",
        r"\b(emergency|urgent|asap|right now|immediately|now!)\b",
        r"\b(something.s wrong|broken|crashed|not working|it.s down)\b",
        r"\b(fix this now|fix it now|undo|revert|rollback)\b",
        r"\b(help!|SOS)\b",
        r"\b(stop everything|cancel everything|shut down|shut it down)\b",
    ]

    # Task — action required, deploy agents or execute commands
    TASK_PATTERNS = [
        # Creation/Building
        r"\b(create|build|make|write|generate|design|scaffold|bootstrap)\b",
        # Deployment/Infrastructure
        r"\b(deploy|install|setup|set up|configure|provision|launch|spin up)\b",
        # Search/Research
        r"\b(search|find|look up|lookup|check|scan|analyze|compare|research)\b",
        # Communication
        r"\b(send|email|message|notify|alert|remind|schedule|invite)\b",
        # File operations
        r"\b(organize|clean|move|copy|delete|rename|compress|extract|backup)\b",
        # Commerce
        r"\b(book|order|buy|purchase|subscribe|sign up|register)\b",
        # Monitoring
        r"\b(track|monitor|watch|follow|alert me|keep an eye)\b",
        # Development
        r"\b(refactor|debug|test|run|execute|compile|lint|format)\b",
        # Data
        r"\b(download|upload|transfer|sync|import|export|migrate)\b",
        # Modification
        r"\b(update|upgrade|change|modify|edit|add|remove|fix|patch)\b",
        # Planning
        r"\b(plan|outline|break down|decompose|prioritize|roadmap)\b",
    ]

    # Quick question — can answer with a command or from knowledge
    QUICK_PATTERNS = [
        r"^(what|when|where|who|how|which|why|is|are|do|does|did|can|could|will|would)\b",
        r"\b(what time|what day|weather|temperature|status|count|show me|list)\b",
        r"\b(how much|how many|how long|how far|how old)\b",
        r"\?$",  # Ends with question mark
    ]

    # Conversation — casual chat, opinions, feelings
    CONVERSATION_PATTERNS = [
        # Greetings
        r"^(hey|hi|hello|yo|sup|what.s up|how are you|how.s it going)[\s!?,.]*",
        r"^(good morning|good night|good evening|gm|gn|morning)[\s!?,.]*",
        # Gratitude
        r"^(thanks|thank you|ty|thx|appreciate|grateful)[\s!?,.]*",
        # Praise
        r"^(good job|nice work|well done|perfect|great|awesome|amazing|impressive)[\s!?,.]*",
        # Humor
        r"^(lol|lmao|haha|😂|🤣|funny|hilarious)",
        # Opinion seeking
        r"^(what do you think|your opinion|thoughts on|recommend|suggest)\b",
        r"^(tell me about|explain|describe|define)\b",
        # Personal
        r"^(i think|i feel|i want|i need|i like|i hate|i love|i wish)\b",
        # Meta
        r"^(who are you|what are you|what can you do|your name)\b",
    ]

    # Follow-up — references previous context
    FOLLOW_UP_PATTERNS = [
        # Status checks
        r"^(did it|was it|how did|what happened|did that|and\?|so\?|result|status|update)",
        # References
        r"\b(that|those|these|the one|the thing|what you|from before|from earlier|the last)\b",
        # Continuation
        r"^(try again|retry|do it again|one more time|keep going|continue|go on|next)\b",
        # Progress
        r"^(what about|how about|any update|progress|done yet|finished|ready)\b",
        # Iteration
        r"^(now|then|after that|next step|what.s next)\b",
    ]

    # Acknowledgment — just confirming, not a new task
    ACKNOWLEDGMENT_PATTERNS = [
        r"^(ok|okay|k|kk|sure|yep|yeah|yes|ya|yea)[\s!.]*$",
        r"^(got it|sounds good|perfect|great|nice|cool|bet|aight|alright|word)[\s!.]*$",
        r"^(go for it|do it|go ahead|proceed|lgtm|looks good|approved|confirmed)[\s!.]*$",
        r"^(roger|copy|affirmative|10-4|understood|ack)[\s!.]*$",
        r"^(👍|✅|🫡|💯|🤝|👌|🙏|💪|🔥|✌️)[\s]*$",
        r"^(thats? (fine|good|great|perfect|cool))[\s!.]*$",
        # Compound acknowledgments: "ok go ahead", "yeah do it", "sure go for it"
        r"^(ok|okay|yeah|yes|sure|yep|ya)[\s,.]*(go ahead|do it|go for it|proceed|sounds good|perfect|great|lets go|let.s go)[\s!.]*$",
    ]

    # ═══════════════════════════════════════════════════
    #  Domain Detection Patterns
    # ═══════════════════════════════════════════════════

    DOMAIN_PATTERNS = {
        "flights": [
            r"\b(flight|flights|fly|flying|airline|airport|travel|trip|layover)\b",
            r"\b(depart|departure|arrival|arrive|round.?trip|one.?way)\b",
            r"\b(cheapest|nonstop|business class|economy|first class)\b",
            r"\b(book|booking|ticket|fare|baggage|boarding)\b",
            r"\b(track.*price|price.*drop|alert.*price|price.*alert)\b",
        ],
        "email": [
            r"\b(email|e-mail|inbox|outbox|send.*mail|mail.*send)\b",
            r"\b(attachment|attach|forward|reply|cc|bcc|subject)\b",
            r"\b(smtp|outlook|gmail|inbox)\b",
        ],
        "dev": [
            r"\b(code|coding|program|programming|developer|development)\b",
            r"\b(git|github|repo|repository|commit|push|pull|branch|merge)\b",
            r"\b(prd|feature|bug|issue|refactor|api|endpoint|database)\b",
            r"\b(react|vue|angular|node|python|typescript|javascript|rust)\b",
            r"\b(vscode|vs code|ide|editor|debug|debugger|test|jest|pytest)\b",
            r"\b(docker|kubernetes|ci.?cd|pipeline|deploy|server|cloud)\b",
        ],
        "browser": [
            r"\b(browse|browser|chrome|website|web page|signup|sign.?up)\b",
            r"\b(login|log.?in|account|password|captcha|form)\b",
            r"\b(click|navigate|open.*page|go to|visit)\b",
        ],
        "research": [
            r"\b(research|investigate|deep.?dive|analyze|report|compare)\b",
            r"\b(find.*(info|information|details|data|specs|reviews))\b",
            r"\b(review|benchmark|comparison|versus|vs)\b",
        ],
        "files": [
            r"\b(file|files|folder|directory|organize|clean up|desktop)\b",
            r"\b(compress|zip|unzip|extract|archive)\b",
            r"\b(rename|move|copy|delete|trash)\b",
        ],
        "system": [
            r"\b(volume|brightness|dark mode|notification|screenshot)\b",
            r"\b(battery|disk|storage|memory|cpu|process)\b",
            r"\b(app|application|settings|preferences)\b",
            r"\b(calendar|reminder|note|notes)\b",
        ],
    }

    # ═══════════════════════════════════════════════════
    #  Main Classification Method
    # ═══════════════════════════════════════════════════

    def classify(self, text: str, has_active_thread: bool = False,
                 batch_type: str = "single") -> Intent:
        """
        Classify message intent without using LLM.
        
        Args:
            text: The message text to classify
            has_active_thread: Whether there's an active conversation thread
            batch_type: From MessageBatch — "single", "correction", "addition", "multi_task"
        
        Returns:
            Intent with type, confidence, and metadata
        """
        text_lower = text.lower().strip()

        # Strip emojis for pattern matching
        text_clean = re.sub(r"[^\w\s?.!,'\-/]", "", text_lower).strip()

        # Detect domain hints for all message types
        domain_hints = self._detect_domains(text_lower)

        # ── Priority 1: Emergency (always check first) ──
        emergency_score = self._score_patterns(text_clean, self.EMERGENCY_PATTERNS)
        if emergency_score >= 0.3:
            return Intent(
                type="EMERGENCY",
                confidence=min(1.0, emergency_score + 0.2),
                detail="urgent_action_required",
                needs_context=True,
                needs_memory=True,
                domain_hints=domain_hints,
            )

        # ── Priority 2: Acknowledgment (fast path, skip LLM) ──
        if self._matches_any(text_clean, self.ACKNOWLEDGMENT_PATTERNS):
            if has_active_thread:
                return Intent(
                    type="ACKNOWLEDGMENT",
                    confidence=0.95,
                    detail="confirm_and_proceed",
                    needs_context=True,
                )
            return Intent(
                type="ACKNOWLEDGMENT",
                confidence=0.90,
                detail="casual_confirm",
            )

        # ── Priority 3: Correction (from batch type) ──
        if batch_type == "correction":
            return Intent(
                type="CORRECTION",
                confidence=0.90,
                detail="modifying_previous_request",
                needs_context=True,
                needs_memory=True,
                domain_hints=domain_hints,
            )

        # ── Priority 4: Follow-up (needs active thread) ──
        follow_up_score = self._score_patterns(text_clean, self.FOLLOW_UP_PATTERNS)
        if follow_up_score >= 0.25 and has_active_thread:
            return Intent(
                type="FOLLOW_UP",
                confidence=min(1.0, follow_up_score + 0.3),
                detail="continuing_previous_thread",
                needs_context=True,
                needs_memory=True,
                domain_hints=domain_hints,
            )

        # ── Priority 5: Task (action required) ──
        task_score = self._score_patterns(text_clean, self.TASK_PATTERNS)
        if task_score >= 0.2:
            return Intent(
                type="TASK",
                confidence=min(1.0, task_score + 0.3),
                detail="action_required",
                needs_context=True,
                needs_memory=True,
                domain_hints=domain_hints,
            )

        # ── Priority 6: Quick question ──
        quick_score = self._score_patterns(text_clean, self.QUICK_PATTERNS)
        if quick_score >= 0.3:
            return Intent(
                type="QUICK_QUESTION",
                confidence=min(1.0, quick_score + 0.2),
                detail="info_request",
                needs_memory=True,
                domain_hints=domain_hints,
            )

        # ── Priority 7: Conversation ──
        conv_score = self._score_patterns(text_clean, self.CONVERSATION_PATTERNS)
        if conv_score >= 0.2:
            return Intent(
                type="CONVERSATION",
                confidence=min(1.0, conv_score + 0.3),
                detail="casual_chat",
                domain_hints=domain_hints,
            )

        # ── Priority 8: Length-based heuristic ──
        word_count = len(text.split())
        if word_count > 15:
            # Long message → probably a task description or detailed request
            return Intent(
                type="TASK",
                confidence=0.55,
                detail="inferred_from_length",
                needs_context=True,
                needs_memory=True,
                domain_hints=domain_hints,
            )

        if word_count > 8:
            # Medium length → could be task or question
            return Intent(
                type="QUICK_QUESTION",
                confidence=0.45,
                detail="inferred_medium_length",
                needs_memory=True,
                domain_hints=domain_hints,
            )

        # ── Default: Conversation (let Brain decide) ──
        return Intent(
            type="CONVERSATION",
            confidence=0.35,
            detail="ambiguous_short_message",
            domain_hints=domain_hints,
        )

    # ═══════════════════════════════════════════════════
    #  Domain Detection
    # ═══════════════════════════════════════════════════

    def _detect_domains(self, text: str) -> List[str]:
        """
        Detect which domains are relevant to this message.
        
        Returns a list of domain keys (e.g., ["flights", "email"]).
        Used to inject only relevant domain knowledge into the Brain prompt.
        """
        domains = []
        for domain, patterns in self.DOMAIN_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text):
                    domains.append(domain)
                    break  # One match per domain is enough
        return domains

    # ═══════════════════════════════════════════════════
    #  Scoring Helpers
    # ═══════════════════════════════════════════════════

    @staticmethod
    def _score_patterns(text: str, patterns: list) -> float:
        """Score how many patterns match (0.0 - 1.0)."""
        if not patterns:
            return 0.0
        matches = sum(1 for p in patterns if re.search(p, text))
        # Normalize: 1 match = 0.3, 2 = 0.6, 3+ = 0.8+
        return min(1.0, matches * 0.3)

    @staticmethod
    def _matches_any(text: str, patterns: list) -> bool:
        """Check if any pattern matches (exact match, not just search)."""
        return any(re.match(p, text) for p in patterns)
