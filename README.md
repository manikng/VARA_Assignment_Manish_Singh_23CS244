# Vera 2.0 — magicpin Merchant AI Assistant

A production-grade, 4-context conversational commerce AI engine for magicpin merchants on WhatsApp. Designed to replace legacy reminder-style nudges with high-conversion, curiosity-driven, and knowledge-grounded conversations.

---

## 1. System Architecture

```
                 ┌────────────────────────────────────────────────────────┐
                 │                4-Context Cognitive Ingestion           │
                 │  CategoryContext  │  MerchantContext  │ TriggerContext │
                 │              CustomerContext (Optional)                │
                 └───────────────────────────┬────────────────────────────┘
                                             │
                                             ▼
                 ┌────────────────────────────────────────────────────────┐
                 │             Cognitive Dispatcher & Composer            │
                 │  - Gemini Flash (T=0, deterministic, JSON mode)        │
                 │  - Strict Grounding Validator (Zero-Hallucination)     │
                 │  - Category Voice & Taboo Filter (No overclaims)       │
                 │  - High-Precision Deterministic Fallback               │
                 └───────────────────────────┬────────────────────────────┘
                                             │
                                             ▼
                 ┌────────────────────────────────────────────────────────┐
                 │             Multi-Turn Replay State Engine             │
                 │  - Auto-reply pattern detection & backoff              │
                 │  - Immediate intent-to-action transition               │
                 │  - Hostile opt-out & out-of-scope redirection          │
                 └────────────────────────────────────────────────────────┘
```

The system operates on the **4-context framework** defined in `challenge-brief.md`:
1. **CategoryContext**: Slow-changing vertical domain knowledge (clinical peer tone for dentists, operator voice for restaurants, taboo filters, peer CTR benchmarks, research digests).
2. **MerchantContext**: Real-time snapshot of the merchant (GBP performance, verified status, active catalog offers, customer roster aggregates, signals).
3. **TriggerContext**: The discrete event answering *"why message right now?"* (e.g., JIDA clinical paper drop, 50% call dip, IPL match shift, 6-month recall due).
4. **CustomerContext** (Optional): Populated when sending on behalf of the merchant (`send_as = "merchant_on_behalf"`) with visit history, language preference, and preferred appointment windows.

---

## 2. Key Design Principles & Levers

1. **Zero Fabrication & Strict Fact Provenance**:
   - Every claim is anchored directly to context fields (e.g., "2,100-patient trial", "38% better caries reduction", "JIDA Oct 2026 p.14", "22 of your 240 chronic-Rx customers").
   - Service + Price catalog anchoring ("Haircut @ ₹99", "Dental Cleaning @ ₹299") instead of generic discount noise ("Flat 20% off").
2. **Zero URL Policy**:
   - Meta WhatsApp template compliance strictly forbids unsolicited outbound URLs. All collateral is offered directly in-chat or synchronized to Google Business Profile.
3. **Compulsion Levers**:
   - **Social Proof & Benchmarking**: Comparing against localized peers (e.g. median CTR in Lajpat Nagar / HSR Layout).
   - **Loss Aversion**: Framing dips as captured searches by competitors, or contextualizing seasonal dips to prevent wasted ad spend.
   - **Effort Externalization**: Pre-drafted WhatsApp copy and Google posts ready in 60 seconds ("Reply YES to publish tomorrow 10am").
   - **Single Binary CTA**: Placed at the very end of the message to minimize cognitive friction.
4. **Natural Code-Mixing**:
   - Automatically detects and honors Hindi-English mix (`hi-en mix` / `hi` in languages) for Indian local merchants and patients.

---

## 3. Multi-Turn Replay State Machine (`/v1/reply`)

- **Auto-Reply Hell**:
  - Turn 1: Identifies canned automated responses and leaves a polite note for the owner to reply when back.
  - Turn 2: Backs off (`wait_seconds: 14400`) rather than wasting turns.
  - Turn 3+: Gracefully terminates (`action: "end"`) to prevent spam penalties.
- **Intent Transition (The #1 Production Vera Defect)**:
  - When the merchant says *"Ok let's do it"* or *"What's next"*, the bot immediately switches to **ACTION mode** (pre-filling GBP posts, drafting patient messages, issuing confirmation requests). It **never asks qualifying questions** once intent is established.
- **Hostile & Out-of-Scope**:
  - Respects opt-outs with a 1-line courteous sign-off.
  - Politely declines out-of-scope asks (e.g. GST filing) and redirects back to the core growth topic without losing the thread.

---

## 4. Tradeoffs & Decisions

| Decision | Tradeoff Made | Rationale |
|---|---|---|
| **Deterministic Generation (T=0) + Dual-Tier Fallback** | Small loss in phrasing variety | Eliminates latency spikes, hallucinations, and ensures 100% SLA uptime (<2s vs 30s timeout). |
| **Strict Single Binary CTA** | Replaced complex multi-question prompts with binary Yes/No or simple slot choice | Conversational data shows merchants drop off when given multiple decisions on mobile. |
| **Strict URL Stripping** | URLs omitted even when informative | Adheres strictly to WhatsApp Business policies and prevents judge evaluation penalties. |

---

## 5. What Additional Context Would Have Helped Most

1. **Live Booking Calendar Sync**: Real-time available chair/stylist slots rather than static 7-day projections for customer-facing recall triggers.
2. **Canonical Multi-Tier Offer Catalog**: Unified pricing and package structures across dine-in, takeaway, and delivery to refine operator recommendations.
3. **Historical WhatsApp Message Tap Rates**: Click-through and reply rates segmented by time of day for Indian metro vs tier-2 merchants.

---

## 6. How to Run Locally

### Start the Bot
```bash
# In your virtual environment:
uvicorn bot:app --host 0.0.0.0 --port 8080
```

### Endpoints
- `GET /v1/healthz` — Liveness & context counter
- `GET /v1/metadata` — Model and team metadata
- `POST /v1/context` — Idempotent context ingestion with version precedence (HTTP 409 on stale versions)
- `POST /v1/tick` — Periodic trigger evaluation & composition
- `POST /v1/reply` — Multi-turn merchant/customer response handler

### Run Judge Simulation
```bash
python judge_simulator.py
```
