from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict


# ----------------------------
# ENUM TYPES
# ----------------------------

Intent = Literal["informational", "operational", "privileged", "ambiguous"]
RiskTier = Literal["low", "medium", "high"]
RouteTo = Literal["knowledge_agent", "action_agent", "human_service_desk"]
ToolClass = Literal["none", "safe_tools", "restricted_tools"]
DecisionType = Literal["allow", "deny"]


# ----------------------------
# POLICY CHECK (STRICT OBJECT)
# ----------------------------

class PolicyCheck(BaseModel):
    policy_obj: str
    policy_act: str
    allowed: bool
    role: str

    class Config:
        extra = "forbid"  # prevents additionalProperties issues


# ----------------------------
# ROUTING DECISION
# ----------------------------

class RoutingDecision(BaseModel):
    intent: Intent
    risk_tier: RiskTier
    route_to: RouteTo
    required_prereqs: List[str] = Field(default_factory=list)
    recommended_tools: ToolClass = "none"
    explanation: str
    confidence: float = Field(ge=0.0, le=1.0)
    policy_check: PolicyCheck

    class Config:
        extra = "forbid"  # strict schema for OpenAI structured output


# ----------------------------
# ACTION AGENT RESULT
# ----------------------------

class ActionResult(BaseModel):
    executed: bool
    tool: str
    args: Dict[str, str] = Field(default_factory=dict)
    decision: DecisionType
    reason: str
    output: Optional[str] = None

    class Config:
        extra = "forbid"
