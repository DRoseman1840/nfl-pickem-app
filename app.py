import streamlit as st
import datetime
import urllib.parse
import html
from zoneinfo import ZoneInfo
from supabase import create_client, Client

# ==========================================
# 1. GLOBAL APP CONFIGURATION
# ==========================================
# Credentials now come from Streamlit secrets instead of being hardcoded.
# Locally: create .streamlit/secrets.toml (already gitignored by default) with:
#   SUPABASE_URL = "https://txgwpaaaecbxivzuosmr.supabase.co"
#   SUPABASE_KEY = "your-anon-key"
#   ADMIN_EMAIL = "drose1840@gmail.com"
# On Streamlit Community Cloud: set the same keys under App settings > Secrets.
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
VENMO_USERNAME = "Derek-Roseman"  # Do NOT include the "@" symbol here
ADMIN_EMAIL = st.secrets.get("ADMIN_EMAIL", "drose1840@gmail.com")

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


def get_current_week() -> int:
    """The current week is the earliest week that still has a non-FINAL game.
    Once every game in a week is FINAL, we roll forward to the next week.
    Falls back to the highest known week number if everything is finished."""
    upcoming = (
        supabase.table("matchups")
        .select("week_number")
        .neq("status", "FINAL")
        .order("game_time")
        .limit(1)
        .execute()
    )
    if upcoming.data:
        return upcoming.data[0]["week_number"]

    latest = (
        supabase.table("matchups")
        .select("week_number")
        .order("week_number", desc=True)
        .limit(1)
        .execute()
    )
    return latest.data[0]["week_number"] if latest.data else 1


# ==========================================
# 2. SCREEN 1: SECURE AUTHENTICATION
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

# ==========================================
# 3. SCREEN 2: MAIN POOL INTERFACE
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
    if st.session_state.user_email.strip().lower() == ADMIN_EMAIL.strip().lower():
        tabs_list.append("⚙️ Admin Panel")

    ui_tabs = st.tabs(tabs_list)

    # ------------------------------------------
    # TAB 1: USER PICK ENTRY FORM
    # ------------------------------------------
    with ui_tabs[0]:
        current_week = get_current_week()
        response = (
            supabase.table("matchups")
            .select("*")
            .eq("week_number", current_week)
            .order("game_time")
            .execute()
        )
        games = response.data

        if not games:
            st.info(
                "🏈 No matchups loaded for this week yet. Run `fetch_schedule.py` "
                "(or wait for the scheduled GitHub Action) to pull the current week's games."
            )
        else:
            st.header(f"NFL Week {current_week} Match Selections")

            pay_check = supabase.table("weekly_payments").select("paid").eq("user_id", st.session_state.user_id).eq("week_number", current_week).execute()
            has_paid = pay_check.data[0]["paid"] if (pay_check.data and len(pay_check.data) > 0) else False

            # --- VENMO LOCK GATEWAY ---
            if not has_paid:
                st.warning("⚠️ Weekly Entry Fee Required")
                st.markdown(f"To unlock your entry sheet for **Week {current_week}**, there is a required **\$5.00 entry fee**.")

                venmo_note = f"Week {current_week} NFL Pickem - {st.session_state.display_name}"
                encoded_note = urllib.parse.quote(venmo_note)
                # Fixed missing "/" between the domain and username (this was broken before).
                venmo_url = f"https://venmo.com/{VENMO_USERNAME}?txn=pay&amount=5.00&note={encoded_note}"

                st.markdown(f'<a href="{venmo_url}" target="_blank"><button style="background-color:#008CBA; color:white; border:none; padding:10px 20px; font-size:16px; border-radius:5px; cursor:pointer; width:100%;">💸 Pay $5.00 on Venmo</button></a>', unsafe_allow_html=True)

                confirm_payment = st.checkbox("I verify I have sent my $5.00 buy-in via Venmo")
                if confirm_payment:
                    if st.button("Unlock My Pick Sheet"):
                        supabase.table("weekly_payments").upsert({"user_id": st.session_state.user_id, "week_number": current_week, "paid": True}, on_conflict="user_id,week_number").execute()
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

                    with st.container(border=True):
                        eastern_time = game_time.astimezone(ZoneInfo("America/New_York"))
                        st.caption(f"🕒 {eastern_time.strftime('%a %b %d, %I:%M %p')} ET")

                        c1, c2, c3 = st.columns(3)
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
                            existing_pick = saved_picks.get(game["id"], "No Selection")
                            st.markdown(f"🔒 **Locked** | Your Choice: `{existing_pick}`")
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
                            existing_pick = saved_picks.get(game["id"], None)
                            options_list = ["Select Team", game["away_team"], game["home_team"]]

                            default_idx = 0
                            if existing_pick == game["away_team"]:
                                default_idx = 1
                            elif existing_pick == game["home_team"]:
                                default_idx = 2

                            choice = st.radio(
                                f"Select Winner for {game['id']}:",
                                options=options_list,
                                index=default_idx,
                                key=f"sel_{game['id']}",
                                horizontal=True,
                                label_visibility="collapsed"
                            )
                            if choice != "Select Team" and choice != existing_pick:
                                supabase.table("picks").upsert({
                                    "user_id": st.session_state.user_id,
                                    "matchup_id": game["id"],
                                    "selected_team": choice,
                                    "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                                }, on_conflict="user_id,matchup_id").execute()
                                st.toast(f"Saved: {choice}!", icon="💾")

    # ------------------------------------------
    # TAB 2: LEADERBOARD (weekly winner + season ranking)
    # ------------------------------------------
    with ui_tabs[1]:
        st.header("🏆 Pool Standings")

        # --- Season standings ---
        st.subheader("📅 Season Ranking")
        try:
            season_res = supabase.table("season_scores").select("*").order("season_rank").execute()
            if season_res.data:
                season_display = [
                    {
                        "Rank": row["season_rank"],
                        "Player": row["display_name"],
                        "Total Points": row["total_points"],
                    }
                    for row in season_res.data
                ]
                st.dataframe(season_display, hide_index=True, use_container_width=True)
            else:
                st.info("Season standings will appear once the first games are final.")
        except Exception as e:
            st.caption(f"Waiting for match completions to rank players. ({e})")

        st.divider()

        # --- Weekly standings, with a week picker ---
        st.subheader("🗓️ Weekly Results")
        try:
            weeks_res = supabase.table("matchups").select("week_number").execute()
            week_options = sorted({row["week_number"] for row in weeks_res.data})
        except Exception:
            week_options = []

        if not week_options:
            st.info("No weeks available yet.")
        else:
            default_week_index = week_options.index(current_week) if current_week in week_options else 0
            selected_week = st.selectbox("Select Week", week_options, index=default_week_index)

            week_matchups = supabase.table("matchups").select("*").eq("week_number", selected_week).execute().data
            matchup_by_id = {m["id"]: m for m in week_matchups}
            matchup_ids = list(matchup_by_id.keys())

            week_picks = (
                supabase.table("picks").select("user_id, matchup_id, selected_team").in_("matchup_id", matchup_ids).execute().data
                if matchup_ids else []
            )
            all_profiles = supabase.table("profiles").select("id, display_name").execute().data
            name_by_id = {p["id"]: p["display_name"] for p in all_profiles}

            picks_by_user = {}
            for pk in week_picks:
                picks_by_user.setdefault(pk["user_id"], []).append(pk)

            if not picks_by_user:
                st.info(f"No picks recorded yet for Week {selected_week}.")
            else:
                player_rows = []
                for user_id, user_picks in picks_by_user.items():
                    correct_logos, incorrect_logos, points = [], [], 0
                    for pk in user_picks:
                        m = matchup_by_id.get(pk["matchup_id"])
                        if not m or m["status"] != "FINAL" or not m.get("winner") or m["winner"] == "TIE":
                            continue  # only completed, decisive games count toward correct/incorrect
                        win_team = m["home_team"] if m["winner"] == "HOME" else m["away_team"]
                        pick_team = pk["selected_team"]
                        logo = m.get("home_logo") if pick_team == m["home_team"] else m.get("away_logo") if pick_team == m["away_team"] else None
                        if pick_team == win_team:
                            points += 1
                            if logo: correct_logos.append(logo)
                        elif logo:
                            incorrect_logos.append(logo)
                    player_rows.append({
                        "display_name": name_by_id.get(user_id, "Unknown Player"),
                        "correct_logos": correct_logos,
                        "incorrect_logos": incorrect_logos,
                        "points": points,
                    })

                player_rows.sort(key=lambda r: r["points"], reverse=True)
                prev_points, current_rank = None, 0
                for i, row in enumerate(player_rows, start=1):
                    if row["points"] != prev_points:
                        current_rank = i
                    row["rank"] = current_rank
                    prev_points = row["points"]

                if player_rows:
                    top_score = player_rows[0]["points"]
                    winners = [r["display_name"] for r in player_rows if r["points"] == top_score]
                    st.success(f"🥇 Week {selected_week} Winner{'s' if len(winners) > 1 else ''}: **{', '.join(winners)}** ({top_score} pts)")

                def logo_cell(urls):
                    if not urls:
                        return "—"
                    return "".join(f'<img src="{u}" style="height:22px;margin-right:4px;vertical-align:middle;" />' for u in urls)

                rows_html = ""
                for row in player_rows:
                    name = html.escape(row["display_name"])
                    rows_html += (
                        "<tr style='border-bottom:1px solid #333;'>"
                        f"<td style='padding:8px;'>{row['rank']}</td>"
                        f"<td style='padding:8px;'>{name}</td>"
                        f"<td style='padding:8px;'>{logo_cell(row['correct_logos'])}</td>"
                        f"<td style='padding:8px;'>{logo_cell(row['incorrect_logos'])}</td>"
                        f"<td style='padding:8px;text-align:center;'>{row['points']}</td>"
                        "</tr>"
                    )

                table_html = f"""
                <table style="width:100%;border-collapse:collapse;">
                <thead>
                <tr style="border-bottom:2px solid #666;">
                <th style="text-align:left;padding:8px;">Rank</th>
                <th style="text-align:left;padding:8px;">Player</th>
                <th style="text-align:left;padding:8px;">Correct</th>
                <th style="text-align:left;padding:8px;">Incorrect</th>
                <th style="text-align:center;padding:8px;">Points</th>
                </tr>
                </thead>
                <tbody>{rows_html}</tbody>
                </table>
                """
                st.markdown(table_html, unsafe_allow_html=True)
                st.caption("Correct/Incorrect logos only appear once a game goes FINAL — picks for upcoming games aren't scored yet.")

    # ------------------------------------------
    # TAB 3: ADMIN MANAGE PANEL
    # ------------------------------------------
    if st.session_state.user_email.strip().lower() == ADMIN_EMAIL.strip().lower():
        with ui_tabs[2]:
            st.header("⚙️ Admin Panel")

            # --- Payment audit, by week ---
            st.subheader("💸 Payment Audit")
            st.caption("Cross-reference your real Venmo feed. Toggle payment access manually to lock or unlock users instantly.")

            try:
                adm_weeks_res = supabase.table("matchups").select("week_number").execute()
                adm_week_options = sorted({row["week_number"] for row in adm_weeks_res.data})
            except Exception:
                adm_week_options = []

            adm_current_week = get_current_week()

            if not adm_week_options:
                st.info("No weeks loaded yet.")
            else:
                adm_default_idx = adm_week_options.index(adm_current_week) if adm_current_week in adm_week_options else 0
                adm_selected_week = st.selectbox("Auditing Week", adm_week_options, index=adm_default_idx, key="adm_week_select")

                try:
                    users_res = supabase.table("profiles").select("id", "display_name").execute()
                    users_list = users_res.data if users_res.data else []

                    payments_res = supabase.table("weekly_payments").select("user_id", "paid").eq("week_number", adm_selected_week).execute()
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
                                if st.button(lbl, key=f"adm_p_{u_id}_{adm_selected_week}"):
                                    supabase.table("weekly_payments").upsert({
                                        "user_id": u_id,
                                        "week_number": adm_selected_week,
                                        "paid": not is_user_paid
                                    }, on_conflict="user_id,week_number").execute()
                                    st.success(f"Updated status for {u_name}!")
                                    st.rerun()
                except Exception as admin_err:
                    st.error(f"Admin Interface Error: {str(admin_err)}")

            st.divider()

            # --- Remove a player from the pool ---
            st.subheader("🗑️ Remove a Player")
            st.caption(
                "This removes the player's profile from the pool — they'll disappear from the leaderboard, "
                "payment audit, and picks list. Their login still exists in Supabase Auth; this doesn't delete "
                "their account credentials, just their participation in the pool."
            )
            try:
                removable_users = supabase.table("profiles").select("id, display_name").execute().data or []
            except Exception as e:
                removable_users = []
                st.error(f"Couldn't load player list: {e}")

            if removable_users:
                names_by_id = {u["id"]: u["display_name"] for u in removable_users}
                target_id = st.selectbox(
                    "Select a player to remove",
                    options=list(names_by_id.keys()),
                    format_func=lambda uid: names_by_id[uid],
                    key="remove_player_select",
                )
                confirm_remove = st.checkbox(f"I understand this will remove {names_by_id[target_id]} from the pool.")
                if st.button("Remove Player", type="primary", disabled=not confirm_remove):
                    try:
                        supabase.table("picks").delete().eq("user_id", target_id).execute()
                        supabase.table("weekly_payments").delete().eq("user_id", target_id).execute()
                        supabase.table("profiles").delete().eq("id", target_id).execute()
                        st.success(f"Removed {names_by_id[target_id]} from the pool.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Couldn't remove player: {e}")
