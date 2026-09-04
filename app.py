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
# 🤖 AUTOMATED NFLVERSE DATA STREAM PIPELINE
# ==========================================
def automated_nfl_pipeline():
    """Calculates active week framework and syncs schedule matrix using open nflverse datasets"""
    now = datetime.datetime.now(datetime.timezone.utc)
    
    # 🗓️ AUTOMATIC TUESDAY WEEK SWITCHER
    # NFL Season tracking anchors (Adapts dynamically to the current calendar date)
    start_date = datetime.datetime(2026, 9, 9, tzinfo=datetime.timezone.utc)
    if now < start_date:
        current_week = 1
    else:
        days_since_start = (now - start_date).days
        # Divide by 7 days per week. Tuesday represents the milestone boundary transition.
        current_week = min(18, max(1, (days_since_start // 7) + 1))
    
    # 📡 LIVE CSV DATA CARRIER (Bypasses firewalls completely)
    csv_url = "https://github.com"
    try:
        df = pd.read_csv(csv_url)
        # Filter down strictly to regular season records matching your target week timeline
        df_week = df[(df['game_type'] == 'REG') & (df['week'] == current_week)]
        
        for _, row in df_week.iterrows():
            game_id = str(row['game_id'])
            home = str(row['home_team'])
            away = str(row['away_team'])
            
            # Map standard timestamps
            g_date = row['gameday']
            g_time = row['gametime'] if pd.notna(row['gametime']) else "13:00"
            game_time = f"{g_date}T{g_time}:00Z"
            
            # Detect live vs final metrics
            h_score = row['home_score']
            a_score = row['away_score']
            
            winner = None
            status = "SCHEDULED"
            
            if pd.notna(h_score) and pd.notna(a_score):
                status = "FINAL" # nflverse switches fields to final on match verification completion
                if int(h_score) > int(a_score): winner = "HOME"
                elif int(a_score) > int(h_score): winner = "AWAY"
                else: winner = "TIE"
                
            # Check if game is currently in-progress based on timeline windows
            g_datetime = datetime.datetime.fromisoformat(game_time.replace("Z", "+00:00"))
            if status == "SCHEDULED" and now > g_datetime:
                status = "LIVE"

            payload = {
                'id': game_id,
                'week_number': current_week,
                'home_team': home,
                'away_team': away,
                'home_logo': f"https://espncdn.com{home.lower()}.png",
                'away_logo': f"https://espncdn.com{away.lower()}.png",
                'game_time': game_time,
                'status': status,
                'winner': winner
            }
            supabase.table('matchups').upsert(payload).execute()
            
    except Exception:
        pass # If GitHub is temporarily down, the app skips gracefully to keep the app loading fast
    
    return current_week

# Fire live background update sequence
active_week = automated_nfl_pipeline()

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
                    st.session_state.display_name = profile.data["display_name"] if profile.data else email.split("@")
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
        
    ui_tabs = st.tabs(tabs_list)

    # ------------------------------------------
    # TAB 1: USER PICK ENTRY FORM
    # ------------------------------------------
    with ui_tabs[0]:
        response = supabase.table("matchups").select("*").eq("week_number", active_week).order("game_time").execute()
        games = response.data

        if not games:
            st.info("🏈 Schedule pipeline initializing data structures. Please refresh the page in 5 seconds...")
        else:
            st.header(f"NFL Week {active_week} Match Selections")
            
            pay_check = supabase.table("weekly_payments").select("paid").eq("user_id", st.session_state.user_id).eq("week_number", active_week).execute()
            has_paid = pay_check.data["paid"] if pay_check.data else False

            # --- VENMO LOCK GATEWAY ---
            if not has_paid:
                st.warning("⚠️ Weekly Entry Fee Required")
                st.markdown(f"To unlock your entry sheet for **Week {active_week}**, there is a required **\$5.00 entry fee**.")
                
                venmo_note = f"Week {active_week} NFL Pick'em - {st.session_state.display_name}"
                encoded_note = urllib.parse.quote(venmo_note)
                venmo_url = f"https://venmo.com{VENMO_USERNAME}&amount=5.00&note={encoded_note}"
                
                st.markdown(f'<a href="{venmo_url}" target="_blank"><button style="background-color:#008CBA; color:white; border:none; padding:10px 20px; font-size:16px; border-radius:5px; cursor:pointer; width:100%;">💸 Pay $5.00 on Venmo</button></a>', unsafe_allow_html=True)
                
                confirm_payment = st.checkbox("I verify I have sent my $5.00 buy-in via Venmo")
                if confirm_payment:
                    if st.button("Unlock My Pick Sheet"):
                        supabase.table("weekly_payments").upsert({"user_id": st.session_state.user_id, "week_number": active_week, "paid": True}).execute()
                        st.success("Form Unlocked!")
                        st.rerun()
                st.divider()
                st.info("🔒 Matchup selections are hidden until payment verification is completed above.")

            # --- RENDER MATCHUPS ---
            if has_paid:
                st.caption("Picks lock individually exactly at each game's kickoff time.")
                user_picks_res = supabase.table("picks").select("matchup_id", "selected_team").eq("user_id", st.session_state.user_id).execute()
