import json
import streamlit as st
import casbin

from router import orchestrate_route
from tools import execute_tool_with_policy
from audit import tail_events

st.set_page_config(page_title="Policy-Gated Agent Orchestration Demo", layout="centered")

@st.cache_resource
def load_enforcer():
    # File-based Casbin model + policy. Works on Streamlit Cloud.
    return casbin.Enforcer("casbin_model.conf", "policy.csv")

enforcer = load_enforcer()

st.title("Policy-Gated Agent Orchestration (Demo)")
st.caption("Orchestrator routes requests under policy. Action Agent executes tools only through policy-gated wrappers.")

with st.sidebar:
    st.subheader("Identity Context")
    user_id = st.text_input("user_id", value="alice")
    role = st.selectbox("role", ["employee", "it_admin", "service_desk_agent"], index=0)
    ticket_id = st.text_input("ticket_id (optional)", value="")

    st.divider()
    st.subheader("Demo Controls")
    show_audit = st.checkbox("Show audit log", value=True)
    audit_limit = st.slider("Audit log entries", 5, 50, 15)

tabs = st.tabs(["1) Orchestrator / Policy Router", "2) Action Agent (Execution Gate Demo)"])

# -------------------------
# Tab 1: Orchestrator
# -------------------------
with tabs[0]:
    st.subheader("User Request")
    prompt = st.text_area("Enter a request", height=120, value="Reset John's password")

    if st.button("Route Request", type="primary"):
        decision = orchestrate_route(
            enforcer=enforcer,
            user_id=user_id,
            role=role,
            prompt=prompt,
            ticket_id=ticket_id.strip() or None
        )

        st.subheader("Routing Decision (JSON)")
        st.json(json.loads(decision.model_dump_json()))

        st.subheader("Summary")
        st.write(f"**Intent:** {decision.intent}")
        st.write(f"**Risk tier:** {decision.risk_tier}")
        st.write(f"**Route to:** {decision.route_to}")
        if decision.required_prereqs:
            st.write("**Required prerequisites:**")
            for x in decision.required_prereqs:
                st.write(f"- {x}")
        st.write(f"**Recommended tools:** {decision.recommended_tools}")
        st.write(f"**Explanation:** {decision.explanation}")
        st.progress(min(max(decision.confidence, 0.0), 1.0))

# -------------------------
# Tab 2: Action Agent + Execution Gate
# -------------------------
with tabs[1]:
    st.subheader("Action Agent (Mock) — Executes Tools Through Policy Gate")
    st.caption("This simulates the “later” phase: Action Agent + Tool Wrapper + Casbin execution gate + audit log.")

    col1, col2 = st.columns(2)
    with col1:
        tool_name = st.selectbox("Tool", ["get_kb_article", "reset_password"])
    with col2:
        st.write("")

    if tool_name == "get_kb_article":
        query = st.text_input("query", value="VPN setup")
        args = {"query": query}
    else:
        username = st.text_input("username", value="john")
        args = {"username": username}

    # Provide context for audit traceability
    request_context = {
        "ticket_id": ticket_id.strip() or None,
        "demo_note": "Execution gate demo"
    }

    if st.button("Attempt Tool Execution", type="primary"):
        result = execute_tool_with_policy(
            enforcer=enforcer,
            user_id=user_id,
            role=role,
            tool_name=tool_name,
            args=args,
            request_context=request_context
        )

        st.subheader("Execution Result")
        st.json(json.loads(result.model_dump_json()))

        if result.output:
            st.subheader("Tool Output")
            st.code(result.output)

# -------------------------
# Audit log viewer
# -------------------------
if show_audit:
    st.divider()
    st.subheader("Audit Log (Latest)")
    events = tail_events(audit_limit)
    if not events:
        st.info("No audit events yet. Route a request or attempt a tool execution.")
    else:
        for e in reversed(events):
            st.json(e)
