"""
magicpin AI Challenge — Vera Merchant Assistant (Production Implementation)
Author: Senior AI/ML Engineer
Contract: challenge-brief.md & challenge-testing-brief.md
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from composer import EngagementComposer
from conversation_handlers import ConversationStore, respond
from models import (
    ContextPushRequest,
    TickRequest,
    TickResponse,
    ActionItem,
    ReplyRequest,
    ReplyResponse,
    HealthzResponse,
    MetadataResponse,
)

app = FastAPI(
    title="Vera 2.0 Merchant AI Assistant",
    description="Intelligent 4-context cognitive routing WhatsApp engagement assistant for magicpin merchants",
    version="2.0.0"
)

START_TIME = time.time()

# Central in-memory state stores
contexts: Dict[Tuple[str, str], Dict[str, Any]] = {}  # (scope, context_id) -> {"version": int, "payload": dict}
suppressed_keys: set[str] = set()
conversation_store = ConversationStore()
composer = EngagementComposer()


def compose(category: dict, merchant: dict, trigger: dict, customer: dict | None = None) -> dict:
    """
    Submission contract requirement from challenge-brief.md §7.1:
    Inputs are dicts loaded from dataset JSON.
    Returns dict with keys: body, cta, send_as, suppression_key, rationale.
    """
    return composer.compose(category, merchant, trigger, customer)


@app.get("/v1/healthz", response_model=HealthzResponse)
async def healthz():
    """Liveness probe reporting uptime and loaded contexts count."""
    counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
    for (scope, _), _ in contexts.items():
        if scope in counts:
            counts[scope] += 1
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME),
        "contexts_loaded": counts
    }


@app.get("/v1/metadata", response_model=MetadataResponse)
async def metadata():
    """Identity and approach metadata."""
    return {
        "team_name": "Team_Manish_Singh (Vera 2.0)",
        "team_members": ["Manish Singh"],
        "model": "gemini-flash-latest",
        "approach": "4-context cognitive routing composer with intent-state machine & few-shot anchor reasoning",
        "contact_email": "[manishsingh_23cs244@dtu.ac.in]",
        "version": "2.0.0",
        "submitted_at": "2026-04-26T08:00:00Z"
    }


@app.post("/v1/context")
async def push_context(body: ContextPushRequest):
    """
    Receive context pushes from judge harness.
    Enforces idempotency and version-precedence.
    """
    key = (body.scope, body.context_id)
    current = contexts.get(key)

    # If version is strictly older than existing, reject with 409
    if current and current["version"] > body.version:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "accepted": False,
                "reason": "stale_version",
                "current_version": current["version"]
            }
        )

    # Store atomically
    contexts[key] = {
        "version": body.version,
        "payload": body.payload
    }

    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "accepted": True,
        "ack_id": f"ack_{body.context_id}_v{body.version}",
        "stored_at": now_iso
    }


@app.post("/v1/tick", response_model=TickResponse)
async def tick(body: TickRequest):
    """
    Periodic wake-up endpoint. Inspects available triggers and composes high-value sends.
    """
    actions: List[ActionItem] = []

    for trg_id in body.available_triggers:
        trg_entry = contexts.get(("trigger", trg_id))
        if not trg_entry:
            continue
        trg = trg_entry.get("payload", {})
        suppression_key = trg.get("suppression_key")

        # Skip if already suppressed
        if suppression_key and suppression_key in suppressed_keys:
            continue

        merchant_id = trg.get("merchant_id")
        customer_id = trg.get("customer_id")

        merchant_entry = contexts.get(("merchant", merchant_id))
        if not merchant_entry:
            continue
        merchant = merchant_entry.get("payload", {})

        cat_slug = merchant.get("category_slug")
        category_entry = contexts.get(("category", cat_slug))
        category = category_entry.get("payload", {}) if category_entry else {"slug": cat_slug}

        customer = None
        if customer_id:
            c_entry = contexts.get(("customer", customer_id))
            if c_entry:
                customer = c_entry.get("payload")

        # Compose message
        composed = compose(category, merchant, trg, customer)

        # Mark suppression key as used
        if suppression_key:
            suppressed_keys.add(suppression_key)

        conv_id = f"conv_{merchant_id}_{trg_id}"

        # Store trigger context in conversation state for contextual responses
        conv_state = conversation_store.get_or_create(conv_id, merchant_id, customer_id)
        conv_state.trigger_kind = trg.get("kind")
        conv_state.trigger_payload = trg.get("payload")

        actions.append(
            ActionItem(
                conversation_id=conv_id,
                merchant_id=merchant_id,
                customer_id=customer_id,
                send_as=composed.get("send_as", "vera"),
                trigger_id=trg_id,
                template_name=composed.get("template_name", "vera_generic_v1"),
                template_params=composed.get("template_params", [merchant.get("identity", {}).get("name", "Merchant")]),
                body=composed.get("body", ""),
                cta=composed.get("cta", "binary_yes_no"),
                suppression_key=composed.get("suppression_key", suppression_key or ""),
                rationale=composed.get("rationale", "Composed with 4-context alignment.")
            )
        )

        # Cap actions per tick at 20 as specified in testing brief
        if len(actions) >= 20:
            break

    return {"actions": actions}


@app.post("/v1/reply", response_model=ReplyResponse)
async def reply(body: ReplyRequest):
    """
    Handle inbound merchant/customer replies.
    Orchestrates replay testing: Auto-Reply detection, intent transitions, hostility, and redirection.
    """
    state = conversation_store.get_or_create(
        conv_id=body.conversation_id,
        merchant_id=body.merchant_id,
        customer_id=body.customer_id
    )
    state.turns.append({"from": body.from_role, "msg": body.message})

    # Evaluate using conversation state machine
    res = respond(state, body.message, body.turn_number)
    return res


@app.post("/v1/teardown")
async def teardown():
    """Wipe in-memory state at end of test as requested by judge harness (§11)."""
    global contexts, suppressed_keys, conversation_store
    contexts.clear()
    suppressed_keys.clear()
    conversation_store._conversations.clear()
    return {"status": "ok", "message": "State wiped successfully"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:app", host="0.0.0.0", port=8080, reload=False)
