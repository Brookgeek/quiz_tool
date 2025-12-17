import streamlit as st
from st_supabase_connection import SupabaseConnection
import time
import random
import pandas as pd

st.set_page_config(page_title="Play Quiz", layout="centered")
conn = st.connection("supabase", type=SupabaseConnection)

def run_safe(operation):
    try:
        return operation()
    except:
        time.sleep(1)
        try: return operation()
        except: return None

# --- HELPERS ---
def get_state():
    def op(): return conn.table("game_state").select("*").eq("id", 1).execute().data[0]
    return run_safe(op)

def get_current_question(q_id):
    def op(): return conn.table("questions").select("*").eq("id", q_id).execute().data[0]
    return run_safe(op)

def check_player_status(user_id):
    def op():
        res = conn.table("players").select("status").eq("user_id", user_id).execute().data
        return res[0]['status'] if res else None
    return run_safe(op)

def register_player(user_id):
    def op():
        # Insert if not exists
        conn.table("players").upsert({"user_id": user_id, "status": "PENDING"}).execute()
    run_safe(op)

# --- LOGIN & ADMISSION ---
if "user_id" not in st.session_state:
    uid = st.text_input("Nickname")
    if st.button("Request to Join"):
        register_player(uid)
        st.session_state.user_id = uid
        st.rerun()
    st.stop()

# Check Status Loop
status = check_player_status(st.session_state.user_id)
if status == "PENDING":
    st.info(f"Hi {st.session_state.user_id}! Waiting for Admin to admit you...")
    time.sleep(3)
    st.rerun()
elif status == "BANNED":
    st.error("You have been blocked from this game.")
    st.stop()

# --- MAIN GAME ---
st.write(f"👤 **{st.session_state.user_id}**")
state = get_state()
if not state: st.stop()

phase = state['phase']
q_id = state['current_question_id']

if phase == "LOBBY":
    st.info("You are in! Waiting for game start...")

elif phase == "INPUT":
    q = get_current_question(q_id)
    st.subheader(q['question_text'])
    
    # Check if submitted
    existing = run_safe(lambda: conn.table("player_inputs").select("*").eq("question_id", q_id).eq("user_id", st.session_state.user_id).execute().data)
    
    if existing:
        st.success("Sent! Admin is reviewing answers...")
    else:
        ans = st.text_input("Your Bluff:")
        if st.button("Send"):
            run_safe(lambda: conn.table("player_inputs").insert({"user_id": st.session_state.user_id, "question_id": q_id, "answer_text": ans}).execute())
            st.rerun()

elif phase == "VOTING":
    q = get_current_question(q_id)
    st.subheader(q['question_text'])
    
    existing = run_safe(lambda: conn.table("player_votes").select("*").eq("question_id", q_id).eq("user_id", st.session_state.user_id).execute().data)
    
    if existing:
        st.success("Voted!")
    else:
        # Get options (Inputs + Correct)
        bluffs = run_safe(lambda: conn.table("player_inputs").select("answer_text").eq("question_id", q_id).execute().data)
        opts = [b['answer_text'] for b in bluffs] + [q['correct_answer']]
        
        # Consistent Shuffle
        if f"shuffled_{q_id}" not in st.session_state:
            random.shuffle(opts)
            st.session_state[f"shuffled_{q_id}"] = opts
            
        choice = st.radio("Vote:", st.session_state[f"shuffled_{q_id}"])
        if st.button("Cast Vote"):
            run_safe(lambda: conn.table("player_votes").insert({"user_id": st.session_state.user_id, "question_id": q_id, "voted_for": choice}).execute())
            st.rerun()

elif phase == "RESULTS":
    q = get_current_question(q_id)
    st.balloons()
    st.write(f"### Correct: {q['correct_answer']}")
    
    st.markdown("### 🕵️ Who wrote what?")
    
    # REVEAL AUTHORS LOGIC
    inputs = run_safe(lambda: conn.table("player_inputs").select("*").eq("question_id", q_id).execute().data)
    
    reveal_data = []
    for i in inputs:
        reveal_data.append({"Bluff Answer": i['answer_text'], "Author": i['user_id']})
    
    st.table(pd.DataFrame(reveal_data))
    
    # Scores logic (Optional to show here again)

time.sleep(3)
st.rerun()
