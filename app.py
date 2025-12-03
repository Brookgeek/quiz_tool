import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random

# --- CONFIGURATION ---
st.set_page_config(page_title="Dynamic Quiz Tool", layout="centered")

# --- CONNECT TO GOOGLE SHEET ---
conn = st.connection("gsheets", type=GSheetsConnection)

def get_data():
    # Reads the sheet; ttl=0 ensures we don't cache old data
    return conn.read(worksheet="Sheet1", ttl=0)

def save_answer(user_id, question, answer):
    try:
        df = get_data()
        new_row = pd.DataFrame([{
            "User_ID": user_id, 
            "Question": question, 
            "Answer": answer
        }])
        updated_df = pd.concat([df, new_row], ignore_index=True)
        conn.update(worksheet="Sheet1", data=updated_df)
        return True
    except Exception as e:
        st.error(f"Error saving data: {e}")
        return False

# --- SESSION STATE ---
if 'phase' not in st.session_state:
    st.session_state.phase = "SETUP"

# --- APP LOGIC ---
st.title("🎲 Live Quiz Tool")

# Simple Admin Toggle
is_admin = st.sidebar.checkbox("Admin Mode")

if is_admin:
    st.sidebar.warning("Admin Panel")
    if st.sidebar.button("Clear All Data (Reset Game)"):
        # Create empty dataframe with headers to reset sheet
        empty_df = pd.DataFrame(columns=["User_ID", "Question", "Answer"])
        conn.update(worksheet="Sheet1", data=empty_df)
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

    question = "What is the best programming language?" # You can make this dynamic later
    st.subheader(f"Q: {question}")
    
    answer_input = st.text_input("Your Answer:")
    
    if st.button("Submit Answer"):
        if answer_input:
            save_answer(user_id, question, answer_input)
            st.success("Answer sent to Google Drive!")
        else:
            st.warning("Please type an answer.")