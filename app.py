import streamlit as st
from st_supabase_connection import SupabaseConnection
import pandas as pd

# --- CONFIGURATION ---
st.set_page_config(page_title="Dynamic Quiz Tool", layout="centered")

# --- CONNECT TO SUPABASE ---
# This looks for [connections.supabase] in your secrets
conn = st.connection("supabase", type=SupabaseConnection)

def get_data():
    # Query the table we created. ttl=0 means "don't cache, give me live data"
    response = conn.query("*", table="quiz_answers", ttl=0)
    return response

def save_answer(user_id, question, answer):
    try:
        # Use the underlying client to perform an insert
        conn.client.table("quiz_answers").insert({
            "user_id": user_id,
            "question": question,
            "answer": answer
        }).execute()
        return True
    except Exception as e:
        st.error(f"Error saving data: {e}")
        return False

# --- SESSION STATE ---
if 'phase' not in st.session_state:
    st.session_state.phase = "SETUP"

# --- APP LOGIC ---
st.title("🎲 Live Quiz (Supabase Edition)")

# Simple Admin Toggle
is_admin = st.sidebar.checkbox("Admin Mode")

if is_admin:
    st.sidebar.warning("Admin Panel")
    if st.sidebar.button("Clear All Data (Reset Game)"):
        # Delete all rows where id is greater than 0
        conn.client.table("quiz_answers").delete().gt("id", 0).execute()
        st.success("Database Wiped!")

# User Interface
user_id = st.text_input("Enter your Nickname to Join:")

if user_id:
    st.markdown("---")
    st.write(f"Welcome, **{user_id}**!")
    
    # 1. READ LIVE DATA
    data = get_data()
    
    # Show current answers (Hidden in real game, shown here for testing)
    with st.expander("Debug: View Database"):
        st.dataframe(data)

    question = "What is the best programming language?" 
    st.subheader(f"Q: {question}")
    
    answer_input = st.text_input("Your Answer:")
    
    if st.button("Submit Answer"):
        if answer_input:
            save_answer(user_id, question, answer_input)
            st.success("Answer saved to Database!")
            st.rerun() # Refresh to see your name in the debug list
        else:
            st.warning("Please type an answer.")
