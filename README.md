# Policy-Gated Agent Orchestration 

## What it shows
1) Orchestrator / Policy Router:
- classifies intent (informational/operational/privileged/ambiguous)
- checks Casbin policy to decide routing
- emits structured routing decision + audit log

2) Action Agent (Mock execution):
- attempts tool execution through Tool Wrapper
- Casbin enforces allow/deny (execution gate)
- logs every attempt (audit)

## Run locally
pip install -r requirements.txt
streamlit run app.py

## Deploy on Streamlit Cloud
- Push repo to GitHub
- Create Streamlit Cloud app pointing to app.py
