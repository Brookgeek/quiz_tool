import streamlit as st
from st_supabase_connection import SupabaseConnection
import time
import random

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
        
st.set_page_config(page_title="Play Quiz", layout="centered")
conn = st.connection("supabase", type=SupabaseConnection)

# --- STATE MANAGEMENT ---
def get_state():
    resp = conn.table("game_state").select("*").eq("id", 1).execute()
    return resp.data[0] if resp.data else None

def get_current_question(q_id):
    if not q_id: return None
    return conn.table("questions").select("*").eq("id", q_id).execute().data[0]

# --- LOGIN ---
if "user_id" not in st.session_state:
    st.title("������ Join Game")
    uid = st.text_input("Enter Nickname")
    if st.button("Join"):
        if uid:
            st.session_state.user_id = uid
            st.rerun()
    st.stop()

st.write(f"������ **{st.session_state.user_id}**")

# --- GAME LOOP ---
state = get_state()
if not state: st.stop()

phase = state['phase']
q_id = state['current_question_id']

# --- LOGIC ---
if phase == "LOBBY":
    st.info("Waiting for host to start...")
    st.image("https://media.giphy.com/media/xTkcEQACH24SMPxIQg/giphy.gif")

elif phase == "INPUT":
    q_data = get_current_question(q_id)
    st.subheader(q_data['question_text'])
    
    # Check if this user already answered
    existing = conn.table("player_inputs").select("*").eq("question_id", q_id).eq("user_id", st.session_state.user_id).execute().data
    
    if existing:
        st.success("Answer sent! Waiting for other players...")
    else:
        ans = st.text_input("Type your bluff answer:")
        if st.button("Submit"):
            if ans:
                conn.table("player_inputs").insert({
                    "user_id": st.session_state.user_id,
                    "question_id": q_id,
                    "answer_text": ans
                }).execute()
                st.rerun()

elif phase == "VOTING":
    q_data = get_current_question(q_id)
    st.subheader(q_data['question_text'])
    st.write("Which is the REAL answer?")
    
    # Check if voted
    existing_vote = conn.table("player_votes").select("*").eq("question_id", q_id).eq("user_id", st.session_state.user_id).execute().data
    
    if existing_vote:
        st.success("Vote cast! Waiting for results...")
    else:
        # Fetch all bluffs + Correct Answer
        bluffs = conn.table("player_inputs").select("answer_text").eq("question_id", q_id).execute().data
        options = [b['answer_text'] for b in bluffs]
        options.append(q_data['correct_answer'])
        
        # Deduplicate and Shuffle
        unique_options = list(set(options))
        # We use a session state seed to ensure shuffle stays consistent for the user during refresh
        if f"shuffled_{q_id}" not in st.session_state:
            random.shuffle(unique_options)
            st.session_state[f"shuffled_{q_id}"] = unique_options
            
        choice = st.radio("Select an option:", st.session_state[f"shuffled_{q_id}"])
        if st.button("Vote"):
            conn.table("player_votes").insert({
                "user_id": st.session_state.user_id,
                "question_id": q_id,
                "voted_for": choice
            }).execute()
            st.rerun()

elif phase == "RESULTS":
    q_data = get_current_question(q_id)
    st.balloons()
    st.subheader(f"The Correct Answer: {q_data['correct_answer']}")
    
    # Show who voted for what
    votes = conn.table("player_votes").select("*").eq("question_id", q_id).execute().data
    df_votes = [{"Player": v['user_id'], "Voted For": v['voted_for']} for v in votes]
    st.table(df_votes)

# Auto-refresh to keep sync with Admin
time.sleep(3)

st.rerun()
