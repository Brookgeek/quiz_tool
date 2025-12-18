import streamlit as st
from st_supabase_connection import SupabaseConnection
import time
import random
import pandas as pd

# --- CONFIGURATION ---
st.set_page_config(page_title="Play Quiz", layout="centered")
conn = st.connection("supabase", type=SupabaseConnection)

# 🖼️ CUSTOM IMAGES (Add your URLs here)
# You can use GitHub Raw URLs or any hosted image link.
WAITING_IMAGES = [
    "https://media.giphy.com/media/xTkcEQACH24SMPxIQg/giphy.gif",
    "https://media.giphy.com/media/l0HlBO7eyXzSZkJri/giphy.gif",
    "https://media.giphy.com/media/tXL4FHPSnVJ0A/giphy.gif"
]

# --- SAFETY WRAPPER ---
def run_safe(operation):
    try:
        return operation()
    except Exception:
        time.sleep(1)
        try:
            return operation()
        except Exception:
            return None

# --- HELPER FUNCTIONS ---
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
        conn.table("players").upsert({"user_id": user_id, "status": "PENDING"}).execute()
    run_safe(op)

def calculate_leaderboard():
    def op():
        # Fetch all data needed for scoring
        all_votes = conn.table("player_votes").select("*").execute().data
        all_inputs = conn.table("player_inputs").select("*").execute().data
        all_qs = conn.table("questions").select("*").execute().data
        
        q_map = {q['id']: q['correct_answer'] for q in all_qs}
        bluff_map = {(i['question_id'], i['answer_text']): i['user_id'] for i in all_inputs}
        
        scores = {}
        for v in all_votes:
            voter = v['user_id']
            qid = v['question_id']
            choice = v['voted_for']
            
            # Init
            scores[voter] = scores.get(voter, 0)
            
            # Points for Correct
            if choice == q_map.get(qid):
                scores[voter] += 10
            
            # Points for Bluffing
            bluffer = bluff_map.get((qid, choice))
            if bluffer and bluffer != voter:
                scores[bluffer] = scores.get(bluffer, 0) + 5
        return scores
    return run_safe(op) or {}

# --- MAIN APP LOGIC ---

# 1. LOGIN SCREEN
if "user_id" not in st.session_state:
    st.title("🎲 Join Quiz")
    uid = st.text_input("Enter Nickname")
    if st.button("Request to Join"):
        if uid:
            # GHOST PLAYER BACKDOOR
            if uid == "GhostPlayer":
                st.session_state.user_id = uid
                st.session_state.is_ghost = True
                st.rerun()
            else:
                register_player(uid)
                st.session_state.user_id = uid
                st.session_state.is_ghost = False
                st.rerun()
    st.stop()

# 2. STATUS CHECK
user_id = st.session_state.user_id
is_ghost = st.session_state.get("is_ghost", False)

if not is_ghost:
    status = check_player_status(user_id)
    if status == "PENDING":
        st.info(f"Hi **{user_id}**! Waiting for Admin to admit you...")
        # Random Waiting Image
        if WAITING_IMAGES:
            st.image(random.choice(WAITING_IMAGES))
        time.sleep(3)
        st.rerun()
    elif status == "BANNED":
        st.error("Access Denied.")
        st.stop()

# 3. GAME LOOP
if is_ghost:
    st.warning("👻 GHOST MODE ACTIVE (Read Only)")

st.write(f"👤 Playing as: **{user_id}**")
st.divider()

state = get_state()
if not state:
    st.write("Connecting...")
    time.sleep(1)
    st.rerun()

phase = state['phase']
q_id = state['current_question_id']

# --- PHASE: LOBBY ---
if phase == "LOBBY":
    st.info("You are in! Waiting for game start...")
    if WAITING_IMAGES:
        st.image(random.choice(WAITING_IMAGES))

# --- PHASE: INPUT ---
elif phase == "INPUT":
    q = get_current_question(q_id)
    if q:
        st.subheader(f"Q: {q['question_text']}")
        
        if is_ghost:
            st.info("Players are typing answers now...")
        else:
            # Check if submitted
            def check_input():
                return conn.table("player_inputs").select("*").eq("question_id", q_id).eq("user_id", user_id).execute().data
            existing = run_safe(check_input)
            
            if existing:
                st.success("Answer sent! Waiting for others...")
            else:
                ans = st.text_input("Type your bluff:")
                if st.button("Submit"):
                    def send_input():
                        conn.table("player_inputs").insert({"user_id": user_id, "question_id": q_id, "answer_text": ans}).execute()
                    run_safe(send_input)
                    st.rerun()

# --- PHASE: VOTING ---
elif phase == "VOTING":
    q = get_current_question(q_id)
    if q:
        st.subheader(f"Q: {q['question_text']}")
        
        if is_ghost:
            st.info("Players are voting now...")
            # Show options for ghost to see
            def get_all_inputs():
                return conn.table("player_inputs").select("answer_text").eq("question_id", q_id).execute().data
            bluffs = run_safe(get_all_inputs) or []
            
            # Deduplication Logic
            raw_options = [b['answer_text'] for b in bluffs] + [q['correct_answer']]
            unique_options = list(set(raw_options))
            st.write("Current Options:", unique_options)

        else:
            # Player Voting Logic
            def check_vote():
                return conn.table("player_votes").select("*").eq("question_id", q_id).eq("user_id", user_id).execute().data
            existing = run_safe(check_vote)
            
            if existing:
                st.success("Vote cast! Waiting for results...")
            else:
                # 1. Fetch Bluffs safely (Empty list if None)
                def fetch_bluffs():
                    return conn.table("player_inputs").select("answer_text").eq("question_id", q_id).execute().data
                bluffs = run_safe(fetch_bluffs) or []
                
                # 2. Create Deduplicated List (The Fix)
                # We use set() to automatically remove identical strings
                raw_options = [b['answer_text'] for b in bluffs] + [q['correct_answer']]
                unique_options = list(set(raw_options))
                
                # 3. Shuffle consistently
                if f"shuffled_{q_id}" not in st.session_state:
                    random.shuffle(unique_options)
                    st.session_state[f"shuffled_{q_id}"] = unique_options
                    
                # 4. Render
                choice = st.radio("Vote for the real answer:", st.session_state[f"shuffled_{q_id}"])
                if st.button("Cast Vote"):
                    def send_vote():
                        conn.table("player_votes").insert({"user_id": user_id, "question_id": q_id, "voted_for": choice}).execute()
                    run_safe(send_vote)
                    st.rerun()

# --- PHASE: RESULTS ---
elif phase == "RESULTS":
    q = get_current_question(q_id)
    if q:
        st.balloons()
        st.success(f"Correct Answer: **{q['correct_answer']}**")
        
        # 1. Who wrote what?
        st.markdown("### 🕵️ Who wrote what?")
        def fetch_authors():
            return conn.table("player_inputs").select("*").eq("question_id", q_id).execute().data
        inputs = run_safe(fetch_authors) or []
        
        reveal_data = []
        for i in inputs:
            reveal_data.append({"Bluff": i['answer_text'], "Author": i['user_id']})
        st.table(pd.DataFrame(reveal_data))
        
        st.divider()
        
        # 2. Leaderboard (Visible to Players now)
        st.markdown("### 🏆 Leaderboard (Top 5)")
        scores = calculate_leaderboard()
        if scores:
            df = pd.DataFrame(list(scores.items()), columns=["Player", "Score"])
            df = df.sort_values("Score", ascending=False).head(5)
            st.dataframe(df, hide_index=True, use_container_width=True)

# Auto-refresh
time.sleep(3)
st.rerun()
