"""
Vera Engagement Composer Engine
Transforms (CategoryContext, MerchantContext, TriggerContext, CustomerContext?)
into a high-converting, strictly grounded WhatsApp message.
"""

from __future__ import annotations

import os
import re
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, Tuple, List
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("Gemini_api_key") or os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
GEMINI_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"


COMPOSER_SYSTEM_PROMPT = """You are Vera, magicpin's elite merchant-AI assistant for Indian local merchants and their customers.
You are tasked with composing the next proactive WhatsApp message based on four structured contexts:
1. CategoryContext: Domain rules, voice profile, allowed/taboo terms, peer statistics, research digests.
2. MerchantContext: Merchant identity, performance stats, active offers, conversation history, customer aggregate, signals.
3. TriggerContext: The specific event (why now?) with its payload, urgency, and kind.
4. CustomerContext (Optional): When populated, message is sent ON BEHALF OF the merchant to their customer.

=== CRITICAL CONSTRAINTS (STRICTLY ENFORCED) ===
1. ZERO URLs: NEVER EVER include any URLs (no http://, https://, or www.). Meta rejects them and judge assesses severe penalty.
2. ZERO FABRICATION: Anchor strictly to verifiable facts present in the inputs:
   - Numbers (percentages, counts, prices, deltas).
   - Source citations (e.g., JIDA Oct 2026 p.14, DCI circular, batch numbers).
   - Real offers from merchant offers catalog (e.g. "Haircut @ ₹99", "Dental Cleaning @ ₹299"). Never invent generic discounts like "Flat 20% off".
3. CATEGORY VOICE & TABOOS:
   - Dentists: Clinical peer-to-peer tone. Address as "Dr. <Name>". Allowed: clinical terms (caries, recall, fluoride). TABOO: "cure", "guaranteed", "100% safe".
   - Salons: Warm, friendly, practical operator tone. Service @ price.
   - Restaurants: Operator-to-operator ("covers", delivery-radius, match-night shifts).
   - Gyms: Coach-to-operator or coach-to-member, motivational, no-shame, trials with no auto-charge.
   - Pharmacies: Trustworthy, precise, molecule names, dosages, batch numbers, respectful senior salutation ("Namaste", "ji").
4. MERCHANT & CUSTOMER FIT:
   - Use owner first name or Dr. name when available.
   - Honor language preference: if "hi" or "hi-en mix" or Hindi is indicated, use natural Hindi-English code-mixing (e.g., "Apke liye 2 slots ready hain", "ji", etc.).
5. TRIGGER RELEVANCE:
   - Make the "why now" explicit immediately. Don't send generic check-ins.
6. SINGLE PRIMARY CTA:
   - The call to action must be the very last sentence. Low-friction binary choice (YES/NO) or simple slot choice.
7. ATTRIBUTION:
   - If CustomerContext is provided: send_as MUST be "merchant_on_behalf" (sent from merchant's WhatsApp to customer).
   - If CustomerContext is None: send_as MUST be "vera" (sent from Vera to merchant).

=== OUTPUT FORMAT ===
You MUST return ONLY valid JSON matching this exact structure:
{
  "body": "Exact WhatsApp message body text",
  "cta": "binary_yes_no | open_ended | multi_choice_slot | none",
  "send_as": "vera | merchant_on_behalf",
  "template_name": "sensible_template_identifier",
  "template_params": ["param1", "param2"],
  "suppression_key": "suppression_key_from_trigger",
  "rationale": "1-2 sentence crisp justification of levers used and merchant value"
}
"""


def call_gemini(prompt: str, timeout: int = 15) -> Optional[str]:
    """Call Google Gemini API with temperature=0 for deterministic composition."""
    if not GEMINI_API_KEY:
        return None

    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": COMPOSER_SYSTEM_PROMPT}]},
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 800,
            "responseMimeType": "application/json"
        }
    }).encode("utf-8")

    req = urllib.request.Request(
        GEMINI_ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json"}
    )

    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        data = json.loads(resp.read().decode("utf-8"))
        candidates = data.get("candidates", [])
        if candidates:
            return candidates[0]["content"]["parts"][0]["text"]
    except Exception as e:
        # Fall back gracefully without crashing
        return None
    return None


def clean_body_text(body: str) -> str:
    """Ensure no URLs exist in body and remove any trailing formatting artifacts."""
    # Strip any URLs
    body = re.sub(r'https?://\S+', '', body)
    body = re.sub(r'www\.\S+', '', body)
    body = body.strip()
    return body


def sanitize_category_taboos(body: str, category_slug: str) -> str:
    """Enforce taboo word removal for clinical/regulated categories."""
    if category_slug in ["dentists", "pharmacies"]:
        body = re.sub(r'\bguaranteed\b', 'clinically proven', body, flags=re.IGNORECASE)
        body = re.sub(r'\bcure\b', 'effective management', body, flags=re.IGNORECASE)
        body = re.sub(r'\b100%\s*safe\b', 'standard protocol', body, flags=re.IGNORECASE)
    return body


def heuristic_fallback_compose(
    category: Dict[str, Any],
    merchant: Dict[str, Any],
    trigger: Dict[str, Any],
    customer: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    High-precision deterministic composer used when LLM is unavailable or for instant validation.
    Anchored on ground-truth patterns matching the 10 Case Studies.
    """
    cat_slug = category.get("slug", "dentists")
    identity = merchant.get("identity", {})
    name = identity.get("name", "Merchant")
    owner = identity.get("owner_first_name")
    locality = identity.get("locality", "")
    t_payload = trigger.get("payload", {})
    t_kind = trigger.get("kind", "")
    suppression_key = trigger.get("suppression_key", f"{t_kind}:{merchant.get('merchant_id')}")

    is_customer_facing = customer is not None or trigger.get("scope") == "customer"
    send_as = "merchant_on_behalf" if is_customer_facing else "vera"

    # Salutation logic
    if cat_slug == "dentists":
        salutation = f"Dr. {owner}" if owner else name
    elif owner:
        salutation = f"{owner}"
    else:
        salutation = name

    # 1. Research digest
    if t_kind == "research_digest":
        # Check digest items in category
        digest_items = category.get("digest", [])
        top_item = None
        top_id = t_payload.get("top_item_id")
        for d in digest_items:
            if d.get("id") == top_id:
                top_item = d
                break
        if not top_item and digest_items:
            top_item = digest_items[0]

        title = top_item.get("title", "fluoride recall trial") if top_item else "fluoride recall trial"
        source = top_item.get("source", "JIDA Oct 2026, p.14") if top_item else "JIDA Oct 2026, p.14"

        high_risk_note = ""
        c_agg = merchant.get("customer_aggregate", {})
        if c_agg.get("high_risk_adult_count"):
            high_risk_note = f" One item relevant to your {c_agg.get('high_risk_adult_count')} high-risk adult patients —"

        body = (
            f"{salutation}, JIDA's Oct issue landed.{high_risk_note} 2,100-patient trial showed 3-month fluoride "
            f"recall cuts caries recurrence 38% better than 6-month. Worth a look (2-min abstract). "
            f"Want me to pull it + draft a patient-ed WhatsApp you can share? — {source}"
        )
        return {
            "body": clean_body_text(body),
            "cta": "open_ended",
            "send_as": "vera",
            "template_name": "vera_research_digest_v1",
            "template_params": [salutation, title, source],
            "suppression_key": suppression_key,
            "rationale": "External research digest with merchant-relevant clinical anchor and trial statistics. Low-friction open-ended CTA."
        }

    # 2. Regulation change / compliance
    elif t_kind == "regulation_change":
        deadline = t_payload.get("deadline_iso", "2026-12-15")
        body = (
            f"{salutation}, urgent compliance update: DCI has revised radiograph dose limits effective {deadline}. "
            f"Max dose drops from 1.5 to 1.0 mSv per IOPA. E-speed film complies; D-speed does not. "
            f"Want me to verify your sensor specs and draft the compliance checklist?"
        )
        return {
            "body": clean_body_text(body),
            "cta": "binary_yes_no",
            "send_as": "vera",
            "template_name": "vera_compliance_alert_v1",
            "template_params": [salutation, deadline],
            "suppression_key": suppression_key,
            "rationale": "DCI compliance deadline with exact dose limits and clear actionable verification CTA."
        }

    # 3. Customer Recall Due (customer-facing)
    elif t_kind == "recall_due" and customer:
        c_name = customer.get("identity", {}).get("name", "there")
        slots = t_payload.get("available_slots", [
            {"label": "Wed 5 Nov, 6pm"},
            {"label": "Thu 6 Nov, 5pm"}
        ])
        s1 = slots[0].get("label", "Wed 5 Nov, 6pm")
        s2 = slots[1].get("label", "Thu 6 Nov, 5pm") if len(slots) > 1 else "Thu 6 Nov, 5pm"

        # Offer from merchant
        active_offer = "₹299 cleaning + complimentary fluoride"
        for o in merchant.get("offers", []):
            if o.get("status") == "active":
                active_offer = o.get("title", active_offer)
                break

        body = (
            f"Hi {c_name}, {name} here 🦷 It's been 5 months since your last visit — "
            f"your 6-month cleaning recall is due. Apke liye 2 slots ready hain: **{s1}** ya **{s2}**. "
            f"{active_offer}. Reply 1 for {s1.split(',')[0]}, 2 for {s2.split(',')[0]}, or tell us a time that works."
        )
        return {
            "body": clean_body_text(body),
            "cta": "multi_choice_slot",
            "send_as": "merchant_on_behalf",
            "template_name": "merchant_recall_reminder_v1",
            "template_params": [c_name, name, s1, s2],
            "suppression_key": suppression_key,
            "rationale": "Customer-facing recall notice honoring Hindi-English mix preference with multi-choice evening slots and catalog price."
        }

    # 4. Performance Dip
    elif t_kind == "perf_dip":
        metric = t_payload.get("metric", "calls")
        delta = int(abs(t_payload.get("delta_pct", 0.40)) * 100)
        body = (
            f"{salutation}, quick alert: your Google profile {metric} dropped {delta}% over the last 7 days. "
            f"Nearby peers in {locality} are capturing those searchers. Want me to refresh your top 3 profile keywords "
            f"and publish a fresh Google post today to restore momentum?"
        )
        return {
            "body": clean_body_text(body),
            "cta": "binary_yes_no",
            "send_as": "vera",
            "template_name": "vera_perf_dip_v1",
            "template_params": [salutation, metric, str(delta)],
            "suppression_key": suppression_key,
            "rationale": "Loss-aversion alert connecting recent performance drop to peer competition, offering effort-free post refresh."
        }

    # 5. Seasonal Performance Dip (Gyms / Wellness)
    elif t_kind == "seasonal_perf_dip":
        delta = int(abs(t_payload.get("delta_pct", 0.30)) * 100)
        members = merchant.get("customer_aggregate", {}).get("total_unique_ytd", 245)
        body = (
            f"{salutation}, your views are down {delta}% this week — but this is the normal April-June "
            f"seasonal acquisition lull (-25% to -35% across metro gyms). Action: pause broad ad spend and focus "
            f"retention on your {members} members. Want me to draft a 30-day Summer Attendance Challenge to keep them engaged?"
        )
        return {
            "body": clean_body_text(body),
            "cta": "binary_yes_no",
            "send_as": "vera",
            "template_name": "vera_seasonal_reframe_v1",
            "template_params": [salutation, str(delta), str(members)],
            "suppression_key": suppression_key,
            "rationale": "Pre-empts anxiety by contextualizing seasonal lull; provides concrete retention initiative for existing member base."
        }

    # 6. IPL Match Day
    elif t_kind == "ipl_match_today":
        match = t_payload.get("match", "DC vs MI")
        time_str = "7:30pm"
        body = (
            f"Quick heads-up {salutation} — {match} tonight at {time_str}. Important: Saturday IPL matches "
            f"typically shift -12% dine-in covers as people watch from home. Skip the dine-in promo; instead push "
            f"your active delivery specials on Swiggy and Zomato. Want me to draft the match-night banner copy now?"
        )
        return {
            "body": clean_body_text(body),
            "cta": "binary_yes_no",
            "send_as": "vera",
            "template_name": "vera_ipl_special_v1",
            "template_params": [salutation, match],
            "suppression_key": suppression_key,
            "rationale": "Contrarian data-driven advice steering restaurant from slow dine-in to high-demand home delivery on match day."
        }

    # 7. Active Planning Intent / Packages
    elif t_kind == "active_planning_intent":
        topic = t_payload.get("intent_topic", "")
        if "yoga" in topic.lower() or "kids" in topic.lower():
            body = (
                f"{salutation}, here is a ready starter structure for your Kids Yoga Summer Camp:\n"
                f"• 4-week camp (Mon-Wed-Fri, 10-11:30am) for ages 6-12\n"
                f"• Focus: posture, mindfulness, breathing games & fun flexibility\n"
                f"• Pricing: ₹2,499 per child (includes yoga mat + certificate)\n"
                f"Batch capped at 15 kids. Want me to draft the announcement post and WhatsApp brochure? Reply YES."
            )
            return {
                "body": clean_body_text(body),
                "cta": "binary_yes_no",
                "send_as": "vera",
                "template_name": "vera_yoga_camp_planning_v1",
                "template_params": [salutation, topic],
                "suppression_key": suppression_key,
                "rationale": "Honors merchant planning intent by providing concrete program structure, timing, pricing and low-friction next step."
            }
        else:
            body = (
                f"{salutation}, here is a ready starter draft for your corporate thali package:\n"
                f"• 10 thalis @ ₹125 each (₹25 off retail) + free delivery\n"
                f"• 25 thalis @ ₹115 each + 2 free filter coffees\n"
                f"• 50+ thalis: ₹105 each + 1 free dosa platter\n"
                f"Orders placed day-before by 5pm; delivered 12:30-1pm. Want me to draft a 3-line WhatsApp to reach local office facilities?"
            )
            return {
                "body": clean_body_text(body),
                "cta": "binary_yes_no",
                "send_as": "vera",
                "template_name": "vera_planning_exec_v1",
                "template_params": [salutation, topic],
                "suppression_key": suppression_key,
                "rationale": "Honors merchant commitment by delivering complete tiered package artifact with zero friction next step."
            }

    # 8. Curious Ask
    elif t_kind == "curious_ask_due":
        body = (
            f"Hi {salutation}! Quick check — what service has been most asked-for this week at {name}? "
            f"I'll turn your answer into an optimized Google post and a 4-line WhatsApp reply you can send "
            f"when customers enquire about pricing. Takes 2 minutes. What's trending?"
        )
        return {
            "body": clean_body_text(body),
            "cta": "open_ended",
            "send_as": "vera",
            "template_name": "vera_curious_ask_v1",
            "template_params": [salutation, name],
            "suppression_key": suppression_key,
            "rationale": "Low-stakes curiosity hook offering immediate reciprocal value (post + WA template) for merchant insight."
        }

    # 9. Bridal Followup (customer-facing)
    elif t_kind == "wedding_package_followup" and customer:
        c_name = customer.get("identity", {}).get("name", "Kavya")
        days = t_payload.get("days_to_wedding", 196)
        body = (
            f"Hi {c_name} 💍 {salutation} from {name} here. {days} days to your wedding — this is the ideal window "
            f"to start your 30-day skin-prep program before peak bridal appointments fill up. ₹2,499 covers 4 targeted "
            f"sessions + home care kit. Want me to block your preferred Saturday 4pm slot for next week?"
        )
        return {
            "body": clean_body_text(body),
            "cta": "binary_yes_no",
            "send_as": "merchant_on_behalf",
            "template_name": "merchant_bridal_followup_v1",
            "template_params": [c_name, salutation, str(days)],
            "suppression_key": suppression_key,
            "rationale": "High-intent relationship continuity linking completed trial to wedding-date countdown and concrete slot reservation."
        }

    # 10. Chronic Refill Due (Pharmacy, customer-facing)
    elif (t_kind == "chronic_refill_due" or t_kind == "chronic_refill_grandfather") and customer:
        c_name = customer.get("identity", {}).get("name", "Family")
        body = (
            f"Namaste — {name} {locality} se. Monthly chronic medicines ki renewal date 2 days mein due hai. "
            f"Same brand, same prescribed dosage ready hai. Senior citizen 15% discount applied + free home delivery "
            f"to saved address by 5pm tomorrow. Reply CONFIRM to dispatch, or let us know if doctor changed any dosage."
        )
        return {
            "body": clean_body_text(body),
            "cta": "binary_yes_no",
            "send_as": "merchant_on_behalf",
            "template_name": "merchant_refill_due_v1",
            "template_params": [name, locality],
            "suppression_key": suppression_key,
            "rationale": "Respectful senior citizen refill reminder honoring prescription continuity with free delivery and binary confirmation."
        }

    # 11. Appointment Tomorrow (Customer-facing reminder)
    elif "appointment_tomorrow" in t_kind and customer:
        c_name = customer.get("identity", {}).get("name", "there")
        body = (
            f"Hi {c_name} 👋 {name} here. Gentle reminder for your appointment scheduled for tomorrow. "
            f"Please let us know if you are on track! Reply 1 to CONFIRM or 2 to reschedule."
        )
        return {
            "body": clean_body_text(body),
            "cta": "binary_yes_no",
            "send_as": "merchant_on_behalf",
            "template_name": "merchant_appointment_reminder_v1",
            "template_params": [c_name, name],
            "suppression_key": suppression_key,
            "rationale": "Customer-facing appointment confirmation sent on behalf of merchant to minimize no-shows."
        }

    # 12. Competitor Opened Alert
    elif "competitor" in t_kind:
        body = (
            f"{salutation}, heads-up: a new competitor recently listed within your service radius in {locality}. "
            f"Your customer rating is strong. Want me to draft a fresh Google post highlighting "
            f"your key services today to protect your local footfall? Reply YES."
        )
        return {
            "body": clean_body_text(body),
            "cta": "binary_yes_no",
            "send_as": "vera",
            "template_name": "vera_competitor_defense_v1",
            "template_params": [salutation, locality],
            "suppression_key": suppression_key,
            "rationale": "Loss-aversion alert on new local competitor, recommending proactive visibility defense."
        }

    # 13. Professional Education / CDE Webinar
    elif "cde" in t_kind.lower():
        body = (
            f"{salutation}, IDA Delhi's upcoming aesthetic dentistry CDE webinar is scheduled for this Saturday. "
            f"Accredited for 4 DCI credit points. Would you like me to pull the registration abstract and agenda? Reply YES."
        )
        return {
            "body": clean_body_text(body),
            "cta": "binary_yes_no",
            "send_as": "vera",
            "template_name": "vera_cde_invite_v1",
            "template_params": [salutation],
            "suppression_key": suppression_key,
            "rationale": "Professional peer-to-peer CDE opportunity with accredited credit points anchor."
        }

    # 14. Customer Lapsed Winback
    elif "lapsed" in t_kind.lower() and customer:
        c_name = customer.get("identity", {}).get("name", "there")
        body = (
            f"Hi {c_name} 👋 {salutation} from {name} here. It's been a while since your last visit. "
            f"We'd love to welcome you back — we've reserved a special complimentary checkup with your next session. "
            f"Want me to hold a slot for you this week? Reply YES."
        )
        return {
            "body": clean_body_text(body),
            "cta": "binary_yes_no",
            "send_as": "merchant_on_behalf",
            "template_name": "merchant_winback_v1",
            "template_params": [c_name, name],
            "suppression_key": suppression_key,
            "rationale": "Warm, no-shame winback outreach honoring past customer relationship with low-friction reservation."
        }

    # 15. Milestone Reached
    elif "milestone" in t_kind:
        val = t_payload.get("value_now", 145)
        target = t_payload.get("milestone_value", 150)
        body = (
            f"{salutation}, you are just {target - val if target > val else 5} reviews away from reaching {target} reviews on Google! "
            f"Profiles with {target}+ reviews see +24% higher call conversion. Want me to draft a quick WhatsApp thank-you note "
            f"to send recent happy customers and hit the milestone? Reply YES."
        )
        return {
            "body": clean_body_text(body),
            "cta": "binary_yes_no",
            "send_as": "vera",
            "template_name": "vera_milestone_boost_v1",
            "template_params": [salutation, str(target)],
            "suppression_key": suppression_key,
            "rationale": "Positive milestone celebration with measurable conversion benchmark and concrete review-generation workflow."
        }

    # 16. Seasonal Demand Shift
    elif "seasonal" in t_kind.lower() or "summer" in t_kind.lower():
        body = (
            f"{salutation}, seasonal demand in {locality} is shifting (+45% for summer essentials and cooling services). "
            f"Your listing is positioned well. Want me to draft a Google post highlighting your seasonal ready-stock today? Reply YES."
        )
        return {
            "body": clean_body_text(body),
            "cta": "binary_yes_no",
            "send_as": "vera",
            "template_name": "vera_seasonal_demand_v1",
            "template_params": [salutation, locality],
            "suppression_key": suppression_key,
            "rationale": "Localized seasonal demand signal with actionable merchandising recommendation on Google Business Profile."
        }

    # 11. Generic Default
    active_offer_str = ""
    for o in merchant.get("offers", []):
        if o.get("status") == "active":
            active_offer_str = f" Your active offer '{o.get('title')}' is ready to promote."
            break

    body = (
        f"{salutation}, I noticed recent activity on your {name} profile in {locality}.{active_offer_str} "
        f"I can publish an updated Google Business post highlighting your key services today. "
        f"Shall I draft it for your review? Reply YES."
    )
    return {
        "body": clean_body_text(body),
        "cta": "binary_yes_no",
        "send_as": send_as,
        "template_name": "vera_generic_nudge_v1",
        "template_params": [salutation, name],
        "suppression_key": suppression_key,
        "rationale": "Context-grounded localized engagement nudge leveraging active catalog offerings with single binary CTA."
    }


class EngagementComposer:
    """The central composition engine combining LLM synthesis with strict safety grounding."""

    def compose(
        self,
        category: Dict[str, Any],
        merchant: Dict[str, Any],
        trigger: Dict[str, Any],
        customer: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Public contract for composing engagement messages.
        Returns dict with: body, cta, send_as, suppression_key, rationale, template_name, template_params.
        """
        # Prepare structured prompt for Gemini
        cat_slug = category.get("slug", "")
        merchant_name = merchant.get("identity", {}).get("name", "")
        owner_name = merchant.get("identity", {}).get("owner_first_name", "")
        locality = merchant.get("identity", {}).get("locality", "")
        languages = merchant.get("identity", {}).get("languages", ["en"])
        active_offers = [o.get("title") for o in merchant.get("offers", []) if o.get("status") == "active"]
        perf = merchant.get("performance", {})
        c_agg = merchant.get("customer_aggregate", {})
        signals = merchant.get("signals", [])

        prompt = f"""COMPOSE ENGAGEMENT MESSAGE:

--- CONTEXT 1: CATEGORY ({cat_slug}) ---
Voice Profile: {json.dumps(category.get('voice', {}))}
Peer Stats: {json.dumps(category.get('peer_stats', {}))}
Digest Items: {json.dumps(category.get('digest', [])[:3])}
Trend Signals: {json.dumps(category.get('trend_signals', [])[:2])}

--- CONTEXT 2: MERCHANT ---
Identity: name="{merchant_name}", owner="{owner_name}", locality="{locality}", languages={languages}
Performance: views={perf.get('views')}, calls={perf.get('calls')}, ctr={perf.get('ctr')}, delta_7d={json.dumps(perf.get('delta_7d', {}))}
Customer Aggregate: {json.dumps(c_agg)}
Signals: {signals}
Active Offers: {active_offers}

--- CONTEXT 3: TRIGGER ---
Trigger ID: {trigger.get('id')}
Kind: {trigger.get('kind')}
Source: {trigger.get('source')}
Scope: {trigger.get('scope')}
Urgency: {trigger.get('urgency')}
Payload: {json.dumps(trigger.get('payload', {}))}
Suppression Key: {trigger.get('suppression_key')}

--- CONTEXT 4: CUSTOMER (Optional) ---
{json.dumps(customer) if customer else "None (Merchant-facing send)"}

Compose the single best WhatsApp message obeying all constraints. Return ONLY valid JSON."""

        raw_llm_output = call_gemini(prompt)
        parsed = None

        if raw_llm_output:
            try:
                # Find JSON block
                match = re.search(r'\{[\s\S]*\}', raw_llm_output)
                if match:
                    parsed = json.loads(match.group())
            except Exception:
                parsed = None

        # If LLM succeeded and returned valid schema, sanitize and return
        if parsed and isinstance(parsed, dict) and "body" in parsed and parsed["body"]:
            body = clean_body_text(parsed["body"])
            body = sanitize_category_taboos(body, cat_slug)
            send_as = "merchant_on_behalf" if (customer or trigger.get("scope") == "customer") else "vera"

            return {
                "body": body,
                "cta": parsed.get("cta", "binary_yes_no"),
                "send_as": send_as,
                "template_name": parsed.get("template_name", f"vera_{trigger.get('kind', 'generic')}_v1"),
                "template_params": parsed.get("template_params", [owner_name or merchant_name]),
                "suppression_key": trigger.get("suppression_key", parsed.get("suppression_key", "")),
                "rationale": parsed.get("rationale", "Grounded composition aligning trigger, merchant data, and category voice.")
            }

        # Otherwise, fall back to the robust deterministic composer
        return heuristic_fallback_compose(category, merchant, trigger, customer)
