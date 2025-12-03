import streamlit as st
from st_supabase_connection import SupabaseConnection
import requests
import time

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

st.set_page_config(page_title="Admin Controller", layout="wide")
conn = st.connection("supabase", type=SupabaseConnection)

# --- HELPER FUNCTIONS ---
def get_state():
    return conn.table("game_state").select("*").eq("id", 1).execute().data[0]

def update_state(updates):
    conn.table("game_state").update(updates).eq("id", 1).execute()

def nuke_data():
    conn.table("questions").delete().gt("id", 0).execute()
    conn.table("player_inputs").delete().gt("id", 0).execute()
    conn.table("player_votes").delete().gt("id", 0).execute()
    update_state({"phase": "LOBBY", "total_players": 0, "current_question_id": None})

def load_questions_from_github(url):
    try:
        resp = requests.get(url)
        if resp.status_code != 200: return False
        lines = resp.text.strip().split('\n')
        count = 0
        for line in lines:
            if "|" in line:
                q, a = line.split("|", 1)
                conn.table("questions").insert({"question_text": q.strip(), "correct_answer": a.strip()}).execute()
                count += 1
        return count
    except: return False

# --- AUTH ---
if 'admin_logged_in' not in st.session_state:
    pwd = st.text_input("Admin Password", type="password")
    if st.button("Login"):
        if pwd == st.secrets["admin"]["password"]:
            st.session_state.admin_logged_in = True
            st.rerun()
    st.stop()

# --- MAIN DASHBOARD ---
st.title("������️ Quiz Master Control")
state = get_state()
phase = state['phase']
total_players = state['total_players']
current_q_id = state['current_question_id']

# --- PHASE: LOBBY ---
if phase == "LOBBY":
    st.info("Step 1: Setup Game")
    
    c1, c2 = st.columns(2)
    with c1:
        gh_url = st.text_input("GitHub Raw URL (.txt)")
        if st.button("������ Import Questions"):
            count = load_questions_from_github(gh_url)
            if count: st.success(f"Loaded {count} questions!")
            else: st.error("Failed to load.")
            
    with c2:
        num_players = st.number_input("Total Players Expected", min_value=1, value=2)
        if st.button("Set Player Count"):
            update_state({"total_players": num_players})
            st.success(f"Game set for {num_players} players.")

    st.markdown("---")
    
    # Question Selection
    questions = conn.table("questions").select("*").execute().data
    if questions:
        q_map = {q['id']: q['question_text'] for q in questions}
        selected_id = st.selectbox("Select First Question", options=q_map.keys(), format_func=lambda x: q_map[x])
        
        if st.button("������ START GAME"):
            # Clear old inputs for this question just in case
            conn.table("player_inputs").delete().gt("id", 0).execute()
            conn.table("player_votes").delete().gt("id", 0).execute()
            update_state({"phase": "INPUT", "current_question_id": selected_id})
            st.rerun()
    
    if st.button("⚠️ Reset Everything"):
        nuke_data()
        st.rerun()

# --- PHASE: INPUT ---
elif phase == "INPUT":
    st.subheader("������ Phase: Collecting Answers")
    
    # Check Progress
    inputs = conn.table("player_inputs").select("*", count="exact").eq("question_id", current_q_id).execute()
    count = len(inputs.data)
    
    st.metric("Submissions", f"{count} / {total_players}")
    
    if count >= total_players:
        st.success("All players have answered!")
        if st.button("Go to Voting"):
            update_state({"phase": "VOTING"})
            st.rerun()
    else:
        st.warning("Waiting for players...")
        time.sleep(2)
        st.rerun()

# --- PHASE: VOTING ---
elif phase == "VOTING":
    st.subheader("������ Phase: Voting")
    
    votes = conn.table("player_votes").select("*", count="exact").eq("question_id", current_q_id).execute()
    count = len(votes.data)
    
    st.metric("Votes Cast", f"{count} / {total_players}")
    
    if count >= total_players:
        st.success("All players have voted!")
        if st.button("Show Results"):
            update_state({"phase": "RESULTS"})
            st.rerun()
    else:
        st.warning("Waiting for votes...")
        time.sleep(2)
        st.rerun()

# --- PHASE: RESULTS ---
elif phase == "RESULTS":
    st.subheader("������ Phase: Results")
    st.write("Results are being shown on player screens.")
    
    questions = conn.table("questions").select("*").execute().data
    current_index = next((i for i, q in enumerate(questions) if q["id"] == current_q_id), -1)
    
    if current_index + 1 < len(questions):
        next_q = questions[current_index + 1]
        if st.button(f"Start Next Question: {next_q['question_text']}"):
             # Clear inputs/votes for the NEW question
            update_state({"phase": "INPUT", "current_question_id": next_q['id']})
            st.rerun()
    else:
        st.success("End of Quiz!")
        if st.button("Back to Lobby"):
            update_state({"phase": "LOBBY"})

            st.rerun()
