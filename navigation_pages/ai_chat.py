import streamlit as st
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from database_files.sqlite_db import sanitize_email
from dotenv import load_dotenv
from PIL import Image
import time
import os

load_dotenv()

# --- SETUP HEADER ---
st.header("Ask Raseed")
st.caption("Your Personal Financial Aide • Powered by Gemini Agent")

# Setup Session State for Chat History
if "messages" not in st.session_state:
    st.session_state.messages = []

# Initial Greeting (Only once)
if not st.session_state.messages:
    user_name = st.session_state['user_info'].get('name', 'User').split()[0]
    welcome_msg = f"Hi {user_name}! I've analyzed your receipts. Ask me about your spending habits, recent purchases, or inventory."
    st.session_state.messages.append({"role": "assistant", "content": welcome_msg})

# --- CONNECT TO DATABASE ---
try:
    user_email = st.session_state['user_info'].get('email')
    sanitized_email = sanitize_email(user_email)
    
    # We dynamically select ONLY the user's tables to keep data safe/focused
    db = SQLDatabase.from_uri(
        'sqlite:///invoicegpt_db.db',
        include_tables=[f"invoices_{sanitized_email}", f"line_items_{sanitized_email}"]
    )
except Exception as e:
    st.error(f"Database Connection Error: {e}")
    st.stop()

# --- INITIALIZE AGENT ---
@st.cache_resource
def get_agent():
    # 1. Setup Gemini
    llm = ChatGoogleGenerativeAI(
        model="gemini-flash-latest",
        temperature=0,
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        convert_system_message_to_human=True
    )

    # 2. Define the "Brain" (System Prompt)
    prefix = f"""
    You are 'Raseed', an expert home finance assistant. 
    You are querying a SQL database of receipts for user: {user_email}.

    DATABASE SCHEMA:
    - invoices_{sanitized_email}: Contains summary data (merchant, date, total, category).
    - line_items_{sanitized_email}: Contains specific products purchased (milk, bread, etc.).

    CRITICAL INSTRUCTIONS:
    1. **Categorization:** If asked about "Groceries" or "Dining", query the 'category' column.
    2. **Inventory:** If asked "Do I have X?", check 'line_items' for recent purchases of X.
    3. **Format:** ALWAYS end your response with "Final Answer: [Your response here]".
    4. **Privacy:** Never reveal data from other tables/users.
    
    If you get a parsing error, just output the answer naturally.
    """

    # 3. Create Agent with Error Handling
    return create_sql_agent(
        llm=llm,
        db=db,
        agent_type="zero-shot-react-description",
        prefix=prefix,
        verbose=True,
        # CRITICAL FIX: This tells the agent how to handle "chatty" responses
        agent_executor_kwargs={
            "handle_parsing_errors": True 
        }
    )

agent = get_agent()
# --- CHAT INTERFACE ---
# Display history
for msg in st.session_state.messages:
    # Use different avatars for user vs assistant
    avatar = "images/invoicegpt_icon.png" if msg["role"] == "assistant" else None
    if msg["role"] == "assistant" and not os.path.exists(avatar): avatar = "🤖" # Fallback
    
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# Handle User Input
if prompt := st.chat_input("Ex: 'How much did I spend on Dining this month?'"):
    # 1. Show User Message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Generate Response
    with st.chat_message("assistant", avatar="images/invoicegpt_icon.png"):
        with st.spinner("Raseed is thinking..."):
            try:
                # Prepare context
                response = agent.invoke({"input": prompt})
                output_text = response['output']
                
                # Simulate typing effect
                message_placeholder = st.empty()
                full_response = ""
                for chunk in output_text.split():
                    full_response += chunk + " "
                    time.sleep(0.05)
                    message_placeholder.markdown(full_response + "▌")
                message_placeholder.markdown(full_response)
                
                # Save to history
                st.session_state.messages.append({"role": "assistant", "content": full_response})
                
            except Exception as e:
                st.error("I ran into an issue analyzing that. Please try rephrasing.")
                print(f"Agent Error: {e}")