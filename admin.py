def load_questions_from_github(url):
    try:
        resp = requests.get(url)
        if resp.status_code != 200: 
            return False
        
        # FIX: Force correct decoding or ignore bad characters
        resp.encoding = 'utf-8' 
        content = resp.text
        
        # If that failed, try decoding bytes manually ignoring errors
        if not content:
            content = resp.content.decode('utf-8', errors='ignore')

        lines = content.strip().split('\n')
        count = 0
        for line in lines:
            if "|" in line:
                # specific split to avoid issues if answer has pipes
                parts = line.split("|")
                q = parts[0].strip()
                # Join the rest in case the answer itself contains a pipe
                a = "|".join(parts[1:]).strip()
                
                if q and a:
                    conn.table("questions").insert({
                        "question_text": q, 
                        "correct_answer": a
                    }).execute()
                    count += 1
        return count
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return False

import streamlit as st
from st_supabase_connection import SupabaseConnection
import requests
import time
import pandas as pd

st.set_page_config(page_title="Admin Controller", layout="wide")
conn = st.connection("supabase", type=SupabaseConnection)

# ==========================================
# 🛡️ SAFETY LAYER (Prevents Network Crashes)
# ==========================================
def run_safe(operation):
    try:
        return operation()
    except Exception:
        time.sleep(1)
        try:
            return operation()
        except Exception:
            return None

# ==========================================
# 🧠 HELPER FUNCTIONS
# ==========================================
def get_state():
    def op():
        return conn.table("game_state").select("*").eq("id", 1).execute().data[0]
    return run_safe(op)

def update_state(updates):
    def op():
        conn.table("game_state").update(updates).eq("id", 1).execute()
        return True
    run_safe(op)

def get_current_question(q_id):
    if not q_id: return None
    def op():
        return conn.table("questions").select("*").eq("id", q_id).execute().data[0]
    return run_safe(op)

def nuke_data():
    def op():
        # Delete children first, then parent
        conn.table("game_state").update({"current_question_id": None, "phase": "LOBBY", "total_players": 0}).eq("id", 1).execute()
        conn.table("player_votes").delete().gt("id", 0).execute()
        conn.table("player_inputs").delete().gt("id", 0).execute()
        conn.table("questions").delete().gt("id", 0).execute()
        return True
    run_safe(op)

def load_questions_from_github(url):
    try:
        resp = requests.get(url)
        resp.encoding = 'utf-8'
        content = resp.text
        if not content: return False
        
        lines = content.strip().split('\n')
        count = 0
        for line in lines:
            if "|" in line:
                parts = line.split("|")
                q = parts[0].strip()
                a = "|".join(parts[1:]).strip()
                if q and a:
                    conn.table("questions").insert({"question_text": q, "correct_answer": a}).execute()
                    count += 1
        return count
    except: return False

def get_live_inputs(q_id):
    def op():
        return conn.table("player_inputs").select("*").eq("question_id", q_id).execute().data
    return run_safe(op)

def get_live_votes(q_id):
    def op():
        return conn.table("player_votes").select("*").eq("question_id", q_id).execute().data
    return run_safe(op)

# ==========================================
# 🔒 AUTHENTICATION
# ==========================================
if 'admin_logged_in' not in st.session_state:
    pwd = st.text_input("Enter Admin Password", type="password")
    if st.button("Login"):
        if pwd == st.secrets["admin"]["password"]:
            st.session_state.admin_logged_in = True
            st.rerun()
    st.stop()

# ==========================================
# 🕹️ SIDEBAR CONTROLS
# ==========================================
with st.sidebar:
    st.header("⚙️ Game Settings")
    
    # RESET BUTTON
    with st.expander("Danger Zone"):
        reset_pwd = st.text_input("Confirm Password", type="password", key="reset_key")
        if st.button("☢️ HARD RESET GAME"):
            if reset_pwd == st.secrets["admin"]["password"]:
                nuke_data()
                st.success("Game Wiped.")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Wrong Password")

# ==========================================
# 🚀 MAIN DASHBOARD
# ==========================================
st.title("🕹️ Quiz Master Control")

state = get_state()
if not state:
    st.warning("Connecting to database...")
    st.stop()

phase = state['phase']
total_players = state['total_players']
current_q_id = state['current_question_id']

# Layout: Two Columns (Controls | Live Monitor)
col_controls, col_mirror = st.columns([1, 1])

# --- LEFT COLUMN: CONTROLLER ---
with col_controls:
    st.subheader("1. Game Controller")
    st.info(f"Current Phase: **{phase}**")

    # PHASE: LOBBY
    if phase == "LOBBY":
        gh_url = st.text_input("GitHub Raw URL (.txt)")
        if st.button("📥 Import Questions"):
            count = load_questions_from_github(gh_url)
            if count: st.success(f"Loaded {count} questions!")
        
        # 1. Get value from DB
        db_val = state.get('total_players', 0)
        # 2. Ensure it is at least 1 before putting it in the widget
        safe_val = db_val if db_val >= 1 else 2
        if st.button("Set Player Count"):
            update_state({"total_players": num_players})
            st.success("Saved.")
        
        st.markdown("---")
        questions = conn.table("questions").select("*").execute().data
        if questions:
            q_map = {q['id']: q['question_text'] for q in questions}
            selected_id = st.selectbox("Pick First Question", options=q_map.keys(), format_func=lambda x: q_map[x])
            if st.button("🚀 START GAME"):
                update_state({"phase": "INPUT", "current_question_id": selected_id})
                st.rerun()

    # PHASE: INPUT
    elif phase == "INPUT":
        live_inputs = get_live_inputs(current_q_id) or []
        count = len(live_inputs)
        st.metric("Submissions", f"{count} / {total_players}")
        
        # Show who has submitted
        if live_inputs:
            st.write("✅ Submitted:", ", ".join([i['user_id'] for i in live_inputs]))
        
        if count >= total_players:
            st.success("Ready to Vote!")
            if st.button("➡️ Start Voting"):
                update_state({"phase": "VOTING"})
                st.rerun()
        else:
            st.warning("Waiting for players...")

    # PHASE: VOTING
    elif phase == "VOTING":
        live_votes = get_live_votes(current_q_id) or []
        count = len(live_votes)
        st.metric("Votes Cast", f"{count} / {total_players}")
        
        if live_votes:
            st.write("✅ Voted:", ", ".join([v['user_id'] for v in live_votes]))

        if count >= total_players:
            st.success("Voting Complete!")
            if st.button("➡️ Reveal Results"):
                update_state({"phase": "RESULTS"})
                st.rerun()
        else:
            st.warning("Waiting for votes...")

    # PHASE: RESULTS
    elif phase == "RESULTS":
        st.success("Results are live on screen.")
        
        # Logic for Next Question
        questions = conn.table("questions").select("*").execute().data
        current_index = next((i for i, q in enumerate(questions) if q["id"] == current_q_id), -1)
        
        if current_index + 1 < len(questions):
            next_q = questions[current_index + 1]
            if st.button(f"⏭️ Next: {next_q['question_text']}"):
                update_state({"phase": "INPUT", "current_question_id": next_q['id']})
                st.rerun()
        else:
            st.balloons()
            st.write("🎉 No more questions!")
            if st.button("Back to Lobby"):
                update_state({"phase": "LOBBY"})
                st.rerun()

# --- RIGHT COLUMN: SCREEN MIRROR ---
with col_mirror:
    st.subheader("📱 Player Screen Mirror")
    st.markdown("*(This is exactly what players see on their phones)*")
    
    container = st.container(border=True)
    
    with container:
        if phase == "LOBBY":
            st.info("Waiting for host to start...")
            st.image("https://media.giphy.com/media/xTkcEQACH24SMPxIQg/giphy.gif")
            
        elif phase == "INPUT":
            q_data = get_current_question(current_q_id)
            if q_data:
                st.subheader(q_data['question_text'])
                st.text_input("Type your bluff answer:", key="mirror_input", disabled=True, placeholder="Players are typing here...")
                
        elif phase == "VOTING":
            q_data = get_current_question(current_q_id)
            if q_data:
                st.subheader(q_data['question_text'])
                st.write("Select an option:")
                
                # Fetch what the options look like
                inputs = get_live_inputs(current_q_id) or []
                options = [i['answer_text'] for i in inputs]
                options.append(q_data['correct_answer'])
                
                # Display them as a static list (since we can't shuffle identically to every user)
                for opt in set(options):
                    st.markdown(f"- 🔘 {opt}")
                    
        elif phase == "RESULTS":
            q_data = get_current_question(current_q_id)
            if q_data:
                st.balloons()
                st.markdown(f"### Correct Answer: **{q_data['correct_answer']}**")
                st.write("📊 [Leaderboard is displayed here]")

# Auto-refresh
time.sleep(2)
st.rerun()

