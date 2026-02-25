from typing import Any, Dict, Optional
from schemas import ActionResult
from audit import log_event

# --- Mock tool implementations (safe for demo) ---
def get_kb_article_impl(query: str) -> str:
    return (
        f"KB Results for '{query}':\n"
        f"- VPN Setup Guide\n"
        f"- MFA Troubleshooting\n"
        f"- Remote Access Policy"
    )

def reset_password_impl(username: str) -> str:
    return f"Password reset initiated for user '{username}'. (Mock execution)"

# --- Execution gate wrapper ---
def execute_tool_with_policy(
    enforcer,
    user_id: str,
    role: str,
    tool_name: str,
    args: Dict[str, Any],
    request_context: Optional[Dict[str, Any]] = None,
) -> ActionResult:
    obj = f"tool:{tool_name}"
    act = "execute"
    allowed = bool(enforcer.enforce(role, obj, act))

    base = {
        "user_id": user_id,
        "role": role,
        "tool": tool_name,
        "args": args,
        "policy_obj": obj,
        "policy_act": act,
        "allowed": allowed,
        "request_context": request_context or {},
    }

    if not allowed:
        log_event("tool_execution", {**base, "decision": "deny"})
        return ActionResult(
            executed=False,
            tool=tool_name,
            args=args,
            decision="deny",
            reason="Policy denied tool execution.",
        )

    try:
        if tool_name == "get_kb_article":
            output = get_kb_article_impl(**args)
        elif tool_name == "reset_password":
            output = reset_password_impl(**args)
        else:
            output = f"Unknown tool '{tool_name}'."

        log_event("tool_execution", {**base, "decision": "allow", "output_summary": output[:200]})
        return ActionResult(
            executed=True,
            tool=tool_name,
            args=args,
            decision="allow",
            reason="Policy allowed tool execution.",
            output=output,
        )
    except Exception as e:
        log_event("tool_execution", {**base, "decision": "allow", "error": str(e)})
        return ActionResult(
            executed=False,
            tool=tool_name,
            args=args,
            decision="allow",
            reason=f"Tool execution failed: {e}",
        )
