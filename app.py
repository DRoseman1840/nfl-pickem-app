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
# 2. SCREEN 1: SECURE AUTHENTICATION
# ==========================================
if not st.session_state.authenticated:
    st.title("🏈 CDW & Cisco NFL Pick'em Pool")
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
                    
                    # 🔧 FIX: Safely pull row [0] out of the list wrapper
                    profile = supabase.table("profiles").select("display_name").eq("id", res.user.id).execute()
                    if profile.data and len(profile.data) > 0:
                        st.session_state.display_name = profile.data[0]["display_name"]
                    else:
                        st.session_state.display_name = email.split("@")[0]
                        
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

    # ------------------------------------------
    # TAB 3: ADMIN MANAGE PANEL
    # ------------------------------------------
    if st.session_state.user_email.strip().lower() == ADMIN_EMAIL.strip().lower():
        with ui_tabs[-1]:  # 🔧 FIX: Explicitly target the last tab slot safely
            st.header("⚙️ Admin Payment Audit Panel")
            st.caption("Cross-reference your real Venmo feed. Toggle payment access manually to lock or unlock users instantly.")
            
            # Safely query existing matchups to find the active week number
            games_check = supabase.table("matchups").select("week_number").limit(1).execute()
            adm_current_week = games_check.data[0]["week_number"] if games_check.data else 1
            
            st.write(f"Auditing Payment Status for: **Week {adm_current_week}**")
            st.divider()

            try:
                # Fetch all registered user profiles
                profiles_res = supabase.table("profiles").select("id", "display_name").execute()
                users_list = profiles_res.data if profiles_res.data else []
                
                # Fetch payment logs for this week
                payments_res = supabase.table("weekly_payments").select("user_id", "paid").eq("week_number", adm_current_week).execute()
                paid_map = {p["user_id"]: p["paid"] for p in payments_res.data} if payments_res.data else {}
                
                if not users_list:
                    st.info("No players have registered accounts in your pool yet.")
                else:
                    for user in users_list:
                        u_id = user["id"]
                        u_name = user["display_name"]
                        is_user_paid = paid_map.get(u_id, False)
                        
                        col_n, col_s = st.columns(2)
                        with col_n:
                            st.write(f"👤 **{u_name}**")
                        with col_s:
                            lbl = "✅ Paid (Click to Lock)" if is_user_paid else "❌ Unpaid (Click to Force Approve)"
                            if st.button(lbl, key=f"adm_p_{u_id}"):
                                supabase.table("weekly_payments").upsert({
                                    "user_id": u_id,
                                    "week_number": adm_current_week,
                                    "paid": not is_user_paid
                                }).execute()
                                st.success(f"Updated status for {u_name}!")
                                st.rerun()
            except Exception as admin_err:
                st.error(f"Admin Interface Error: {str(admin_err)}")


    # ------------------------------------------
    # TAB 1: USER PICK ENTRY FORM
    # ------------------------------------------
    with ui_tabs[0]:
        response = supabase.table("matchups").select("*").order("game_time").execute()
        games = response.data

        if not games:
            st.info("🏈 Awaiting matchups dataset loading. Please use your database SQL editor script tool to populate Week 1 matchups.")
        else:
            current_week = games[0]["week_number"] if games else 1
            st.header(f"NFL Week {current_week} Match Selections")


                        # 🔧 FIX: Pull row [0] safely for the payment check
            pay_check = supabase.table("weekly_payments").select("paid").eq("user_id", st.session_state.user_id).eq("week_number", current_week).execute()
            has_paid = pay_check.data[0]["paid"] if (pay_check.data and len(pay_check.data) > 0) else False

            # --- VENMO LOCK GATEWAY ---
            if not has_paid:
                st.warning("⚠️ Weekly Entry Fee Required")
                st.markdown(f"To unlock your entry sheet for **Week {current_week}**, there is a required **\$5.00 entry fee**.")

                # 🎯 FIX: Explicitly enforce the "?" hook boundary to allow mobile devices to auto-route params
                venmo_note = f"Week {current_week} NFL Pickem - {st.session_state.display_name}"
                encoded_note = urllib.parse.quote(venmo_note)
                venmo_url = f"https://venmo.com/{VENMO_USERNAME}?txn=pay&amount=5.00&note={encoded_note}"
                
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
                user_picks_res = supabase.table("picks").select("matchup_id", "selected_team").eq("user_id", st.session_state.user_id).execute()
                saved_picks = {p["matchup_id"]: p["selected_team"] for p in user_picks_res.data}

                current_time = datetime.datetime.now(datetime.timezone.utc)
                
                for game in games:
                    game_time = datetime.datetime.fromisoformat(game["game_time"].replace("Z", "+00:00"))
                    is_locked = current_time > game_time
                    existing_pick = saved_picks.get(game["id"], None)
                    
                    default_idx = 0
                    if existing_pick == game["home_team"]:
                        default_idx = 1

                    with st.container(border=True):
                        c1, c2, c3 = st.columns()
                        with c1:
                            if game.get("away_logo"): st.image(game["away_logo"], width=30)
                            st.write(f"**{game['away_team']}**")
                        with c2:
                            if game["status"] == "LIVE":
                                st.markdown("<p style='text-align:center;color:red;font-weight:bold;'>🔴 LIVE</p>", unsafe_allow_html=True)
                            elif game["status"] == "FINAL":
                                st.markdown("<p style='text-align:center;color:gray;font-weight:bold;'>🏁 FINAL</p>", unsafe_allow_html=True)
                            else:
                                st.markdown("<p style='text-align:center;font-weight:bold;margin-top:10px;'>@</p>", unsafe_allow_html=True)
                        with c3:
                            if game.get("home_logo"): st.image(game["home_logo"], width=30)
                            st.write(f"**{game['home_team']}**")

                        if is_locked:
                            st.markdown(f"🔒 **Locked** | Your Choice: `{existing_pick if existing_pick else 'None'}`")
                            if game["status"] == "FINAL":
                                if game["winner"] == "TIE":
                                    st.warning("Game ended in a Tie!")
                                else:
                                    win_team = game["home_team"] if game["winner"] == "HOME" else game["away_team"]
                                    if existing_pick == win_team:
                                        st.success(f"✅ Correct!")
                                    else:
                                        st.error(f"❌ Incorrect.")
                        else:
                            choice = st.radio(
                                f"Select Winner for {game['id']}:",
                                options=[game["away_team"], game["home_team"]],
                                index=default_idx,
                                key=f"sel_{game['id']}",
                                horizontal=True,
                                label_visibility="collapsed"
                            )                                  

                            if choice != existing_pick:
                                supabase.table("picks").upsert({
                                    "user_id": st.session_state.user_id,
                                      "matchup_id": game["id"],
                                    "selected_team": choice,
                                    "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                                }).execute()  # 👈 Parenthesis is now closed correctly here!
                                st.toast(f"Saved: {choice}!", icon="💾")
