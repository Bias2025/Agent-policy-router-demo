```python
# graph.py
from typing import TypedDict, Optional, Dict, Any, List, Literal

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
from langchain_core.tools import tool

from schemas import RoutingDecision, ActionResult  # assumes schemas.py updated with PolicyCheck model
from tools import execute_tool_with_policy
from audit import log_event


class DemoState(TypedDict, total=False):
    user_id: str
    role: str
    ticket_id: Optional[str]
    prompt: str

    routing: RoutingDecision
    action_result: Optional[ActionResult]
    messages: List[Any]  # LangChain message objects for the action agent loop


def build_tools(enforcer, user_id: str, role: str, ticket_id: Optional[str]):
    """
    Returns LangChain tools that are policy-gated via execute_tool_with_policy.
    """

    @tool
    def get_kb_article(query: str) -> str:
        """Search the knowledge base for relevant articles."""
        res = execute_tool_with_policy(
            enforcer=enforcer,
            user_id=user_id,
            role=role,
            tool_name="get_kb_article",
            args={"query": query},
            request_context={"ticket_id": ticket_id},
        )
        if res.decision == "deny":
            return f"DENIED: {res.reason}"
        return res.output or ""

    @tool
    def reset_password(username: str) -> str:
        """Reset a user's password (privileged)."""
        res = execute_tool_with_policy(
            enforcer=enforcer,
            user_id=user_id,
            role=role,
            tool_name="reset_password",
            args={"username": username},
            request_context={"ticket_id": ticket_id},
        )
        if res.decision == "deny":
            return f"DENIED: {res.reason}"
        return res.output or ""

    return [get_kb_article, reset_password]


def orchestrator_node(enforcer, model_name: str = "gpt-4o-mini"):
    """
    LLM proposes a RoutingDecision (structured output). Then we apply Casbin planning gate
    and attach a strict PolicyCheck object (no free-form dicts).
    """
    llm = ChatOpenAI(model=model_name, temperature=0).with_structured_output(RoutingDecision)

    system_instructions = (
        "You are an enterprise Orchestrator / Policy Router for an IT organization.\n"
        "Classify the request into intent = informational | operational | privileged | ambiguous.\n"
        "Choose route_to:\n"
        "- knowledge_agent for safe informational queries,\n"
        "- action_agent when automation is appropriate,\n"
        "- human_service_desk when privileged or prerequisites/permissions are missing.\n"
        "Set risk_tier low/medium/high.\n"
        "If privileged and ticket_id is missing, include required_prereqs=['ticket_id'].\n"
        "Keep explanation short and audit-friendly.\n"
        "IMPORTANT: policy_check is NOT for you to decide; it will be filled by the system.\n"
    )

    def _node(state: DemoState) -> Dict[str, Any]:
        user_id = state["user_id"]
        role = state["role"]
        prompt = state["prompt"]
        ticket_id = state.get("ticket_id") or None

        # Get a proposed routing decision from the LLM.
        # NOTE: RoutingDecision schema must include policy_check as a strict object model (PolicyCheck),
        # but the model should not invent it. We'll overwrite it.
        proposed: RoutingDecision = llm.invoke(
            [HumanMessage(content=system_instructions + "\nUSER REQUEST:\n" + prompt)]
        )

        # Planning gate: can this role route this intent?
        obj = f"route:intent:{proposed.intent}"
        act = "allow"
        allowed = bool(enforcer.enforce(role, obj, act))

        # Enforce prerequisites for privileged requests
        required = list(proposed.required_prereqs or [])
        if proposed.intent == "privileged" and not ticket_id and "ticket_id" not in required:
            required.append("ticket_id")

        # Apply policy: if not allowed, force human route; if prereqs missing, force human route.
        route_to = proposed.route_to
        explanation = proposed.explanation

        if proposed.intent == "privileged":
            if not allowed:
                route_to = "human_service_desk"
                explanation = "Privileged request: policy does not allow automated routing for this role."
            elif required:
                route_to = "human_service_desk"
                explanation = "Privileged request: prerequisites required before automation."
            else:
                route_to = "action_agent"

        elif proposed.intent == "operational":
            # Optional: you can also require allowed=True for operational routing
            if not allowed:
                route_to = "human_service_desk"
                explanation = "Operational request: policy does not allow automated routing for this role."
            else:
                route_to = "action_agent"

        elif proposed.intent == "informational":
            route_to = "knowledge_agent"

        else:
            route_to = "knowledge_agent"
            explanation = "Intent ambiguous. Start with clarification / knowledge lookup before any action."

        # Build final RoutingDecision, overwriting policy_check with strict fields (PolicyCheck model).
        # This avoids OpenAI structured-output schema issues caused by Dict[str, Any].
        final = RoutingDecision(
            intent=proposed.intent,
            risk_tier=proposed.risk_tier,
            route_to=route_to,
            required_prereqs=required,
            recommended_tools=proposed.recommended_tools,
            explanation=explanation,
            confidence=proposed.confidence,
            policy_check={
                "policy_obj": obj,
                "policy_act": act,
                "allowed": allowed,
                "role": role,
            },
        )

        log_event(
            "routing_decision",
            {
                "user_id": user_id,
                "role": role,
                "prompt": prompt,
                "ticket_id": ticket_id,
                "routing": final.model_dump(),
            },
        )

        # Initialize action-agent messages
        return {
            "routing": final,
            "messages": [HumanMessage(content=prompt)],
            "action_result": None,
        }

    return _node


def should_run_action_agent(state: DemoState) -> Literal["run", "skip"]:
    routing = state.get("routing")
    if routing and routing.route_to == "action_agent":
        return "run"
    return "skip"


def action_agent_node(enforcer, model_name: str = "gpt-4o-mini", max_tool_loops: int = 2):
    """
    Tool-calling action agent:
    - LLM decides tool call(s)
    - tools run through execution gate (Casbin)
    - tool outputs fed back to agent
    """
    def _node(state: DemoState) -> Dict[str, Any]:
        user_id = state["user_id"]
        role = state["role"]
        ticket_id = state.get("ticket_id") or None

        tools = build_tools(enforcer, user_id=user_id, role=role, ticket_id=ticket_id)
        llm = ChatOpenAI(model=model_name, temperature=0).bind_tools(tools)

        messages = state.get("messages", [])
        last_tool_used = ""
        last_args: Dict[str, Any] = {}
        last_output = ""
        decision = "deny"
        reason = "No tool executed."

        for _ in range(max_tool_loops):
            ai: AIMessage = llm.invoke(messages)
            messages.append(ai)

            tool_calls = getattr(ai, "tool_calls", None) or []
            if not tool_calls:
                break

            # Execute first tool call for demo simplicity
            call = tool_calls[0]
            tool_name = call["name"]
            tool_args = call.get("args", {}) or {}

            tool_fn = next((t for t in tools if t.name == tool_name), None)
            if tool_fn is None:
                out = f"Tool '{tool_name}' not found."
            else:
                out = tool_fn.invoke(tool_args)

            last_tool_used = tool_name
            last_args = tool_args
            last_output = str(out)

            if isinstance(out, str) and out.startswith("DENIED:"):
                decision = "deny"
                reason = out.replace("DENIED:", "").strip()
            else:
                decision = "allow"
                reason = "Tool executed (policy-gated)."

            messages.append(ToolMessage(content=str(out), tool_call_id=call["id"]))
            break

        action_result = ActionResult(
            executed=(decision == "allow"),
            tool=last_tool_used or "none",
            args=last_args,
            decision=decision,  # type: ignore
            reason=reason,
            output=(last_output if last_output else None),
        )

        log_event(
            "action_agent",
            {
                "user_id": user_id,
                "role": role,
                "ticket_id": ticket_id,
                "action_result": action_result.model_dump(),
            },
        )

        return {"action_result": action_result, "messages": messages}

    return _node


def build_graph(enforcer, model_name: str = "gpt-4o-mini"):
    g = StateGraph(DemoState)

    g.add_node("orchestrator", orchestrator_node(enforcer, model_name=model_name))
    g.add_node("action_agent", action_agent_node(enforcer, model_name=model_name))

    g.set_entry_point("orchestrator")

    g.add_conditional_edges(
        "orchestrator",
        should_run_action_agent,
        {"run": "action_agent", "skip": END},
    )

    g.add_edge("action_agent", END)

    return g.compile()
```
