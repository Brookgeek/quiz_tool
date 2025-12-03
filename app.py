import streamlit as st
from st_supabase_connection import SupabaseConnection
import pandas as pd
import requests
import time

# --- CONFIGURATION ---
st.set_page_config(page_title="Pro Quiz Tool", layout="centered")

# --- DATABASE CONNECTION ---
conn = st.connection("supabase", type=SupabaseConnection)

# --- AUTHENTICATION & STATE ---
if 'admin_authenticated' not in st.session_state:
    st.session_state.admin_authenticated = False

# --- HELPER FUNCTIONS ---
def get_game_state():
    response = conn.table("game_state").select("*").execute()
    if not response.data:
        conn.table("game_state").insert({"id": 1, "phase": "LOBBY"}).execute()
        return {"id": 1, "phase": "LOBBY"}
    return response.data[0]

def update_game_state(phase, question_id=None):
    payload = {"phase": phase}
    if question_id is not None:
        payload["current_question_id"] = question_id
    conn.table("game_state").update(payload).eq("id", 1).execute()

def get_current_question(q_id):
    if not q_id: return None
    response = conn.table("questions").select("*").eq("id", q_id).execute()
    return response.data[0] if response.data else None

def get_all_questions():
    response = conn.table("questions").select("*").order("created_at").execute()
    return response.data

def reset_game_data():
    conn.table("quiz_answers").delete().gt("id", 0).execute()
    update_game_state("LOBBY", None)

def nuke_questions():
    conn.table("questions").delete().gt("id", 0).execute()

def fetch_questions_from_github(raw_url):
    try:
        response = requests.get(raw_url)
        if response.status_code != 200:
            return False, "Failed to load URL."
        
        lines = response.text.strip().split('\n')
        count = 0
        
        for line in lines:
            if "|" in line:
                parts = line.split("|")
                # Take the first part as question, the rest as answer (in case answer has pipes)
                q = parts[0].strip()
                a = "|".join(parts[1:]).strip()
                
                if q and a:
                    conn.table("questions").insert({
                        "question_text": q, 
                        "correct_answer": a
                    }).execute()
                    count += 1
        return True, f"Successfully imported {count} questions!"
    except Exception as e:
        return False, str(e)

# --- ADMIN LOGIN SIDEBAR ---
with st.sidebar:
    st.header("🔒 Admin Access")
    if not st.session_state.admin_authenticated:
        pwd = st.text_input("Enter Admin Password", type="password")
        if st.button("Login"):
            # Check password against secrets
            if pwd == st.secrets["admin"]["password"]:
                st.session_state.admin_authenticated = True
                st.success("Access Granted")
                st.rerun()
            else:
                st.error("Wrong Password")
    
    if st.session_state.admin_authenticated:
        if st.button("Logout"):
            st.session_state.admin_authenticated = False
            st.rerun()

# --- MAIN APP ---
state = get_game_state()
phase = state['phase']
current_q_id = state.get('current_question_id')

# ==========================================
# 👑 ADMIN VIEW
# ==========================================
if st.session_state.admin_authenticated:
    st.markdown("---")
    st.subheader("🛠️ Host Control Panel")
    
    # 1. LOBBY: BUILD DECK
    if phase == "LOBBY":
        st.info("Build your deck below.")
        
        tab1, tab2 = st.tabs(["Manual Add", "Import from GitHub"])
        
        with tab1:
            with st.form("add_q"):
                c1, c2 = st.columns([3, 1])
                q_text = c1.text_input("Question")
                a_text = c2.text_input("Real Answer")
                if st.form_submit_button("Add Single Question"):
                    if q_text and a_text:
                        conn.table("questions").insert({
                            "question_text": q_text, 
                            "correct_answer": a_text
                        }).execute()
                        st.success("Added!")
                        st.rerun()

        with tab2:
            st.markdown("Paste the **Raw** GitHub URL of your `.txt` file.")
            st.markdown("Format per line: `Question | Answer`")
            gh_url = st.text_input("GitHub Raw URL")
            if st.button("📥 Load Deck from File"):
                if gh_url:
                    success, msg = fetch_questions_from_github(gh_url)
                    if success:
                        st.success(msg)
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(msg)

        # Show Deck
        questions = get_all_questions()
        if questions:
            st.write(f"**Current Deck ({len(questions)} Questions):**")
            st.dataframe(pd.DataFrame(questions)[['question_text', 'correct_answer']])
            
            col1, col2 = st.columns(2)
            if col1.button("🚀 START GAME (First Question)"):
                first_q = questions[0]
                update_game_state("INPUT", first_q['id'])
                st.rerun()
                
            if col2.button("🗑️ Clear All Questions"):
                nuke_questions()
                st.rerun()

    # 2. GAME LOOP
    elif phase in ["INPUT", "VOTING", "RESULTS"]:
        current_q = get_current_question(current_q_id)
        st.write(f"**Live Question:** {current_q['question_text']}")
        
        c1, c2, c3 = st.columns(3)
        
        if phase == "INPUT":
            st.write("🔴 Users are typing answers...")
            if c2.button("Stop Typing & Start Voting"):
                update_game_state("VOTING")
                st.rerun()
                
        elif phase == "VOTING":
            st.write("🟠 Users are voting...")
            if c3.button("Reveal Results"):
                update_game_state("RESULTS")
                st.rerun()
                
        elif phase == "RESULTS":
            st.write("🟢 Results shown.")
            
            # Find next question
            all_qs = get_all_questions()
            current_index = next((i for i, item in enumerate(all_qs) if item["id"] == current_q_id), -1)
            
            col_next, col_end = st.columns(2)
            if current_index + 1 < len(all_qs):
                next_q = all_qs[current_index + 1]
                if col_next.button(f"⏭️ Next: {next_q['question_text'][:20]}..."):
                    update_game_state("INPUT", next_q['id'])
                    st.rerun()
            else:
                st.success("End of Deck!")
            
            if col_end.button("🏁 End Game"):
                update_game_state("GAME_OVER")
                st.rerun()

    elif phase == "GAME_OVER":
        if st.button("🔄 Start New Game"):
            reset_game_data()
            st.rerun()

# ==========================================
# 👤 PLAYER VIEW
# ==========================================
st.title("🎲 Dynamic Quiz")

if not st.session_state.admin_authenticated:
    if phase == "LOBBY":
        st.info("Waiting for host...")
        if "user_id" not in st.session_state:
            uid = st.text_input("Nickname:")
            if st.button("Join"):
                st.session_state.user_id = uid
                st.rerun()
        else:
            st.success(f"Ready as: **{st.session_state.user_id}**")

    elif phase == "INPUT":
        q_data = get_current_question(current_q_id)
        if q_data:
            st.subheader(f"Q: {q_data['question_text']}")
            if "user_id" in st.session_state:
                ans = st.text_input("Your Bluff:")
                if st.button("Submit"):
                    conn.table("quiz_answers").insert({
                        "user_id": st.session_state.user_id,
                        "question": q_data['question_text'],
                        "answer": ans
                    }).execute()
                    st.success("Sent!")

    elif phase == "VOTING":
        q_data = get_current_question(current_q_id)
        st.subheader(f"Q: {q_data['question_text']}")
        st.info("Look at the main screen to vote!")
        # [Note: You would typically fetch all answers from DB here and show Radio buttons]

    elif phase == "RESULTS":
        q_data = get_current_question(current_q_id)
        st.balloons()
        st.subheader(f"Correct Answer: {q_data['correct_answer']}")

    time.sleep(2)
    st.rerun()
