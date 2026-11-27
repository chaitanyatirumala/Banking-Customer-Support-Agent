from langgraph.graph import END, START, StateGraph
from app.graph.edges import route_after_tier_2, route_intent
from app.graph.nodes.intent_classifier import classify_intent_node
from app.graph.nodes.tiers import (
    tier_1_rag_node,
    tier_2_crm_action,
    tier_3_human_node,
)
from app.graph.state import AgentState

graph = StateGraph(AgentState)

# Add Nodes
graph.add_node("classifier", classify_intent_node)
graph.add_node("tier-1", tier_1_rag_node)
graph.add_node("tier-2", tier_2_crm_action)
graph.add_node("tier-3", tier_3_human_node)

# Entry -> Classifier
graph.add_edge(START, "classifier")

# Classifier -> Tier-1 / Tier-2 / Tier-3
graph.add_conditional_edges(
    "classifier",
    route_intent,
    {
        "tier-1_faq": "tier-1",
        "tier-2_crm_action": "tier-2",
        "tier-3_human_escalation": "tier-3",
    },
)

# Tier-2 -> Either END (resolved) OR Tier-3 (guardrail escalated)
graph.add_conditional_edges(
    "tier-2",
    route_after_tier_2,
    {
        "tier-3_human_escalation": "tier-3",
        "end": END,
    },
)

# Closing edges
graph.add_edge("tier-1", END)
graph.add_edge("tier-3", END)

workflow = graph.compile()