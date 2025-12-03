import streamlit as st
from st_supabase_connection import SupabaseConnection
import pandas as pd
import time

# --- CONFIGURATION ---
st.set_page_config(page_title="Live Quiz", layout="centered")

# --- DATABASE CONNECTION ---
conn = st.connection("supabase", type=SupabaseConnection)

# --- HELPER FUNCTIONS ---
def get_game_state():
    # Fetch the single row that controls the game for everyone
    return conn.query("*", table="game_state", ttl=0).data[0]

def get_current_question(q_id):
    if not q_id: return None
    return conn.query("*", table="questions", ttl=0).eq("id", q_id).data[0]

def update_game_state(phase, question_id=None):
    data = {"phase": phase}
    if question_id:
        data["current_question_id"] = question_id
    conn.client.table("game_state").update(data).eq("id", 1).execute()

def add_new_question(q_text, a_text):
    conn.client.table("questions").insert({
        "question_text": q_text, 
        "correct_answer": a_text
    }).execute()

# --- MAIN APP LOGIC ---
st.title("🎲 Dynamic Quiz")

# 1. ADMIN PANEL (Sidebar)
with st.sidebar:
    st.header("👮 Admin Control")
    is_admin = st.toggle("Enable Admin Mode")
    
    if is_admin:
        st.markdown("---")
        st.subheader("1. Add New Question")
        with st.form("add_q_form"):
            new_q = st.text_input("Question Text")
            new_a = st.text_input("Correct Answer")
            if st.form_submit_button("Save to Bank"):
                add_new_question(new_q, new_a)
                st.success("Saved!")

        st.markdown("---")
        st.subheader("2. Control Game")
        
        # Fetch all available questions for the dropdown
        all_qs = conn.query("*", table="questions", ttl=0).data
        q_options = {q['id']: f"{q['question_text']} ({q['correct_answer']})" for q in all_qs}
        
        selected_q_id = st.selectbox("Pick Active Question", options=list(q_options.keys()), format_func=lambda x: q_options[x])
        
        col1, col2 = st.columns(2)
        if col1.button("▶ START (Input)"):
            update_game_state("INPUT", selected_q_id)
            # Also clear old answers for this question if you want (optional)
        
        if col2.button("📊 VOTING"):
            update_game_state("VOTING")
            
        if st.button("🏆 RESULTS"):
            update_game_state("RESULTS")
            
        if st.button("⏹ RESET (Setup)"):
            update_game_state("SETUP")

# 2. PLAYER VIEW (Updates automatically based on DB)
state = get_game_state()
phase = state['phase']
current_q_id = state['current_question_id']

# Get the actual text of the current question
question_data = get_current_question(current_q_id) if current_q_id else None

st.write(f"**Status:** {phase}")

if phase == "SETUP":
    st.info("Waiting for host to start the next round...")
    st.image("https://media.giphy.com/media/l0HlBO7eyXzSZkJri/giphy.gif") # Optional waiting GIF

elif phase == "INPUT":
    if question_data:
        st.subheader(f"Q: {question_data['question_text']}")
        u_answer = st.text_input("Your Bluff Answer:")
        if st.button("Submit"):
            # Reuse your save logic from before here
            conn.client.table("quiz_answers").insert({
                "user_id": st.session_state.get("user_id", "Anon"),
                "question": question_data['question_text'],
                "answer": u_answer
            }).execute()
            st.success("Sent!")

elif phase == "VOTING":
    st.subheader(f"Q: {question_data['question_text']}")
    st.write("Voting is open! (Logic to show options goes here)")
    # Logic to fetch user answers and show radio buttons

elif phase == "RESULTS":
    st.balloons()
    st.subheader(f"The correct answer was: {question_data['correct_answer']}")
    # Logic to show scoreboard

# Auto-refresh helper for users so they don't have to hit F5
time.sleep(2)
st.rerun()
