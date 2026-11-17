import os
from langchain_core.messages import HumanMessage,SystemMessage
from app.graph.workflow import workflow
def run_test():
    test_message = "The delivery is expected to deliver in 10 days but the seller is located within 100km from me."
    print(f"Customer : {test_message}")
    initial_state = {
        "messages" :[HumanMessage(content=test_message)],
        
        "customer_id" :"CUST-001",

        "intent":None,
        "curr_tier": "unassigned",
        "confidence_score":None,
        "escalation_reason":None,
        "handoff_summary":None 
    }
    final_state = workflow.invoke(initial_state)
    print("Classification Results:")
    print(f"Intent: {final_state['intent']}")
    print(f"Current Tier: {final_state['curr_tier']}")
    print(f"Confidence Score: {final_state['confidence_score']}")
    print(f"Escalation Reason: {final_state['escalation_reason']}")
    print(f"Handoff Summary: {final_state['handoff_summary']}")

if __name__ == "__main__":
    run_test()