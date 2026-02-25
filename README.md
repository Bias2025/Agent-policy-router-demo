

# LangGraph Policy-Gated Orchestration 

## What it is
- LangGraph orchestrates an Orchestrator node and (optionally) an Action Agent node.
- Orchestrator uses OpenAI (via langchain-openai) to produce a structured RoutingDecision.
- Casbin enforces:
  1) planning gate (routing permissions)
  2) execution gate (tool permissions)
- Audit logs are written to audit_log.jsonl.

## Run locally
export OPENAI_API_KEY="..."
pip install -r requirements.txt
streamlit run app.py

## Deploy to Streamlit Cloud
- Push repo to GitHub
- Create Streamlit app from repo
- Add secret:
  OPENAI_API_KEY = "..."



