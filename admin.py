import streamlit as st
from st_supabase_connection import SupabaseConnection
import requests
import time
import pandas as pd
import json

st.set_page_config(page_title="Admin Pro", layout="wide")
conn = st.connection("supabase", type=SupabaseConnection)

# --- SAFETY & HELPERS ---
def run_safe(operation):
    try:
        return operation()
    except Exception:
        time.sleep(1)
        try:
            return operation()
        except Exception:
            return None

def get_state():
    def op(): return conn.table("game_state").select("*").eq("id", 1).execute().data[0]
    return run_safe(op)

def update_state(updates):
    def op(): conn.table("game_state").update(updates).eq("id", 1).execute()
    run_safe(op)

def log_event(round_id, l_type, data):
    # Saves data to DB for crash recovery
    def op():
        conn.table("game_logs").insert({
            "round_id": round_id, "log_type": l_type, "details": json.dumps(data)
        }).execute()
    run_safe(op)

def calculate_scores_snapshot():
    # Helper to get current scores for logging
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
        
        scores[voter] = scores.get(voter, 0)
        if choice == q_map.get(qid): scores[voter] += 10
        
        bluffer = bluff_map.get((qid, choice))
        if bluffer and bluffer != voter:
            scores[bluffer] = scores.get(bluffer, 0) + 5
    return scores

def nuke_data():
    def op():
        conn.table("game_state").update({"current_question_id": None, "phase": "LOBBY", "total_players": 2}).eq("id", 1).execute()
        conn.table("player_votes").delete().gt("id", 0).execute()
        conn.table("player_inputs").delete().gt("id", 0).execute()
        conn.table("players").delete().neq("user_id", "xyz").execute() # Delete all players
        conn.table("game_logs").delete().gt("id", 0).execute()
        conn.table("questions").delete().gt("id", 0).execute()
    run_safe(op)

# --- AUTH ---
if 'admin_logged_in' not in st.session_state:
    pwd = st.text_input("Password", type="password")
    if st.button("Login"):
        if pwd == st.secrets["admin"]["password"]:
            st.session_state.admin_logged_in = True
            st.rerun()
    st.stop()

# --- SIDEBAR: LEADERBOARD & LOGS ---
with st.sidebar:
    st.header("🏆 Live Standings")
    curr_scores = calculate_scores_snapshot()
    if curr_scores:
        df = pd.DataFrame(list(curr_scores.items()), columns=["Player", "Score"])
        df = df.sort_values("Score", ascending=False)
        st.dataframe(df, hide_index=True)
    else:
        st.write("No points yet.")
        
    st.divider()
    with st.expander("System Logs"):
        logs = conn.table("game_logs").select("*").order("created_at", desc=True).execute().data
        if logs:
            st.write(logs)
            st.download_button("Download Logs JSON", json.dumps(logs), "game_logs.json")

    with st.expander("Danger Zone"):
        if st.button("☢️ HARD RESET"):
            nuke_data()
            st.rerun()

# --- MAIN APP ---
st.title("🛡️ Admin Console")
state = get_state()
phase = state['phase']
q_id = state['current_question_id']

# 1. LOBBY (Admission Control)
if phase == "LOBBY":
    c1, c2 = st.columns(2)
    with c1:
        # Import Logic (Same as before)
        gh = st.text_input("GitHub URL")
        if st.button("Import"):
            # (Insert your import logic here from previous code)
            pass 
        
        # Player Count
        tot = st.number_input("Max Players", min_value=1, value=state.get('total_players', 2))
        if st.button("Update Count"):
            update_state({"total_players": tot})
    
    with c2:
        st.subheader("🚪 Admission Gate")
        # Fetch pending players
        pending = conn.table("players").select("*").eq("status", "PENDING").execute().data
        approved = conn.table("players").select("*").eq("status", "APPROVED").execute().data
        
        st.write(f"Approved: {len(approved)} | Pending: {len(pending)}")
        
        if pending:
            for p in pending:
                col_p1, col_p2 = st.columns([3, 1])
                col_p1.write(f"**{p['user_id']}** wants to join.")
                if col_p2.button("Admit", key=p['user_id']):
                    conn.table("players").update({"status": "APPROVED"}).eq("user_id", p['user_id']).execute()
                    st.rerun()
        
    st.divider()
    # Start Game Logic
    qs = conn.table("questions").select("*").execute().data
    if qs:
        selected = st.selectbox("Start Question", [q['id'] for q in qs])
        if st.button("🚀 START GAME"):
            update_state({"phase": "INPUT", "current_question_id": selected})
            st.rerun()

# 2. INPUT (Moderation)
elif phase == "INPUT":
    st.subheader("📝 Moderation Phase")
    
    inputs = conn.table("player_inputs").select("*").eq("question_id", q_id).execute().data
    approved_players = len(conn.table("players").select("*").eq("status", "APPROVED").execute().data)
    
    st.metric("Submissions", f"{len(inputs)} / {approved_players}")
    
    # MODERATION FORM
    with st.form("mod_form"):
        st.write("Edit bluffs before voting (Fix typos):")
        edited_data = {}
        for row in inputs:
            # Show text input for each user's answer
            val = st.text_input(f"{row['user_id']}'s answer:", value=row['answer_text'])
            edited_data[row['id']] = val
            
        if st.form_submit_button("✅ Save & Start Voting"):
            # 1. Update DB with edited text
            for db_id, new_text in edited_data.items():
                conn.table("player_inputs").update({"answer_text": new_text}).eq("id", db_id).execute()
            
            # 2. Log this round's finalized bluffs
            log_event(q_id, "BLUFFS_FINALIZED", edited_data)
            
            # 3. Move Phase
            update_state({"phase": "VOTING"})
            st.rerun()

# 3. VOTING
elif phase == "VOTING":
    st.subheader("🗳️ Voting in Progress")
    votes = conn.table("player_votes").select("*").eq("question_id", q_id).execute().data
    approved_players = len(conn.table("players").select("*").eq("status", "APPROVED").execute().data)
    
    st.metric("Votes", f"{len(votes)} / {approved_players}")
    
    if len(votes) >= approved_players:
        if st.button("Reveal Results"):
            # Log scores at end of round
            scores = calculate_scores_snapshot()
            log_event(q_id, "SCORES_END_ROUND", scores)
            
            update_state({"phase": "RESULTS"})
            st.rerun()

# 4. RESULTS
elif phase == "RESULTS":
    st.subheader("📊 Results & Reveal")
    
    # Next Question Logic
    qs = conn.table("questions").select("*").execute().data
    curr_idx = next((i for i, q in enumerate(qs) if q["id"] == q_id), -1)
    
    if curr_idx + 1 < len(qs):
        next_q = qs[curr_idx + 1]
        if st.button(f"⏭️ Next: {next_q['question_text']}"):
            update_state({"phase": "INPUT", "current_question_id": next_q['id']})
            st.rerun()
    else:
        st.balloons()
        st.write("Game Over")

time.sleep(2)
st.rerun()
