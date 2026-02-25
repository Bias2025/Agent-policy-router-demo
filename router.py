import re
from typing import Optional, Dict, Any
from schemas import RoutingDecision
from audit import log_event

PRIVILEGED_PATTERNS = [
    r"\breset\b.*\bpassword\b",
    r"\bgrant\b.*\baccess\b",
    r"\bdisable\b.*\baccount\b",
    r"\belevate\b.*\bprivilege\b",
    r"\bcreate\b.*\badmin\b",
]
INFO_PATTERNS = [
    r"\bhow do i\b",
    r"\binstructions\b",
    r"\bpolicy\b",
    r"\bguide\b",
    r"\bdocumentation\b",
    r"\bwhat is\b",
    r"\bwhere can i\b",
]

def classify_intent(prompt: str) -> str:
    p = prompt.lower().strip()
    if any(re.search(ptn, p) for ptn in PRIVILEGED_PATTERNS):
        return "privileged"
    if any(re.search(ptn, p) for ptn in INFO_PATTERNS):
        return "informational"
    # heuristic: operational if it sounds like "do X" but not privileged
    if re.search(r"\b(create|update|change|request|provision|run)\b", p):
        return "operational"
    return "ambiguous"

def risk_from_intent(intent: str) -> str:
    return {
        "informational": "low",
        "operational": "medium",
        "privileged": "high",
        "ambiguous": "medium"
    }[intent]

def orchestrate_route(
    enforcer,
    user_id: str,
    role: str,
    prompt: str,
    ticket_id: Optional[str] = None,
    extras: Optional[Dict[str, Any]] = None
) -> RoutingDecision:
    """
    Orchestrator / Policy Router with Casbin planning gate.
    """
    intent = classify_intent(prompt)
    risk = risk_from_intent(intent)

    # Planning gate: is role allowed to route this intent?
    obj = f"route:intent:{intent}"
    act = "allow"
    allowed = bool(enforcer.enforce(role, obj, act))

    required = []
    explanation = ""
    route_to = "knowledge_agent"
    recommended_tools = "safe_tools"

    if intent == "privileged":
        recommended_tools = "restricted_tools"
        if not ticket_id:
            required.append("ticket_id")

        if not allowed:
            route_to = "human_service_desk"
            explanation = "Privileged request detected. Policy does not permit this role to route privileged actions to automation."
        else:
            # Allowed roles still need prereqs
            if required:
                route_to = "human_service_desk"
                explanation = "Privileged request detected. Role permitted, but prerequisites missing for automated routing."
            else:
                route_to = "action_agent"
                explanation = "Privileged request detected. Role permitted and prerequisites satisfied. Route to Action Agent (execution gate will apply)."

    elif intent == "operational":
        recommended_tools = "safe_tools"
        if not allowed:
            route_to = "human_service_desk"
            explanation = "Operational request detected. Policy does not permit automated handling for this role."
        else:
            route_to = "action_agent"
            explanation = "Operational request detected. Role permitted. Route to Action Agent (execution gate will apply)."

    elif intent == "informational":
        route_to = "knowledge_agent"
        explanation = "Informational request detected. Route to Knowledge Agent / safe tools."

    else:
        route_to = "knowledge_agent"
        explanation = "Intent ambiguous. Start with knowledge lookup / clarification before any action."

    decision = RoutingDecision(
        intent=intent,
        risk_tier=risk,
        route_to=route_to,
        required_prereqs=required,
        recommended_tools=recommended_tools if intent != "ambiguous" else "safe_tools",
        explanation=explanation,
        confidence=0.85 if intent in ("informational", "privileged") else 0.65,
        notes=(None if intent != "ambiguous" else "Ask for target system, desired outcome, and (if privileged) ticket_id."),
        policy_check={
            "policy_obj": obj,
            "policy_act": act,
            "allowed": allowed,
            "role": role
        }
    )

    log_event("routing_decision", {
        "user_id": user_id,
        "role": role,
        "prompt": prompt,
        "ticket_id": ticket_id,
        "intent": intent,
        "risk_tier": risk,
        "route_to": route_to,
        "required_prereqs": required,
        "policy_obj": obj,
        "policy_act": act,
        "allowed": allowed,
        "extras": extras or {}
    })

    return decision
