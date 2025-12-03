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
import time
import random
import pandas as pd

st.set_page_config(page_title="Play Quiz", layout="centered")
conn = st.connection("supabase", type=SupabaseConnection)

# ==========================================
# 🛡️ THE SAFETY LAYER (Prevents Crashes)
# ==========================================
def run_safe(operation):
    """
    Tries to run a database command. 
    If it crashes (httpx error), it waits 1 second and tries again.
    """
    try:
        return operation()
    except Exception:
        time.sleep(1) # Wait for network to reconnect
        try:
            return operation() # Retry once
        except Exception:
            return None # Return None if it fails twice (keeps app alive)

# ==========================================
# 🧠 HELPER FUNCTIONS (All Wrapped)
# ==========================================
def get_state():
    def op():
        return conn.table("game_state").select("*").eq("id", 1).execute().data[0]
    return run_safe(op)

def get_current_question(q_id):
    if not q_id: return None
    def op():
        return conn.table("questions").select("*").eq("id", q_id).execute().data[0]
    return run_safe(op)

def get_my_input(q_id, user_id):
    def op():
        return conn.table("player_inputs").select("*").eq("question_id", q_id).eq("user_id", user_id).execute().data
    return run_safe(op)

def submit_input(user_id, q_id, text):
    def op():
        conn.table("player_inputs").insert({
            "user_id": user_id, "question_id": q_id, "answer_text": text
        }).execute()
        return True
    run_safe(op)

def get_my_vote(q_id, user_id):
    def op():
        return conn.table("player_votes").select("*").eq("question_id", q_id).eq("user_id", user_id).execute().data
    return run_safe(op)

def submit_vote(user_id, q_id, choice):
    def op():
        conn.table("player_votes").insert({
            "user_id": user_id, "question_id": q_id, "voted_for": choice
        }).execute()
        return True
    run_safe(op)

def get_voting_options(q_id, correct_answer):
    def op():
        bluffs = conn.table("player_inputs").select("answer_text").eq("question_id", q_id).execute().data
        options = [b['answer_text'] for b in bluffs]
        options.append(correct_answer)
        return list(set(options)) # Deduplicate
    return run_safe(op)

def get_round_results(q_id):
    # This is where your error was happening! Now it's safe.
    def op():
        return conn.table("player_votes").select("*").eq("question_id", q_id).execute().data
    return run_safe(op)

def calculate_leaderboard():
    def op():
        # Fetch all data in one go
        all_votes = conn.table("player_votes").select("*").execute().data
        all_inputs = conn.table("player_inputs").select("*").execute().data
        all_questions = conn.table("questions").select("*").execute().data
        
        # Logic
        correct_map = {q['id']: q['correct_answer'] for q in all_questions}
        bluff_map = {}
        for i in all_inputs:
            bluff_map[(i['question_id'], i['answer_text'])] = i['user_id']
            
        scores = {}
        for v in all_votes:
            voter = v['user_id']
            qid = v['question_id']
            choice = v['voted_for']
            
            # Init scorer
            if voter not in scores: scores[voter] = 0
            
            # Points for Correct Guess (+10)
            if choice == correct_map.get(qid):
                scores[voter] += 10
            
            # Points for Fooling Others (+5)
            bluffer = bluff_map.get((qid, choice))
            if bluffer and bluffer != voter:
                if bluffer not in scores: scores[bluffer] = 0
                scores[bluffer] += 5
        return scores
    return run_safe(op)

# ==========================================
# 🎮 MAIN APP LOGIC
# ==========================================

# 1. LOGIN
if "user_id" not in st.session_state:
    st.title("🎲 Join Game")
    uid = st.text_input("Enter Nickname")
    if st.button("Join"):
        if uid:
            st.session_state.user_id = uid
            st.rerun()
    st.stop()

st.write(f"👤 **{st.session_state.user_id}**")

# 2. SYNC STATE
state = get_state()
if not state:
    st.warning("Connecting...")
    time.sleep(1)
    st.rerun()

phase = state['phase']
q_id = state['current_question_id']

# 3. PHASE HANDLERS
if phase == "LOBBY":
    st.info("Waiting for host to start...")
    st.image("https://media.giphy.com/media/xTkcEQACH24SMPxIQg/giphy.gif")

elif phase == "INPUT":
    q_data = get_current_question(q_id)
    if q_data:
        st.subheader(q_data['question_text'])
        
        existing = get_my_input(q_id, st.session_state.user_id)
        if existing:
            st.success("Answer sent! Waiting for others...")
        else:
            ans = st.text_input("Type your bluff answer:")
            if st.button("Submit"):
                if ans:
                    submit_input(st.session_state.user_id, q_id, ans)
                    st.rerun()

elif phase == "VOTING":
    q_data = get_current_question(q_id)
    if q_data:
        st.subheader(q_data['question_text'])
        
        existing_vote = get_my_vote(q_id, st.session_state.user_id)
        if existing_vote:
            st.success("Vote cast! Waiting for results...")
        else:
            # Generate options logic
            if f"shuffled_{q_id}" not in st.session_state:
                options = get_voting_options(q_id, q_data['correct_answer'])
                random.shuffle(options)
                st.session_state[f"shuffled_{q_id}"] = options
            
            choice = st.radio("Select an option:", st.session_state[f"shuffled_{q_id}"])
            if st.button("Vote"):
                submit_vote(st.session_state.user_id, q_id, choice)
                st.rerun()

elif phase == "RESULTS":
    q_data = get_current_question(q_id)
    if q_data:
        st.balloons()
        st.markdown(f"### Correct Answer: **{q_data['correct_answer']}**")
        st.markdown("---")

        # ROUND SUMMARY
        st.subheader("📊 Round Results")
        current_votes = get_round_results(q_id) # <--- Safe function used here now
        
        if current_votes:
            vote_data = [{"Player": v['user_id'], "Voted For": v['voted_for']} for v in current_votes]
            st.dataframe(pd.DataFrame(vote_data), hide_index=True)
        
        st.markdown("---")
        
        # LEADERBOARD
        st.subheader("🏆 Leaderboard")
        scores = calculate_leaderboard()
        if scores:
            sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            df_scores = pd.DataFrame(sorted_scores, columns=["Player", "Total Points"])
            st.dataframe(df_scores, hide_index=True, use_container_width=True)

# Auto-refresh loop
time.sleep(3)
st.rerun()        
