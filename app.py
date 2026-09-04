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

# Track authentication state
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_email" not in st.session_state:
    st.session_state.user_email = ""
if "user_id" not in st.session_state:
    st.session_state.user_id = ""
if "display_name" not in st.session_state:
    st.session_state.display_name = ""

# ==========================================
# 🤖 EMBEDDED AUTOMATIC SYNC SYSTEM (No GitHub Needed!)
# ==========================================
def background_nfl_sync():
    """Fetches real-time scores/games from ESPN and caches them inside Supabase"""
    index_url = 'https://espn.com'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
    }
    try:
        res = requests.get(index_url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            week_number = data.get('week', {}).get('number', 1)
            events = data.get('events', [])
            
            for event in events:
                try:
                    game_id = event['id']
                    competition = event['competitions'][0]
                    game_time = competition['date']
                    
                    status_name = event['status']['type']['name']
                    status = 'SCHEDULED'
                    if 'STATUS_IN_PROGRESS' in status_name:
                        status = 'LIVE'
                    elif 'STATUS_FINAL' in status_name:
                        status = 'FINAL'
                        
                    teams = competition['competitors']
                    home_node = next(t for t in teams if t['homeAway'] == 'home')
                    away_node = next(t for t in teams if t['homeAway'] == 'away')
                    
                    home_team = home_node['team']['abbreviation']
                    home_logo = home_node['team'].get('logo', '')
                    away_team = away_node['team']['abbreviation']
                    away_logo = away_node['team'].get('logo', '')
                    
                    winner = None
                    if status == 'FINAL':
                        if home_node.get('winner') is True:
                            winner = 'HOME'
                        elif away_node.get('winner') is True:
                            winner = 'AWAY'
                        else:
                            winner = 'TIE'

                    matchup_data = {
                        'id': game_id,
                        'week_number': int(week_number),
                        'home_team': home_team,
                        'away_team': away_team,
                        'home_logo': home_logo,
                        'away_logo': away_logo,
                        'game_time': game_time,
                        'status': status,
                        'winner': winner
                    }
                    supabase.table('matchups').upsert(matchup_data).execute()
                except Exception:
                    continue
    except Exception:
        pass # Silently proceed if ESPN fails to keep app smooth

# Run background sync seamlessly on app refresh
background_nfl_sync()

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
                        st.success("Account created successfully! You can now log in.")
                except Exception as e:
                    st.error(f"Registration error: {str(e)}")
            else:
                st.warning("All registration fields are required.")

# ==========================================
# 4. SCREEN 2: THE MAIN APPLICATION
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
        tabs_list.append("⚙️ Admin Payment Panel")
        
    tabs = st.tabs(tabs_list)

    # ------------------------------------------
    # TAB 1: SUBMIT WEEKLY PICKS
    # ------------------------------------------
    with tabs[0]:
        response = supabase.table("matchups").select("*").order("game_time").execute()
        games = response.data

        if not games:
            st.info("Gathering live schedule updates. Please refresh the page in 5 seconds!")
        else:
            current_week = games[0]["week_number"] if games else 1
            st.header(f"NFL Week {current_week} Match Selections")
            
            pay_check = supabase.table("weekly_payments").select("paid").eq("user_id", st.session_state.user_id).eq("week_number", current_week).execute()
            has_paid = pay_check.data[0]["paid"] if pay_check.data else False

            # --- VENMO FEE GATEWAY ---
            if not has_paid:
                st.warning("⚠️ Weekly Entry Fee Required")
                st.markdown(f"To submit or edit your picks for **Week {current_week}**, there is a **\$5.00 buy-in**.")
                
                venmo_note = f"Week {current_week} NFL Pick'em - {st.session_state.display_name}"
                encoded_note = urllib.parse.quote(venmo_note)
                venmo_url = f"https://venmo.com{VENMO_USERNAME}&amount=5.00&note={encoded_note}"
                
                st.markdown(f'<a href="{venmo_url}" target="_blank"><button style="background-color:#008CBA; color:white; border:none; padding:10px 20px; font-size:16px; border-radius:5px; cursor:pointer; width:100%;">💸 Pay $5.00 on Venmo</button></a>', unsafe_allow_html=True)
                st.caption(f"Venmo note will automatically send as: *\"{venmo_note}\"*")
                
                confirm_payment = st.checkbox("I have sent my $5.00 payment via Venmo")
                if confirm_payment:
                    if st.button("Unlock My Pick Sheet"):
                        supabase.table("weekly_payments").upsert({
                            "user_id": st.session_state.user_id,
                            "week_number": current_week,
                            "paid": True
                        }).execute()
                        st.success("Form Unlocked! Happy picking.")
                        st.rerun()
                        
                st.divider()
                st.info("🔒 The entry form remains locked below until the payment verification step is acknowledged above.")
            
            # --- THE ACTIVE ENTRY FORM ---
            st.caption("Picks lock individually exactly at each game's kickoff time.")
            user_picks_res = supabase.table("picks").select("matchup_id", "selected_team").eq("user_id", st.session_state.user_id).execute()
            saved_picks = {p["matchup_id"]: p["selected_team"] for p in user_picks_res.data}

            current_time = datetime.datetime.now(datetime.timezone.utc)
            
            for game in games:
                game_time = datetime.datetime.fromisoformat(game["game_time"].replace("Z", "+00:00"))
                is_locked = current_time > game_time
