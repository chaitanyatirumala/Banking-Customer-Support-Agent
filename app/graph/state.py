from typing import TypedDict,Annotated,Optional
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    
    # 1. Conversation History (Context)
    messages : Annotated[list[BaseMessage],add_messages]
    
    # 2. Customer 
    customer_id : str
    
    # 3. Routing & Classification
    intent : Optional[str]
    curr_tier : str
    confidence_score : float
    
    #4. Human Context
    escalation_reason : Optional[str]
    handoff_summary : Optional[str]