import streamlit as st
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from database_files.sqlite_db import sanitize_email, check_empty_db
from dotenv import load_dotenv
from PIL import Image
import time
import os

load_dotenv()

# Setup Session State
if "messages" not in st.session_state:
    st.session_state.messages = []

if not st.session_state.messages:
    first_name = st.session_state['user_info'].get('name', 'User').split()[0]
    st.session_state.messages.append({
        "role": "assistant",
        "content": f"Hi {first_name}, I am Raseed AI. I can analyze your database. Try asking: 'Show me all items in the last invoice'."
    })

# Connect to Local SQLite Database
sanitized_email = sanitize_email(st.session_state['user_info'].get('email'))
invoices_table = f"invoices_{sanitized_email}"
line_items_table = f"line_items_{sanitized_email}"

db = SQLDatabase.from_uri(
    'sqlite:///invoicegpt_db.db',
    include_tables=[invoices_table, line_items_table]
)

img_avatar = Image.open('images/invoicegpt_icon.png')

st.header("Ask Raseed")
st.caption("Powered by Gemini 2.5 Flash | SQL Agent")

# Display History
for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar=img_avatar if message["role"]=="assistant" else None):
        st.markdown(message["content"])

@st.cache_resource(show_spinner=False)
def initialize_agent():
    # --- FIX: Using the model confirmed in your list ---
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash", 
        temperature=0, 
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )
    
    custom_prefix = """You are an expert financial analyst agent designed to interact with a SQL database for Project Raseed.

    CRITICAL INSTRUCTIONS:
    1. When asked for a list of items (e.g., "what did I buy?", "full list"), NEVER use 'LIMIT 1'. Always fetch ALL relevant rows.
    2. If the user asks about the "last receipt" or "last purchase", find the invoice with the most recent 'invoice_date' or highest 'id', and join with line_items to list products.
    3. Always format your final answer as a readable list or summary.
    
    Given an input question, create a syntactically correct SQLite query to run, then look at the results of the query and return the answer.
    """

    agent = create_sql_agent(
        llm=llm,
        db=db,
        agent_type="zero-shot-react-description",
        prefix=custom_prefix,
        verbose=True,
        handle_parsing_errors=True
    )
    return agent

agent = initialize_agent()

def make_output(prompt):
    conversation_history = f"User Question: {prompt}"
    
    try:
        output = agent.invoke({"input": conversation_history})
        return output['output']
    except Exception as e:
        print(f"-------- AGENT ERROR --------\n{e}\n-----------------------------")
        return "I'm having trouble analyzing the data right now. Please try rephrasing."

def modify_output(input_text):
    for text in input_text.split():
        yield text + " "
        time.sleep(0.05)

if prompt := st.chat_input("Ask about your expenses..."):
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.spinner("Raseed is thinking..."):
        response = make_output(prompt)

    with st.chat_message("assistant", avatar=img_avatar):
        st.write_stream(modify_output(response))

    st.session_state.messages.append({"role": "assistant", "content": response})