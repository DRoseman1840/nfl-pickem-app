import streamlit as st
import datetime
import urllib.parse
import requests
from supabase import create_client, Client

# ==========================================
# 1. GLOBAL APP CONFIGURATION
# ==========================================
SUPABASE_URL = "https://txgwpaaaecbxivzuosmr.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InR4Z3dwYWFhZWNieGl2enVvc21yIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODg0NzcwNTcsImV4cCI6MjEwNDA1MzA1N30.ZdQhH7u15ozbEHvIT_xB7FH7rI8h3WkUfvnWnKtlNtE"
VENMO_USERNAME = "Derek-Roseman"  # Do NOT include the "@" symbol here
ADMIN_EMAIL = "drose1840@gmail.com"  # 👈 REPLACE THIS with your personal email to unlock Admin settings

@st.cache_resource
def get_supabase_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = get_supabase_client()

st.set_page_config(page_title="NFL Pick'em Pool", page_icon="🏈", layout="centered")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_email" not in st.session_state:
    st.session_state.user_email = ""
if "user_id" not in st.session_state:
    st.session_state.user_id = ""
if "display_name" not in st.session_state:
    st.session_state.display_name = ""

# ==========================================
# 🤖 EMBEDDED NFLVERSE DATA SYNCHRONIZER 
# ==========================================
def automated_nflverse_sync():
    """Fetches real-time schedules and game results cleanly from nflverse open CDN"""
    url = "https://bigballsdata.com"
    
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            raw_data = res.json()
            
            # 🔧 FIX: Handle dictionary structures if the CDN wraps the payload
            if isinstance(raw_data, dict):
                games_list = raw_data.get("games", []) if "games" in raw_data else list(raw_data.values())
            else:
                games_list = raw_data

            # Loop through regular season matches safely
            for game in games_list:
                if not isinstance(game, dict) or game.get("season_type") != "REG":
                    continue
                    
                game_id = str(game.get("game_id"))
                week_number = int(game.get("week", 1))
                home_team = game.get("home_team")
                away_team = game.get("away_team")
                
                # Format standard kick dates 
                game_time = game.get("gameday") + "T" + game.get("gametime") + ":00Z"
                
                raw_status = game.get("status", "POST")
                status = "SCHEDULED"
                winner = None
                
                if raw_status == "FINAL" or game.get("home_score") is not None:
                    status = "FINAL"
                    h_score = int(game.get("home_score", 0))
                    a_score = int(game.get("away_score", 0))
                    if h_score > a_score:
                        winner = "HOME"
                    elif a_score > h_score:
                        winner = "AWAY"
                    else:
                        winner = "TIE"
                elif raw_status == "INGAME":
                    status = "LIVE"

                matchup_payload = {
                    'id': game_id,
                    'week_number': week_number,
                    'home_team': home_team,
                    'away_team': away_team,
                    'home_logo': f"https://espncdn.com{home_team.lower()}.png",
                    'away_logo': f"https://espncdn.com{away_team.lower()}.png",
                    'game_time': game_time,
                    'status': status,
                    'winner': winner
                }
                
                # Keep database updated in the background
                supabase.table('matchups').upsert(matchup_payload).execute()
    except Exception:
        pass # Gracefully skip processing exceptions to keep interface functional

# Fire background sync natively whenever a user touches the web portal
automated_nflverse_sync()

# ==========================================
# 3. SCREEN 1: SECURE AUTHENTICATION
# ==========================================
if not st.session_state.authenticated:
    st.title("🏈 NFL Pick'em Pool")
    st.subheader("Sign In or Register")
    
    email = st.text_input("Email Address").strip().lower()
    password = st.text_input("Password", type="password")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Log In", use_container_width=True):
            if email and password:
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state.user_id = res.user.id
                    st.session_state.user_email = res.user.email
                    profile = supabase.table("profiles").select("display_name").eq("id", res.user.id).execute()
                    st.session_state.display_name = profile.data[0]["display_name"] if profile.data else email.split("@")[0]
                    st.session_state.authenticated = True
                    st.success("Logged in successfully!")
                    st.rerun()
                except Exception as e:
                    if "Email not confirmed" in str(e):
                        st.error("🔒 Login Blocked: Check your email inbox and click the confirmation link to activate your profile.")
                    else:
                        st.error(f"Login failed: {str(e)}")
            else:
                st.warning("Please fill out both fields.")

    with col2:
        st.info("💡 New player? Enter your details above and a display name below to sign up.")
        new_name = st.text_input("Display Name (Public)", key="reg_name")
        if st.button("Create Account", use_container_width=True):
            if email and password and new_name.strip():
                try:
                    res = supabase.auth.sign_up({"email": email, "password": password})
                    if res.user:
                        supabase.table("profiles").insert({"id": res.user.id, "display_name": new_name.strip()}).execute()
                        st.markdown("---")
                        st.success("🎉 Account Created Successfully!")
                        st.info("📧 **Action Required:** Open your email inbox and click the confirmation link before attempting to log in.")
                        st.markdown("---")
                except Exception as e:
                    st.error(f"Registration error: {str(e)}")
            else:
                st.warning("All fields are required.")

# ==========================================
# 4. SCREEN 2: MAIN POOL INTERFACE
# ==========================================
else:
    st.sidebar.title("🏈 Match Center")
    st.sidebar.write(f"Logged in as: **{st.session_state.display_name}**")
    st.sidebar.caption(f"Account: {st.session_state.user_email}")
    
    if st.sidebar.button("Log Out", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_id = ""
        st.rerun()

    tabs_list = ["📝 Submit Weekly Picks", "🏆 Standings & Leaderboard"]
    if st.session_state.user_email == ADMIN_EMAIL.strip().lower():
        tabs_list.append("⚙️ Admin Panel")
        
    tabs = st.tabs(tabs_list)

    # ------------------------------------------
    # TAB 1: USER PICK ENTRY FORM
    # ------------------------------------------
    with tabs:
        # Pull current matchups from database
        response = supabase.table("matchups").select("*").order("game_time").execute()
        games = response.data

        if not games:
            st.info("🏈 Connecting to live NFL schedule data pipeline. Please refresh the page in 5 seconds...")
        else:
            # 🔧 FIX: Find the current active week by looking at today's calendar context
            today_str = datetime.date.today().isoformat()
            current_week = games[0]["week_number"]
            for g in games:
                if g["game_time"] >= today_str:
                    current_week = g["week_number"]
                    break
                    
            st.header(f"NFL Week {current_week} Match Selections")
            
            pay_check = supabase.table("weekly_payments").select("paid").eq("user_id", st.session_state.user_id).eq("week_number", current_week).execute()
            has_paid = pay_check.data[0]["paid"] if pay_check.data else False

            # --- VENMO LOCK GATEWAY ---
            if not has_paid:
                st.warning("⚠️ Weekly Entry Fee Required")
                st.markdown(f"To unlock your entry sheet for **Week {current_week}**, there is a required **\$5.00 entry fee**.")
                
                venmo_note = f"Week {current_week} NFL Pick'em - {st.session_state.display_name}"
                encoded_note = urllib.parse.quote(venmo_note)
                venmo_url = f"https://venmo.com{VENMO_USERNAME}&amount=5.00&note={encoded_note}"
                
                st.markdown(f'<a href="{venmo_url}" target="_blank"><button style="background-color:#008CBA; color:white; border:none; padding:10px 20px; font-size:16px; border-radius:5px; cursor:pointer; width:100%;">💸 Pay $5.00 on Venmo</button></a>', unsafe_allow_html=True)
                
                confirm_payment = st.checkbox("I verify I have sent my $5.00 buy-in via Venmo")
                if confirm_payment:
                    if st.button("Unlock My Pick Sheet"):
                        supabase.table("weekly_payments").upsert({"user_id": st.session_state.user_id, "week_number": current_week, "paid": True}).execute()
                        st.success("Form Unlocked!")
                        st.rerun()
                st.divider()
                st.info("🔒 Matchup selections are hidden until payment verification is completed above.")

            # --- RENDER MATCHUPS ---
            if has_paid:
                st.caption("Picks lock individually exactly at each game's kickoff time.")

