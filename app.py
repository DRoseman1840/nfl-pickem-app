import streamlit as st
import datetime
from supabase import create_client

# 1. Initialize Database Connection
SUPABASE_URL = "https://supabase.co"
SUPABASE_KEY = "your-anon-public-key"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="NFL Pick'em Pool", page_icon="🏈", layout="centered")
st.title("🏈 Weekly NFL Pick'em Pool")

# 2. Simple User Context (Entry Log-In)
if "user_name" not in st.session_state:
    st.session_state.user_name = ""

if not st.session_state.user_name:
    st.subheader("Welcome! Please enter your name to start picking:")
    name_input = st.text_input("Your Display Name")
    if st.button("Enter App"):
        if name_input.strip():
            # Check if profile exists, or create a mock/light session context
            st.session_state.user_name = name_input.strip()
            st.rerun()
        else:
            st.error("Name cannot be blank!")
else:
    st.sidebar.write(f"Logged in as: **{st.session_state.user_name}**")
    if st.sidebar.button("Log Out"):
        st.session_state.user_name = ""
        st.rerun()

    # 3. Main Dashboard: Fetch current games from database
    st.header("Make Your Selections")
    
    # Query database for matchups (Automatically adjusts if it's 16, 14, or 13 games due to byes!)
    # In a production app, fetch the active week dynamically
    response = supabase.table("matchups").select("*").order("game_time").execute()
    games = response.data

    if not games:
        st.info("The automated script is currently populating this week's matches. Please check back shortly!")
    else:
        current_time = datetime.datetime.now(datetime.timezone.utc)
        
        # Display each game as a beautiful card layout
        for game in games:
            game_time = datetime.datetime.fromisoformat(game["game_time"].replace("Z", "+00:00"))
            is_locked = current_time > game_time
            
            with st.container(border=True):
                col1, col2, col3 = st.columns([2, 1, 2])
                
                with col1:
                    if game["away_logo"]:
                        st.image(game["away_logo"], width=50)
                    st.write(f"**{game['away_team']}** (Away)")
                    
                with col2:
                    st.markdown("<h3 style='text-align: center;'>@</h3>", unsafe_allow_html=True)
                    
                with col3:
                    if game["home_logo"]:
                        st.image(game["home_logo"], width=50)
                    st.write(f"**{game['home_team']}** (Home)")

                # Lock validation logic
                if is_locked:
                    st.caption(f"🔒 Locked (Started: {game_time.strftime('%b %d, %I:%M %p')})")
                else:
                    # Provide team picking options
                    pick = st.radio(
                        f"Choose Winner for Game {game['id']}:",
                        options=[game["away_team"], game["home_team"]],
                        key=f"pick_{game['id']}",
                        horizontal=True
                    )
                    
                    if st.button("Submit Pick", key=f"btn_{game['id']}"):
                        # Logic to save selection into 'picks' table via Supabase
                        st.success(f"Saved pick: {pick}!")

        # 4. Global Standings Standings Tab
        st.divider()
        st.header("🏆 Live Leaderboard")
        # Direct select query to our live SQL View
        leaderboard_data = supabase.table("leaderboard").select("*").execute()
        if leaderboard_data.data:
            st.table(leaderboard_data.data)
        else:
            st.caption("Leaderboard will populate once the first wave of games finish!")
