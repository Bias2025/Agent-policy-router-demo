import os
import json
import streamlit as st
import casbin

from graph import build_graph
from audit import tail_events

st.write("Key exists:", bool(os.getenv("OPENAI_API_KEY")))
st.set_page_config(page_title="LangGraph Policy-Gated Orchestration Demo", layout="centered")

@st.cache_resource
def load_enforcer():
    return casbin.Enforcer("casbin_model.conf", "policy.csv")

@st.cache_resource
def load_graph(_enforcer, model_name: str):
    return build_graph(_enforcer, model_name=model_name)

enforcer = load_enforcer()

st.title("LangGraph + OpenAI: Policy-Gated Agent Orchestration (Demo)")
st.caption("LangGraph orchestrates Orchestrator → (optional) Action Agent. Casbin gates both planning and tool execution.")

with st.sidebar:
    st.subheader("Identity Context")
    user_id = st.text_input("user_id", value="alice")
    role = st.selectbox("role", ["employee", "it_admin", "service_desk_agent"], index=0)
    ticket_id = st.text_input("ticket_id (optional)", value="")

    st.divider()
    st.subheader("Model")
    model_name = st.text_input("OpenAI model", value="gpt-4o-mini")

    st.divider()
    show_audit = st.checkbox("Show audit log", value=True)
    audit_limit = st.slider("Audit log entries", 5, 50, 15)

# Streamlit Cloud: set OPENAI_API_KEY in Secrets
if not os.getenv("OPENAI_API_KEY"):
    st.warning("OPENAI_API_KEY is not set. Add it in Streamlit Cloud → App settings → Secrets.")
    st.stop()

graph = load_graph(enforcer, model_name=model_name)

st.subheader("User Request")
prompt = st.text_area("Enter a request", height=120, value="Reset John's password")

if st.button("Run Orchestration", type="primary"):
    state_in = {
        "user_id": user_id.strip(),
        "role": role,
        "ticket_id": (ticket_id.strip() or None),
        "prompt": prompt.strip(),
    }

    out = graph.invoke(state_in)

    routing = out.get("routing")
    action_result = out.get("action_result")

    st.subheader("Routing Decision")
    st.json(routing.model_dump() if routing else {"error": "No routing decision"})

    if action_result:
        st.subheader("Action Agent Result")
        st.json(action_result.model_dump())
        if action_result.output:
            st.subheader("Tool Output")
            st.code(action_result.output)
    else:
        st.info("Action Agent did not run (routed to knowledge_agent or human_service_desk).")

if show_audit:
    st.divider()
    st.subheader("Audit Log (Latest)")
    events = tail_events(audit_limit)
    if not events:
        st.info("No audit events yet.")
    else:
        for e in reversed(events):
            st.json(e)
