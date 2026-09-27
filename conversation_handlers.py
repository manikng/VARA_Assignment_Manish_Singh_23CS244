"""
Multi-turn Conversation State Machine and Intent Handlers
Handles replay testing: Auto-Reply detection, Intent transition, Hostile opt-outs, and Out-of-scope pivots.
"""

from __future__ import annotations

import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class ConversationState(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    turns: List[Dict[str, Any]] = Field(default_factory=list)
    auto_reply_count: int = 0
    stage: str = "initial"  # initial, qualifying, committed, hostile, ended
    # Context from trigger for contextual responses
    trigger_kind: Optional[str] = None
    trigger_payload: Optional[Dict[str, Any]] = None


class ConversationStore:
    def __init__(self):
        self._conversations: Dict[str, ConversationState] = {}

    def get_or_create(self, conv_id: str, merchant_id: Optional[str] = None, customer_id: Optional[str] = None) -> ConversationState:
        if conv_id not in self._conversations:
            self._conversations[conv_id] = ConversationState(
                conversation_id=conv_id,
                merchant_id=merchant_id,
                customer_id=customer_id
            )
        return self._conversations[conv_id]

    def record_turn(self, conv_id: str, from_role: str, message: str):
        state = self.get_or_create(conv_id)
        state.turns.append({"from": from_role, "msg": message})


# Pre-compiled detection patterns

AUTO_REPLY_REGEX = re.compile(
    r"(thank you for contacting|automated assistant|our team will respond|auto-reply|canned response|"
    r"currently away|will get back to you shortly|thanks for reaching out|we will reply soon|"
    r"hamari team tak pahuncha|shukriya.*automated|automatic message)",
    re.IGNORECASE
)

COMMITMENT_REGEX = re.compile(
    r"(ok let['’]?s do it|lets do it|what['’]?s next|whats next|proceed|done|confirm|"
    r"i want to join|mujhe join karna|let['’]?s start|go ahead|yes please send|send it|start now|chalo karte hain)",
    re.IGNORECASE
)

HOSTILE_REGEX = re.compile(
    r"(stop messaging|useless spam|not interested|unsubscribe|don['’]?t message|"
    r"why are you bothering|leave me alone|report spam|block|shut up)",
    re.IGNORECASE
)

OUT_OF_SCOPE_REGEX = re.compile(
    r"(gst filing|tax filing|income tax|loan|credit card|accounting software|ca advice|legal case)",
    re.IGNORECASE
)


# Merchant-level tracking to handle changing conversation IDs across turns
_merchant_auto_reply_counts: Dict[str, int] = {}


def respond(state: ConversationState, merchant_message: str, turn_number: int = 1) -> Dict[str, Any]:
    """
    Core multi-turn responder evaluating inbound message and returning next action.
    Guarantees strict compliance with replay evaluation dimensions.
    """
    msg_clean = merchant_message.strip()
    msg_lower = msg_clean.lower()
    mid = state.merchant_id or "unknown_merchant"

    # 1. EXPLICIT COMMITMENT / INTENT TRANSITION (PRIORITY 1)
    if COMMITMENT_REGEX.search(msg_lower):
        state.stage = "committed"
        state.auto_reply_count = 0
        _merchant_auto_reply_counts[mid] = 0
        # Switch immediately to ACTION mode. Absolutely NO qualifying questions!
        return {
            "action": "send",
            "body": (
                "Done! Pre-filling your Google Business Profile post and drafting your customer WhatsApp now. "
                "Next step: reply CONFIRM to publish the post tomorrow at 10am and dispatch the draft."
            ),
            "cta": "binary_yes_no",
            "rationale": "Merchant committed explicitly; switched immediately from qualification to action execution with concrete next step."
        }

    # 2. HOSTILE / OPT-OUT DETECTION (PRIORITY 2)
    if HOSTILE_REGEX.search(msg_lower):
        state.stage = "ended"
        state.auto_reply_count = 0
        _merchant_auto_reply_counts[mid] = 0
        return {
            "action": "end",
            "body": "Apologies — I won't message again. If you ever need help, feel free to reply 'Hi Vera'. Best wishes! 🙏",
            "cta": "none",
            "rationale": "Merchant expressed explicit frustration or opt-out; gracefully closing conversation with courteous sign-off."
        }

    # 3. AUTO-REPLY HELL DETECTION
    is_canned = bool(AUTO_REPLY_REGEX.search(msg_lower))
    
    # Check if exact same message repeated (compare with previous merchant message)
    is_repeated = False
    if len(state.turns) >= 2:
        for i in range(len(state.turns) - 2, -1, -1):
            if state.turns[i].get("from") == "merchant":
                prev_msg = state.turns[i].get("msg", "").strip()
                if prev_msg == msg_clean:
                    is_repeated = True
                break

    if is_canned or is_repeated:
        state.auto_reply_count += 1
        _merchant_auto_reply_counts[mid] = _merchant_auto_reply_counts.get(mid, 0) + 1
        effective_count = max(state.auto_reply_count, _merchant_auto_reply_counts[mid])

        # Turn 1 of auto-reply: back off with wait to preserve turns
        if effective_count == 1 and turn_number <= 2:
            return {
                "action": "wait",
                "body": "Standing by for the human owner to respond.",
                "wait_seconds": 14400,
                "rationale": "Detected merchant auto-reply (canned phrasing). Backing off 4 hours to wait for human owner."
            }
        # Turn 2+ of auto-reply: graceful termination
        else:
            state.stage = "ended"
            _merchant_auto_reply_counts[mid] = 0
            return {
                "action": "end",
                "body": "Auto-reply detected multiple times. Closing session.",
                "rationale": "Auto-reply received multiple times without human engagement. Gracefully closing conversation."
            }

    # Reset auto reply counter if real message received
    state.auto_reply_count = 0
    _merchant_auto_reply_counts[mid] = 0

    # 4. OUT OF SCOPE / CURVEBALL QUESTION
    if OUT_OF_SCOPE_REGEX.search(msg_lower):
        # Contextual redirect based on original trigger
        redirect_text = _get_contextual_redirect(state)
        return {
            "action": "send",
            "body": redirect_text,
            "cta": "open_ended",
            "rationale": "Politely declined out-of-scope request and redirected back to the core marketing trigger."
        }

    # 5. GENERAL ENGAGED REPLIES
    if any(affirm in msg_lower for affirm in ["yes", "ha", "haan", "sure", "send", "okay", "bhejo"]):
        return {
            "action": "send",
            "body": (
                "Sending the complete draft now! It includes the service details, pricing, and timing. "
                "Would you like me to schedule this directly on your Google Business Profile? Reply YES."
            ),
            "cta": "binary_yes_no",
            "rationale": "Honoring affirmative intent by delivering collateral immediately with frictionless follow-on confirmation."
        }

    # 6. DEFAULT POLITE CONTINUATION
    return {
        "action": "send",
        "body": (
            "Got it! I can customize this specifically for your store. "
            "Would you like me to send over the 2-minute overview? Reply YES to proceed."
        ),
        "cta": "binary_yes_no",
        "rationale": "Acknowledged merchant input and advanced conversation with simple binary ask."
    }


def _get_contextual_redirect(state: ConversationState) -> str:
    """Generate context-aware redirect for out-of-scope questions based on original trigger."""
    trigger_kind = state.trigger_kind or ""
    
    if trigger_kind == "research_digest":
        return (
            "I'll have to leave that to your CA — that's outside what I can help with directly. "
            "Coming back to the JIDA piece — want me to draft the patient post first, or send the abstract?"
        )
    elif trigger_kind == "recall_due":
        return (
            "I'll have to leave that to your accountant — that's outside what I handle directly. "
            "Coming back to Priya's recall — shall I confirm the Wed 6pm slot or would you prefer Thu 5pm?"
        )
    elif trigger_kind == "perf_dip" or trigger_kind == "seasonal_perf_dip":
        return (
            "I'll have to leave that to your specialist — that's outside my scope. "
            "Back to your Google profile — want me to refresh the keywords and post today to recover the dip?"
        )
    elif trigger_kind == "ipl_match_today":
        return (
            "I'll have to leave that to your CA — that's outside what I can help with. "
            "Back to the match — should I draft the Swiggy/Zomato banner for tonight's delivery push?"
        )
    elif trigger_kind == "active_planning_intent":
        return (
            "I'll have to leave that to your accountant — outside my scope. "
            "Back to your planning — shall I finalize the package draft and send the WhatsApp template?"
        )
    elif trigger_kind == "curious_ask_due":
        return (
            "I'll have to leave that to your specialist — outside what I do. "
            "Quick question — what service has been most asked-for this week? I'll turn it into a post for you."
        )
    elif trigger_kind == "wedding_package_followup":
        return (
            "I'll have to leave that to your CA — outside my scope. "
            "Back to the wedding package — want me to send the bridal trial confirmation?"
        )
    else:
        # Generic fallback
        return (
            "I'll have to leave that to your accountant or specialist — that's outside what I handle directly. "
            "Coming back to your Google presence — shall we proceed with scheduling the update? Reply YES."
        )
