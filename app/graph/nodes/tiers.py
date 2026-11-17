from app.graph.state import AgentState
from app.tools.faq_rag import retrieve_faq
from app.tools.crm_db import CRM_TOOLS
from langchain_core.messages import AIMessage,SystemMessage,HumanMessage
from langchain_ollama import ChatOllama
# RAG for FAQ 

def tier_1_rag_node(state:AgentState):
    print("\n[SYSTEM] -> Routing to Tier 1 (FAQ Database)........")
    user_question = state["messages"][-1].content
    relevant_rules = retrieve_faq(user_question)
    llm = ChatOllama(model="llama3.1:8b",temperature = 0.0)
    prompt = (
        "You are a Tier- 1 FAQ customer support assistant.Answer the customer's question"
        "strictly using the company rules below.Keep your answers concise and simple to understand\n\n"
        f"Company_rules:\n{relevant_rules}\n\n"
        f"Customer_Question: {user_question}"
    )

    response = llm.invoke(prompt)
    return {"curr_tier": "tier_1_rag",
            "messages":[AIMessage(content=response.content)]}

# TOol Mapping
TOOL_MAP = {tool.name for tool in CRM_TOOLS}



def tier_2_crm_action(state:AgentState):
    print("\n[SYSTEM] -> Routing to Tier 2 (CRM Tools)........")

    user_query = state['messages'][-1].content
    user_id = state['customer_id']

    llm = ChatOllama(model="llama3.1:8b", temperature=0.0)
    llm_with_tools = llm.bind_tools(CRM_TOOLS)

    messages = [
        SystemMessage(content=(
            f"You are a Tier-2 CRM support agent. The current logged-in customer_id is '{state['customer_id']}'. "
            "Use the provided CRM tools to check account details, order status, or process refunds."
        )),
        HumanMessage(content=user_query)
    ]
    ai_decision = llm_with_tools.invoke(messages)


    ## print the tool calling
    if ai_decision.tool_calls:
        tool_call = ai_decision.tool_calls[0]
        tool_name = tool_call['name']
        tool_args = tool_call['args']

        print(f"[CRM_AGENT]  -> calling tool:{tool_name} with args:{tool_args}")

        selected_tool = TOOL_MAP[tool_name]

        db_result = selected_tool.invoke(tool_args)
        print(f"[CRM DB]    -> Result: {db_result}")
        final_prompt = (
            f"Customer asked: {user_query}\n"
            f"Database returned: {db_result}\n"
            "Write a short, helpful reply to the customer using this exact database result."
        )
        final_reply = llm.invoke(final_prompt)
        reply_text = final_reply.content
    else:
        # If the user didn't provide an order ID or no tool matched, ask for clarification
        reply_text = ai_decision.content or "Could you please provide your Order ID (e.g., ORD-101) so I can check the CRM?"

    return {
        "current_tier": "tier_2_crm",
        "messages": [AIMessage(content=reply_text)]
    }


def tier_3_human_node(state:AgentState):
    print("\n[SYSTEM] -> Routing to Tier 3 (Human Handoff)........")
    return {"curr_tier": "tier_3_human"}