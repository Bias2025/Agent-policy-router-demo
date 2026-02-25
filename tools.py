from typing import Any, Dict, Optional
from schemas import ActionResult
from audit import log_event

def get_kb_article(query: str) -> str:
    # Mock: replace with real KB lookup later
    return f"KB Article Results for '{query}':\n- VPN Setup Guide\n- MFA Troubleshooting\n- Remote Access Policy"

def reset_password(username: str) -> str:
    # Mock: replace with ServiceNow / IAM action later
    return f"Password reset initiated for user '{username}'. (Mock execution)"

def execute_tool_with_policy(
    enforcer,
    user_id: str,
    role: str,
    tool_name: str,
    args: Dict[str, Any],
    request_context: Optional[Dict[str, Any]] = None
) -> ActionResult:
    """
    Execution gate: Tool Wrapper -> Casbin -> Execute/Deny -> Log
    """
    obj = f"tool:{tool_name}"
    act = "execute"

    allowed = bool(enforcer.enforce(role, obj, act))

    base_log = {
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
        log_event("tool_execution", {**base_log, "decision": "deny"})
        return ActionResult(
            executed=False,
            tool=tool_name,
            args=args,
            decision="deny",
            reason="Policy denied tool execution."
        )

    # Execute allowed tools
    try:
        if tool_name == "get_kb_article":
            output = get_kb_article(**args)
        elif tool_name == "reset_password":
            output = reset_password(**args)
        else:
            output = f"Unknown tool '{tool_name}'."

        log_event("tool_execution", {**base_log, "decision": "allow", "output_summary": output[:200]})
        return ActionResult(
            executed=True,
            tool=tool_name,
            args=args,
            decision="allow",
            reason="Policy allowed tool execution.",
            output=output
        )

    except Exception as e:
        log_event("tool_execution", {**base_log, "decision": "allow", "error": str(e)})
        return ActionResult(
            executed=False,
            tool=tool_name,
            args=args,
            decision="allow",
            reason=f"Tool execution failed: {e}",
            output=None
        )
