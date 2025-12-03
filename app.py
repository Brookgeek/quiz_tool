import streamlit as st
from st_supabase_connection import SupabaseConnection
import pandas as pd
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
    # Fetches the global game state (Phase + Current Question)
    response = conn.table("game_state").select("*").execute()
    if not response.data:
        # Initialize if empty
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
    # Fetch questions ordered by creation time
    response = conn.table("questions").select("*").order("created_at").execute()
    return response.data

def reset_game_data():
    # Clear answers but KEEP questions
    conn.table("quiz_answers").delete().gt("id", 0).execute()
    update_game_state("LOBBY", None)

def nuke_questions():
    # Clear ALL questions to start fresh
    conn.table("questions").delete().gt("id", 0).execute()

# --- ADMIN LOGIN SIDEBAR ---
with st.sidebar:
    st.header("🔒 Admin Access")
    if not st.session_state.admin_authenticated:
        pwd = st.text_input("Enter Admin Password", type="password")
        if st.button("Login"):
            if pwd == st.secrets["admin"]["password"]:
                st.session_state.admin_authenticated = True
                st.success("Access Granted")
                st.rerun()
            else:
                st.error("Wrong Password")
    
    # LOGOUT BUTTON
    if st.session_state.admin_authenticated:
        if st.button("Logout"):
            st.session_state.admin_authenticated = False
            st.rerun()

# --- MAIN APP ---
state = get_game_state()
phase = state['phase']
current_q_id = state.get('current_question_id')

# ==========================================
# 👑 ADMIN VIEW (Only visible if logged in)
# ==========================================
if st.session_state.admin_authenticated:
    st.markdown("---")
    st.subheader("🛠️ Host Control Panel")
    
    # 1. LOBBY PHASE: BUILD THE DECK
    if phase == "LOBBY":
        st.info("Step 1: Add all your questions for this game.")
        
        # Add Question Form
        with st.form("add_q"):
            c1, c2 = st.columns([3, 1])
            q_text = c1.text_input("Question")
            a_text = c2.text_input("Real Answer")
            if st.form_submit_button("Add to Deck"):
                if q_text and a_text:
                    conn.table("questions").insert({
                        "question_text": q_text, 
                        "correct_answer": a_text
                    }).execute()
                    st.success("Added!")
                    st.rerun()

        # Show Deck
        questions = get_all_questions()
        if questions:
            st.write(f"**Current Deck ({len(questions)} Questions):**")
            st.dataframe(pd.DataFrame(questions)[['question_text', 'correct_answer']])
            
            col1, col2 = st.columns(2)
            if col1.button("🚀 START GAME"):
                # Pick the first question automatically
                first_q = questions[0]
                update_game_state("INPUT", first_q['id'])
                st.rerun()
                
            if col2.button("🗑️ Clear All Questions"):
                nuke_questions()
                st.rerun()
        else:
            st.warning("Add at least one question to start.")

    # 2. GAME LOOP (INPUT -> VOTING -> RESULTS)
    elif phase in ["INPUT", "VOTING", "RESULTS"]:
        current_q = get_current_question(current_q_id)
        st.write(f"**Live Question:** {current_q['question_text']}")
        
        # Navigation Buttons
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
            st.markdown("### What's Next?")
            
            # Logic to find the next question
            all_qs = get_all_questions()
            current_index = next((i for i, item in enumerate(all_qs) if item["id"] == current_q_id), -1)
            
            col_next, col_end = st.columns(2)
            
            # Check if there is a next question
            if current_index + 1 < len(all_qs):
                next_q = all_qs[current_index + 1]
                if col_next.button(f"⏭️ Next: {next_q['question_text'][:20]}..."):
                    update_game_state("INPUT", next_q['id'])
                    st.rerun()
            else:
                st.success("No more questions in deck!")
            
            if col_end.button("🏁 End Game (Show Final Score)"):
                update_game_state("GAME_OVER")
                st.rerun()

    # 3. GAME OVER
    elif phase == "GAME_OVER":
        st.success("Game Finished!")
        if st.button("🔄 Start New Game (Reset)"):
            reset_game_data()
            st.rerun()

# ==========================================
# 👤 PLAYER VIEW (Visible to everyone)
# ==========================================
st.title("🎲 Dynamic Quiz")

if not st.session_state.admin_authenticated:
    # --- PHASE: LOBBY ---
    if phase == "LOBBY":
        st.info("Waiting for the host to set up the game...")
        st.image("https://media.giphy.com/media/xTkcEQACH24SMPxIQg/giphy.gif") # Waiting GIF
        
        # Login
        if "user_id" not in st.session_state:
            uid = st.text_input("Enter your Nickname to join:")
            if st.button("Join"):
                st.session_state.user_id = uid
                st.rerun()
        else:
            st.success(f"Ready as: **{st.session_state.user_id}**")

    # --- PHASE: GAME OVER ---
    elif phase == "GAME_OVER":
        st.balloons()
        st.header("🏆 Final Standings")
        
        # Calculate scores
        # (Assuming you added scoring logic in the voting phase previously, 
        # otherwise this just lists participants)
        users = conn.table("quiz_answers").select("user_id").execute().data
        unique_users = list(set([u['user_id'] for u in users]))
        st.write("Thanks for playing:", ", ".join(unique_users))

    # --- PHASE: INPUT ---
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
            else:
                st.warning("Please refresh and join in the lobby first!")

    # --- PHASE: VOTING & RESULTS ---
    elif phase in ["VOTING", "RESULTS"]:
        q_data = get_current_question(current_q_id)
        st.subheader(f"Q: {q_data['question_text']}")
        
        if phase == "VOTING":
            st.info("👀 Look at the big screen to vote!")
        else:
            st.success(f"The answer was: **{q_data['correct_answer']}**")

    # Auto-refresh for players
    time.sleep(2)
    st.rerun()
