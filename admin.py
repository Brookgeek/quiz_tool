import streamlit as st
from st_supabase_connection import SupabaseConnection
import requests
import time
import pandas as pd
import json

st.set_page_config(page_title="Admin Pro", layout="wide")
conn = st.connection("supabase", type=SupabaseConnection)

# ==========================================
# 🛡️ SAFETY LAYER (Prevents Network Crashes)
# ==========================================
def run_safe(operation):
    """
    Tries to run a database command. 
    If it crashes (httpx error), it waits 1 second and tries again.
    """
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
    def op(): return conn.table("game_state").select("*").eq("id", 1).execute().data[0]
    return run_safe(op)

def update_state(updates):
    def op(): conn.table("game_state").update(updates).eq("id", 1).execute()
    run_safe(op)

def log_event(round_id, l_type, data):
    def op():
        conn.table("game_logs").insert({
            "round_id": round_id, "log_type": l_type, "details": json.dumps(data)
        }).execute()
    run_safe(op)

def calculate_scores_snapshot():
    # --- THIS WAS THE CRASHING FUNCTION. NOW FIXED. ---
    def op():
        # Fetch data safely inside the wrapper
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
            
            # 1. Init Voter Score
            scores[voter] = scores.get(voter, 0)
            
            # 2. Points for Correct Answer (+10)
            if choice == q_map.get(qid): 
                scores[voter] += 10
            
            # 3. Points for Bluffing Others (+5)
            bluffer = bluff_map.get((qid, choice))
            if bluffer and bluffer != voter:
                scores[bluffer] = scores.get(bluffer, 0) + 5
                
        return scores
    
    # Execute safely
    return run_safe(op)

def nuke_data():
    def op():
        # Reset Game State
        conn.table("game_state").update({"current_question_id": None, "phase": "LOBBY", "total_players": 2}).eq("id", 1).execute()
        # Delete Children
        conn.table("player_votes").delete().gt("id", 0).execute()
        conn.table("player_inputs").delete().gt("id", 0).execute()
        conn.table("game_logs").delete().gt("id", 0).execute()
        # Delete Players (except Admin/System if needed, here we wipe all)
        conn.table("players").delete().neq("user_id", "SYSTEM").execute()
        # Delete Parents
        conn.table("questions").delete().gt("id", 0).execute()
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

def get_pending_players():
    def op(): return conn.table("players").select("*").eq("status", "PENDING").execute().data
    return run_safe(op) or []

def get_approved_players():
    def op(): return conn.table("players").select("*").eq("status", "APPROVED").execute().data
    return run_safe(op) or []

def approve_player(uid):
    def op(): conn.table("players").update({"status": "APPROVED"}).eq("user_id", uid).execute()
    run_safe(op)

# ==========================================
# 🔒 AUTHENTICATION
# ==========================================
if 'admin_logged_in' not in st.session_state:
    pwd = st.text_input("Admin Password", type="password")
    if st.button("Login"):
        if pwd == st.secrets["admin"]["password"]:
            st.session_state.admin_logged_in = True
            st.rerun()
    st.stop()

# ==========================================
# 🕹️ SIDEBAR (Leaderboard & Logs)
# ==========================================
with st.sidebar:
    st.header("🏆 Live Standings")
    
    # Calculate scores safely now
    curr_scores = calculate_scores_snapshot()
    
    if curr_scores:
        df = pd.DataFrame(list(curr_scores.items()), columns=["Player", "Score"])
        df = df.sort_values("Score", ascending=False)
        st.dataframe(df, hide_index=True, use_container_width=True)
    else:
        st.write("No points yet.")
        
    st.divider()
    
    with st.expander("System Logs"):
        def fetch_logs():
            return conn.table("game_logs").select("*").order("created_at", desc=True).limit(20).execute().data
        logs = run_safe(fetch_logs)
        if logs:
            st.write(logs)
            st.download_button("Download Logs JSON", json.dumps(logs), "game_logs.json")

    with st.expander("Danger Zone"):
        reset_pwd = st.text_input("Reset Password", type="password")
        if st.button("☢️ HARD RESET"):
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
st.title("🛡️ Admin Console")

state = get_state()
if not state:
    st.warning("Connecting...")
    st.stop()

phase = state['phase']
q_id = state['current_question_id']

# 1. LOBBY (Admission Control)
if phase == "LOBBY":
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("⚙️ Setup")
        gh_url = st.text_input("GitHub Raw URL (.txt)")
        if st.button("📥 Import Questions"):
            count = load_questions_from_github(gh_url)
            if count: st.success(f"Loaded {count} questions!")
        
        # Safe Input for Players
        db_val = state.get('total_players', 0)
        safe_val = db_val if db_val >= 1 else 2
        tot = st.number_input("Max Players", min_value=1, value=safe_val)
        
        if st.button("Update Count"):
            update_state({"total_players": tot})
            st.success("Saved.")
            
        # Question Picker
        def get_qs(): return conn.table("questions").select("*").execute().data
        qs = run_safe(get_qs)
        
        if qs:
            st.divider()
            selected = st.selectbox("Start Question", [q['id'] for q in qs], format_func=lambda x: next((i['question_text'] for i in qs if i['id'] == x), x))
            if st.button("🚀 START GAME"):
                update_state({"phase": "INPUT", "current_question_id": selected})
                st.rerun()
    
    with c2:
        st.subheader("🚪 Admission Gate")
        pending = get_pending_players()
        approved = get_approved_players()
        
        st.metric("Approved Players", len(approved))
        
        if pending:
            st.warning(f"{len(pending)} Pending Requests:")
            for p in pending:
                col_p1, col_p2 = st.columns([3, 1])
                col_p1.write(f"**{p['user_id']}**")
                if col_p2.button("Admit", key=f"admit_{p['user_id']}"):
                    approve_player(p['user_id'])
                    st.rerun()
        else:
            st.info("No pending requests.")

# 2. INPUT (Moderation)
elif phase == "INPUT":
    st.subheader("📝 Moderation Phase")
    
    # 1. Fetch Data
    def get_inputs(): return conn.table("player_inputs").select("*").eq("question_id", q_id).execute().data
    inputs = run_safe(get_inputs) or []
    
    approved = get_approved_players()
    total_players = len(approved)
    submitted_count = len(inputs)
    
    st.metric("Submissions", f"{submitted_count} / {total_players}")
    
    # 2. CHECK: Is everyone finished?
    if submitted_count < total_players:
        # CASE A: Still Waiting -> Block Editing
        st.warning(f"⚠️ Waiting for {total_players - submitted_count} more player(s)...")
        st.info("Editing will unlock automatically when everyone has submitted.")
        
        # Show who has finished so you can yell at slow players
        if inputs:
            submitted_names = [i['user_id'] for i in inputs]
            st.write(f"✅ **Received:** {', '.join(submitted_names)}")
            
        # Optional: "Force Unlock" button in case a player disconnects/leaves
        if st.button("⚠️ Force Unlock (Someone left)"):
            # This is a hack to bypass the check if needed
            st.session_state.force_unlock = True
            st.rerun()

    else:
        # CASE B: Everyone Finished (or Forced) -> Show Edit Form
        st.success("🎉 All answers received! You may now edit and start voting.")
        
        with st.form("mod_form"):
            st.write("Edit bluffs before voting (Fix typos):")
            edited_data = {}
            
            for row in inputs:
                # Unique key ensures no crashes
                val = st.text_input(
                    f"{row['user_id']}'s answer:", 
                    value=row['answer_text'],
                    key=f"edit_{row['id']}" 
                )
                edited_data[row['id']] = val
                
            if st.form_submit_button("✅ Save & Start Voting"):
                # Update DB
                for db_id, new_text in edited_data.items():
                    def update_op(did=db_id, txt=new_text):
                        conn.table("player_inputs").update({"answer_text": txt}).eq("id", did).execute()
                    run_safe(update_op)
                
                # Log Event
                log_event(q_id, "BLUFFS_FINALIZED", edited_data)
                
                update_state({"phase": "VOTING"})
                st.rerun()

# 3. VOTING
elif phase == "VOTING":
    st.subheader("🗳️ Voting in Progress")
    
    def get_votes(): return conn.table("player_votes").select("*").eq("question_id", q_id).execute().data
    votes = run_safe(get_votes) or []
    
    approved = get_approved_players()
    st.metric("Votes Cast", f"{len(votes)} / {len(approved)}")
    
    if len(votes) >= len(approved):
        st.success("All votes in!")
        if st.button("Reveal Results"):
            # Log Scores Snapshot
            scores = calculate_scores_snapshot()
            log_event(q_id, "SCORES_END_ROUND", scores)
            
            update_state({"phase": "RESULTS"})
            st.rerun()

# 4. RESULTS
elif phase == "RESULTS":
    st.subheader("📊 Results & Reveal")
    st.success("Results are live on player screens.")
    
    def get_all_qs(): return conn.table("questions").select("*").execute().data
    qs = run_safe(get_all_qs) or []
    
    curr_idx = next((i for i, q in enumerate(qs) if q["id"] == q_id), -1)
    
    if curr_idx + 1 < len(qs):
        next_q = qs[curr_idx + 1]
        if st.button(f"⏭️ Next: {next_q['question_text']}"):
            update_state({"phase": "INPUT", "current_question_id": next_q['id']})
            st.rerun()
    else:
        st.balloons()
        st.write("🎉 Game Over! Final scores are in the sidebar.")
        if st.button("Return to Lobby"):
            update_state({"phase": "LOBBY"})
            st.rerun()

time.sleep(2)
st.rerun()


