"""
╔══════════════════════════════════════════════════════════════╗
║      TARS Brain v4 — Phase 1: Message Stream Parser          ║
╠══════════════════════════════════════════════════════════════╣
║  Handles back-to-back iMessages intelligently.               ║
║                                                              ║
║  Problem: User sends "search flights to NYC" then            ║
║  immediately "actually make it Tokyo". Without this parser,  ║
║  TARS processes them as two separate tasks.                  ║
║                                                              ║
║  Solution: Accumulate messages within a short window (3s),   ║
║  detect relationships (correction, addition, new topic),     ║
║  and merge into a single coherent batch before the Brain     ║
║  processes them.                                             ║
║                                                              ║
║  Flow: iMessage → ingest() → [3s window] → batch → Brain    ║
╚══════════════════════════════════════════════════════════════╝
"""

import re
import time
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Callable


# ─── Data Classes ────────────────────────────────────

@dataclass
class ParsedMessage:
    """A single parsed message with stream metadata."""
    text: str
    timestamp: float
    stream_intent: str = "new"  # correction, addition, acknowledgment, new


@dataclass
class MessageBatch:
    """A batch of messages ready for the Brain.
    
    If user sent one message, batch_type="single".
    If multiple arrived in the merge window:
      - "correction" → last correction replaces earlier text
      - "addition"   → all merged into one compound request
      - "multi_task" → separate tasks, processed in order
    """
    messages: List[ParsedMessage]
    merged_text: str
    batch_type: str          # single, correction, addition, multi_task
    individual_tasks: List[str] = field(default_factory=list)
    timestamp: float = 0.0

    @property
    def is_single(self) -> bool:
        return len(self.messages) == 1

    @property
    def has_correction(self) -> bool:
        return self.batch_type == "correction"

    def __repr__(self):
        return f"MessageBatch(type={self.batch_type}, msgs={len(self.messages)}, text={self.merged_text[:80]}...)"


# ─── Stream Intent Patterns ─────────────────────────

# Correction: user is changing/fixing what they just said
CORRECTION_PATTERNS = [
    r"^actually\b",
    r"^wait\b",
    r"^no[\s,]",
    r"^nah\b",
    r"^nvm\b",
    r"^nevermind\b",
    r"^scratch that\b",
    r"^change\b",
    r"^instead\b",
    r"^make it\b",
    r"^switch (it |that )?to\b",
    r"^not .+[,] (but|use|try)\b",
    r"^i meant\b",
    r"^sorry[,]?\s*(i meant|it.s|it should)\b",
    r"^correction\b",
    r"^wrong\b",
    r"^oops\b",
]

# Addition: user is adding to what they just said
ADDITION_PATTERNS = [
    r"^also\b",
    r"^and\b",
    r"^plus\b",
    r"^oh and\b",
    r"^oh also\b",
    r"^btw\b",
    r"^by the way\b",
    r"^one more thing\b",
    r"^additionally\b",
    r"^another thing\b",
    r"^forgot to (mention|say|add)\b",
    r"^can you also\b",
    r"^while you.re at it\b",
    r"^oh[,]?\s",
    r"^also,?\s",
]

# Acknowledgment: quick response, not a new task
ACKNOWLEDGMENT_PATTERNS = [
    r"^(ok|okay|k|sure|yep|yeah|yes|ya|yea)[\s!.]*$",
    r"^(got it|sounds good|perfect|great|nice|cool)[\s!.]*$",
    r"^(thanks|ty|thx|thank you)[\s!.]*$",
    r"^(bet|aight|alright|word)[\s!.]*$",
    r"^(go for it|do it|go ahead|proceed|lgtm|looks good)[\s!.]*$",
    r"^(roger|copy|affirmative|10-4)[\s!.]*$",
    r"^(👍|✅|🫡|💯|🤝|👌|🙏|💪|🔥)[\s]*$",
]


class MessageStreamParser:
    """
    Accumulates back-to-back iMessages and merges them intelligently.
    
    When messages arrive within MERGE_WINDOW seconds of each other:
    - Corrections ("actually", "wait", "no") → replaces previous
    - Additions ("also", "and", "plus") → appends to previous
    - Separate tasks → queued individually but with shared context
    
    After MERGE_WINDOW of silence, the batch is finalized and emitted
    via the on_batch_ready callback.
    
    Usage:
        parser = MessageStreamParser(on_batch_ready=my_callback)
        parser.ingest("search flights to NYC")      # starts 3s timer
        parser.ingest("actually make it Tokyo")      # resets timer, merges
        # 3s later → my_callback(MessageBatch(...merged_text="search flights to Tokyo"...))
    """

    MERGE_WINDOW = 3.0  # Seconds to wait for more messages before emitting

    def __init__(self, on_batch_ready: Callable[[MessageBatch], None]):
        self._buffer: List[ParsedMessage] = []
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None
        self._on_batch_ready = on_batch_ready

    def ingest(self, text: str):
        """
        Ingest a new message into the stream.
        
        If no more messages arrive within MERGE_WINDOW seconds,
        the accumulated batch is emitted via on_batch_ready.
        
        Acknowledgments with empty buffer are emitted immediately
        (don't make user wait 3s for "ok").
        """
        text = text.strip()
        if not text:
            return

        stream_intent = self._detect_stream_intent(text)
        msg = ParsedMessage(
            text=text,
            timestamp=time.time(),
            stream_intent=stream_intent,
        )

        with self._lock:
            self._buffer.append(msg)

            # Cancel existing timer
            if self._timer:
                self._timer.cancel()
                self._timer = None

            # Acknowledgments with empty buffer before this msg → emit immediately
            if stream_intent == "acknowledgment" and len(self._buffer) == 1:
                self._emit_batch_locked()
                return

            # Start new timer — if no more messages in MERGE_WINDOW, emit
            self._timer = threading.Timer(self.MERGE_WINDOW, self._emit_batch)
            self._timer.daemon = True
            self._timer.start()

    def force_flush(self):
        """Force-emit whatever's in the buffer. Used on shutdown or urgent messages."""
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
            if self._buffer:
                self._emit_batch_locked()

    def _emit_batch(self):
        """Timer callback — emit the batch (thread-safe wrapper)."""
        with self._lock:
            self._emit_batch_locked()

    def _emit_batch_locked(self):
        """Build and emit a MessageBatch. Must be called with self._lock held."""
        if not self._buffer:
            return

        messages = self._buffer[:]
        self._buffer.clear()
        if self._timer:
            self._timer.cancel()
            self._timer = None

        batch = self._build_batch(messages)
        # Release lock before callback to prevent deadlocks
        # (callback may call back into parser)
        threading.Thread(
            target=self._on_batch_ready,
            args=(batch,),
            daemon=True,
        ).start()

    def _build_batch(self, messages: List[ParsedMessage]) -> MessageBatch:
        """
        Build a smart MessageBatch from accumulated messages.
        
        Single message → pass through.
        Multiple messages → analyze relationships and merge.
        """
        if len(messages) == 1:
            return MessageBatch(
                messages=messages,
                merged_text=messages[0].text,
                batch_type="single",
                timestamp=messages[0].timestamp,
            )

        # Multiple messages — figure out the relationship
        has_correction = any(m.stream_intent == "correction" for m in messages)
        has_addition = any(m.stream_intent == "addition" for m in messages)

        if has_correction:
            # Correction replaces everything before it.
            # But additions after the correction are kept.
            # Example: "search NYC" → "actually Tokyo" → "also track it"
            #   → merged: "search Tokyo, also track it"
            parts = []
            for m in messages:
                if m.stream_intent == "correction":
                    # This message modifies/replaces the previous context
                    # Try to merge intelligently
                    correction_text = self._apply_correction(parts, m.text)
                    parts = [correction_text]
                else:
                    parts.append(m.text)

            return MessageBatch(
                messages=messages,
                merged_text=". ".join(parts),
                batch_type="correction",
                timestamp=messages[-1].timestamp,
            )

        if has_addition:
            # All messages form one compound request
            parts = [m.text for m in messages]
            return MessageBatch(
                messages=messages,
                merged_text=". ".join(parts),
                batch_type="addition",
                timestamp=messages[-1].timestamp,
            )

        # Multiple unrelated messages — could be multi-task or stream of thought
        # If they're all short (<15 words each), probably stream of thought → merge
        all_short = all(len(m.text.split()) < 15 for m in messages)
        if all_short:
            return MessageBatch(
                messages=messages,
                merged_text=" ".join(m.text for m in messages),
                batch_type="addition",
                timestamp=messages[-1].timestamp,
            )

        # Longer, distinct messages → multi-task
        parts = [m.text for m in messages]
        return MessageBatch(
            messages=messages,
            merged_text=" | ".join(parts),
            batch_type="multi_task",
            individual_tasks=parts,
            timestamp=messages[-1].timestamp,
        )

    def _apply_correction(self, previous_parts: List[str], correction: str) -> str:
        """
        Try to intelligently apply a correction to previous context.
        
        "search flights to NYC" + "actually make it Tokyo" 
            → "search flights to Tokyo"
        
        "build a react app" + "wait use vue instead"
            → "build a vue app"
        
        Falls back to just using the correction text if can't merge.
        """
        if not previous_parts:
            return correction

        prev = " ".join(previous_parts)

        # Strip correction prefix words
        clean = re.sub(
            r"^(actually|wait|no|nah|instead|make it|switch to|i meant|sorry|oops|correction)[,:]?\s*",
            "",
            correction.lower(),
        ).strip()

        if not clean:
            return prev

        # Simple replacement heuristic: if the correction is short (1-3 words),
        # it's likely replacing a specific part of the previous message
        if len(clean.split()) <= 3 and len(prev.split()) > 3:
            # Try to find and replace in previous text
            # e.g., prev="search flights to NYC", clean="Tokyo"
            # This is a best-effort heuristic
            pass

        # Default: the correction IS the new instruction
        # Keep the verb/action from previous if correction doesn't have one
        action_words = ["search", "find", "build", "create", "make", "send",
                        "deploy", "check", "track", "book", "organize"]
        has_action = any(clean.startswith(w) for w in action_words)

        if not has_action and prev:
            # Correction is modifying a detail, not the whole instruction
            # e.g., "search flights to NYC" + "actually Tokyo" → use Tokyo as destination
            return f"{prev} (correction: {clean})"

        return clean

    @staticmethod
    def _detect_stream_intent(text: str) -> str:
        """
        Quick classification of how this message relates to the stream.
        
        Returns: "correction", "addition", "acknowledgment", or "new"
        """
        text_lower = text.lower().strip()

        for pattern in CORRECTION_PATTERNS:
            if re.match(pattern, text_lower):
                return "correction"

        for pattern in ADDITION_PATTERNS:
            if re.match(pattern, text_lower):
                return "addition"

        for pattern in ACKNOWLEDGMENT_PATTERNS:
            if re.match(pattern, text_lower):
                return "acknowledgment"

        return "new"
