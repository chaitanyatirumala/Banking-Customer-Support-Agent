from langgraph.graph import StateGraph,START,END
from app.graph.state import AgentState
from app.graph.nodes.intent_classifier import IntentClassifier,classify_intent_node
from app.graph.nodes.tiers import tier_1_rag_node,tier_2_crm_action,tier_3_human_node
from app.graph.edges import route_intent

graph = StateGraph(AgentState)

#Add Nodes
graph.add_node("classifier",classify_intent_node)
graph.add_node("tier-1",tier_1_rag_node)
graph.add_node("tier-2",tier_2_crm_action)
graph.add_node("tier-3",tier_3_human_node)

# Add Edges
graph.add_edge(START,"classifier")
# Add conditional Edges
graph.add_conditional_edges(
    "classifier",
    route_intent,{
    "tier-1_faq"       : "tier-1",
    "tier-2_crm_action": "tier-2",
    "tier-3_human_escalation": "tier-3"
    }
)

# Add closing edges

graph.add_edge("tier-1",END)
graph.add_edge("tier-2",END)
graph.add_edge("tier-3",END)

workflow = graph.compile()