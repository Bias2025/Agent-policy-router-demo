from pydantic import BaseModel, Field
from typing import List, Literal, Optional

Intent = Literal["informational", "operational", "privileged", "ambiguous"]
RiskTier = Literal["low", "medium", "high"]
RouteTo = Literal["knowledge_agent", "action_agent", "human_service_desk"]
ToolClass = Literal["none", "safe_tools", "restricted_tools"]

class PolicyCheck(BaseModel):
    policy_obj: str
    policy_act: str
    allowed: bool
    role: str

class RoutingDecision(BaseModel):
    intent: Intent
    risk_tier: RiskTier
    route_to: RouteTo
    required_prereqs: List[str] = Field(default_factory=list)
    recommended_tools: ToolClass = "none"
    explanation: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.75)
    policy_check: PolicyCheck
