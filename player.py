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

# --- STATE MANAGEMENT ---
def get_state():
    resp = conn.table("game_state").select("*").eq("id", 1).execute()
    return resp.data[0] if resp.data else None

def get_current_question(q_id):
    if not q_id: return None
    return conn.table("questions").select("*").eq("id", q_id).execute().data[0]

# --- SCORING ENGINE ---
def calculate_scores():
    # 1. Fetch EVERYTHING (History of game)
    all_votes = conn.table("player_votes").select("*").execute().data
    all_inputs = conn.table("player_inputs").select("*").execute().data
    all_questions = conn.table("questions").select("*").execute().data
    
    # 2. Build Lookup Maps
    # Map: Question ID -> Correct Answer
    correct_map = {q['id']: q['correct_answer'] for q in all_questions}
    
    # Map: (Question ID, Answer Text) -> User who wrote it (The Bluffer)
    # We normalize to lowercase/strip to ensure matches work
    bluff_map = {}
    for i in all_inputs:
        key = (i['question_id'], i['answer_text'])
        bluff_map[key] = i['user_id']
        
    scores = {}
    
    # 3. Process Votes
    for v in all_votes:
        voter = v['user_id']
        qid = v['question_id']
        choice = v['voted_for']
        correct_answer = correct_map.get(qid)
        
        # Initialize 0 if new user
        if voter not in scores: scores[voter] = 0
        
        # Rule A: Correct Answer (+10 to Voter)
        if choice == correct_answer:
            scores[voter] += 10
            
        # Rule B: Bluff Points (+5 to Bluffer)
        # Check if this choice was someone's bluff
        bluff_key = (qid, choice)
        if bluff_key in bluff_map:
            bluffer = bluff_map[bluff_key]
            # Initialize bluffer if not exists
            if bluffer not in scores: scores[bluffer] = 0
            
            # Grant points (User cannot bluff themselves usually, but if they vote for own bluff no points)
            if bluffer != voter:
                scores[bluffer] += 5
                
    return scores

# --- LOGIN ---
if "user_id" not in st.session_state:
    st.title("🎲 Join Game")
    uid = st.text_input("Enter Nickname")
    if st.button("Join"):
        if uid:
            st.session_state.user_id = uid
            st.rerun()
    st.stop()

st.write(f"👤 **{st.session_state.user_id}**")

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
    
    # RETRY LOGIC: Try to fetch data. If network fails, wait 0.5s and try one more time.
    try:
        existing_vote = conn.table("player_votes").select("*").eq("question_id", q_id).eq("user_id", st.session_state.user_id).execute().data
    except Exception:
        time.sleep(0.5)
        existing_vote = conn.table("player_votes").select("*").eq("question_id", q_id).eq("user_id", st.session_state.user_id).execute().data
    
    if existing_vote:
        st.success("Vote cast! Waiting for results...")
    else:
        bluffs = conn.table("player_inputs").select("answer_text").eq("question_id", q_id).execute().data
        # Exclude my own answer from options? (Optional, but usually fair)
        # options = [b['answer_text'] for b in bluffs if b['user_id'] != st.session_state.user_id]
        options = [b['answer_text'] for b in bluffs]
        options.append(q_data['correct_answer'])
        
        unique_options = list(set(options))
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
    st.markdown(f"### Correct Answer: **{q_data['correct_answer']}**")
    st.markdown("---")

    # 1. SHOW VOTES FOR THIS ROUND
    st.subheader("📊 Round Results")
    current_votes = conn.table("player_votes").select("*").eq("question_id", q_id).execute().data
    if current_votes:
        vote_data = [{"Player": v['user_id'], "Voted For": v['voted_for']} for v in current_votes]
        st.dataframe(pd.DataFrame(vote_data), hide_index=True)
    
    st.markdown("---")
    
    # 2. SHOW TOTAL LEADERBOARD
    st.subheader("🏆 Leaderboard")
    scores = calculate_scores()
    
    # Sort by score descending
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    
    # Create nice DataFrame
    df_scores = pd.DataFrame(sorted_scores, columns=["Player", "Total Points"])
    st.dataframe(df_scores, hide_index=True, use_container_width=True)

# Auto-refresh
time.sleep(3)
st.rerun()

