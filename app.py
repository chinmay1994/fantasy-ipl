import streamlit as st
import pandas as pd
from datetime import datetime
import hmac
import base64
import time
import uuid
import streamlit_authenticator as stauth
from lib.google_sheets import (
    get_matches,
    get_upcoming_matches,
    get_live_matches,
    get_completed_matches,
    get_match_score,
    get_rules,
    get_scoring_rules,
    get_entries,
    get_all_teams_for_match,
    get_match_squad,
    get_player_points,
    get_all_player_points,
    save_entry,
    delete_entry,
    entry_exists,
    get_team_selections,
    clear_all_caches,
    now_ist,
    is_match_live,
    verify_user,
    add_user,
    get_users,
    get_overall_leaderboard,
    get_player_stats_for_match,
)
from lib.validators import validate_team, get_team_stats
from lib.scoring import calculate_team_total, calculate_team_with_player_scores


SECRET_KEY = st.secrets.get("SECRET_KEY", "fallback_secret_key")


@st.fragment(run_every=1)
def render_home_countdown():
    live_matches = get_live_matches()
    
    if "home_countdown" not in st.session_state:
        st.session_state.home_countdown = 60
    
    if live_matches:
        remaining = st.session_state.home_countdown
        remaining = max(0, remaining - 1)
        st.session_state.home_countdown = remaining
        
        if remaining == 0:
            st.session_state.home_countdown = 60
            try:
                st.rerun(scope="fragment")
            except:
                st.rerun()
        else:
            st.caption(f"🔄 Auto-refresh in {remaining}s")
    else:
        st.session_state.home_countdown = 60

def create_session_token(username: str) -> str:
    payload = f"{username}|{int(time.time())}"
    signature = hmac.new(SECRET_KEY.encode(), payload.encode(), "sha256").hexdigest()[:16]
    token = f"{payload}|{signature}"
    return base64.b64encode(token.encode()).decode()

def verify_session_token(token: str) -> str | None:
    try:
        decoded = base64.b64decode(token).decode()
        parts = decoded.split("|")
        if len(parts) != 3:
            return None
        username, timestamp, signature = parts
        expected_sig = hmac.new(SECRET_KEY.encode(), f"{username}|{timestamp}".encode(), "sha256").hexdigest()[:16]
        if signature != expected_sig:
            return None
        if int(time.time()) - int(timestamp) > 86400 * 30:
            return None
        return username
    except:
        return None


st.set_page_config(
    page_title="Fantasy IPL",
    page_icon="https://freesvg.org/img/1526511264.png",
    layout="wide",
)

st.markdown("""
<style>
    .block-container {padding-top: 0.5rem; padding-bottom: 0.5rem;}
    div[data-testid="stToolbar"] {top: 0px;}
</style>
""", unsafe_allow_html=True)


if "username" not in st.session_state:
    st.session_state.username = ""

if "selected_match_id" not in st.session_state:
    st.session_state.selected_match_id = None

if "selected_players" not in st.session_state:
    st.session_state.selected_players = {}

if "captain" not in st.session_state:
    st.session_state.captain = None

if "vice_captain" not in st.session_state:
    st.session_state.vice_captain = None

if "is_submitting" not in st.session_state:
    st.session_state.is_submitting = False

if "shared_match_id" not in st.session_state:
    st.session_state.shared_match_id = None

if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

if "pending_writes" not in st.session_state:
    st.session_state.pending_writes = []

def get_authenticator():
    users_df = get_users()
    credentials = {'usernames': {}}
    
    if users_df.empty:
        return stauth.Authenticate({'usernames': {}}, 'fantasy_ipl_cookie', 'fantasy_ipl_key', cookie_expiry_days=30)

    # Robust column mapping (case-insensitive)
    cols = {c.lower().replace("_", ""): c for c in users_df.columns}
    uname_col = cols.get('username')
    pword_col = cols.get('password')
    admin_col = cols.get('isadmin')
    
    admin_mapping = {}
    for _, row in users_df.iterrows():
        uname = str(row[uname_col]) if uname_col else str(row.iloc[0])
        pword = str(row[pword_col]) if pword_col else str(row.iloc[1])
        is_admin_val = str(row[admin_col]) if admin_col else (str(row.iloc[2]) if len(row) > 2 else 'FALSE')
        is_admin = is_admin_val.strip().upper() == 'TRUE'
        
        credentials['usernames'][uname] = {
            'name': uname,
            'password': pword
        }
        admin_mapping[uname] = is_admin
    
    st.session_state.admin_mapping = admin_mapping
    
    return stauth.Authenticate(
        credentials,
        'fantasy_ipl_cookie',
        'fantasy_ipl_key',
        cookie_expiry_days=30
    )

def set_cookie_safari_cloud(name, value, days=30):
    # This uses SameSite=None and Secure, which is required for Safari in iframes (Streamlit Cloud)
    expiry = (datetime.now() + timedelta(days=days)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    components.html(f"""
        <script>
            try {{
                var cookieStr = "{name}={value}; expires={expiry}; path=/; SameSite=None; Secure";
                console.log("Setting bridge cookie...");
                document.cookie = cookieStr;
                try {{
                    window.parent.document.cookie = cookieStr;
                    console.log("Parent cookie set successfully");
                }} catch(e) {{
                    console.log("Note: Parent window cookie access blocked (expected on Streamlit Cloud)");
                }}
            }} catch(e) {{
                console.log("Cookie error:", e);
            }}
        </script>
    """, height=0)

authenticator = get_authenticator()


def main():
    st.title("🏏 Fantasy IPL")
    
    if not st.session_state.username:
        # Debug: Visible on your staging app
        if hasattr(st, "context"):
            st.sidebar.write("Debug Cookies:", list(st.context.cookies.keys()))
            
        # Check native browser cookies (Safari Bridge)
        if hasattr(st, "context"):
            # Check if our Safari-specific bridge cookie exists
            bridge_token = st.context.cookies.get('safari_auth_token')
            if bridge_token:
                username = verify_session_token(bridge_token)
                if username:
                    st.session_state.username = username
                    st.session_state.is_admin = st.session_state.get('admin_mapping', {}).get(username, False)
                    # Don't rerun yet, let the authenticator also see it if possible
        
    if "match_id" in st.query_params:
        shared_id = st.query_params["match_id"]
        # If it's a new link, trigger the redirection
        if st.session_state.get("last_processed_match_id") != shared_id:
            st.session_state.shared_match_id = shared_id
            st.session_state.page = "📝 Create Team"
            st.session_state.last_processed_match_id = shared_id
            # Clear query params immediately to clean the address bar
            st.query_params.clear()
    
    if not st.session_state.username:
        with st.container():
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                tab_login, tab_signup = st.tabs(["Login", "Sign Up"])
                
                with tab_login:
                    # Use the authenticator's login widget
                    # In newer versions, login() updates session_state directly
                    authenticator.login(location='main')
                    
                    authentication_status = st.session_state.get('authentication_status')
                    username = st.session_state.get('username')
                    
                    if authentication_status:
                        st.session_state.username = username
                        st.session_state.is_admin = st.session_state.get('admin_mapping', {}).get(username, False)
                        
                        # Set the Safari Bridge cookie
                        token = create_session_token(username)
                        set_cookie_safari_cloud('safari_auth_token', token, days=30)
                        
                        # Handle deep link redirection after login
                        if st.session_state.get("shared_match_id"):
                            st.session_state.page = "📝 Create Team"
                        st.rerun()
                    elif authentication_status is False:
                        st.error("Username/password is incorrect")
                
                with tab_signup:
                    st.subheader("Create a new account")
                    with st.form("signup_form"):
                        new_username = st.text_input(
                            "Username",
                            placeholder="Choose a username",
                            label_visibility="collapsed",
                            key="signup_username",
                        )
                        new_password = st.text_input(
                            "Password",
                            type="password",
                            placeholder="Choose a password",
                            label_visibility="collapsed",
                            key="signup_password",
                        )
                        confirm_password = st.text_input(
                            "Confirm Password",
                            type="password",
                            placeholder="Confirm your password",
                            label_visibility="collapsed",
                            key="signup_confirm",
                        )
                        if st.form_submit_button("Sign Up", use_container_width=True):
                            if not new_username:
                                st.warning("Please enter a username")
                            elif not new_password:
                                st.warning("Please enter a password")
                            elif not confirm_password:
                                st.warning("Please confirm your password")
                            elif new_password != confirm_password:
                                st.error("Passwords do not match")
                            elif add_user(new_username, new_password):
                                st.success("Account created! Please login.")
                            else:
                                st.error("Username already exists")
        st.stop()
    
    st.sidebar.success(f"Logged in as: **{st.session_state.username}**")
    
    action_cols = st.sidebar.columns(3)
    with action_cols[0]:
        if st.button("🔄", key="refresh_btn"):
            clear_all_caches()
            st.rerun()
    with action_cols[2]:
        if st.button("🚪", key="logout_btn"):
            st.session_state.username = ""
            authenticator.logout(location='unrendered')
            st.rerun()
    
    if "page" not in st.session_state:
        st.session_state.page = "🏠 Home"
    
    pages = ["🏠 Home", "📝 Create Team", "📋 My Teams", "👥 All Teams", "🏆 Leaderboard"]
    live_matches = get_live_matches()
    if live_matches:
        pages.insert(1, "📊 Live Contest Stats")
        
    if st.session_state.is_admin:
        pages.append("🔧 Admin")
    current_index = pages.index(st.session_state.page) if st.session_state.page in pages else 0
    
    page = st.sidebar.radio(
        "Navigation",
        pages,
        index=current_index,
    )
    
    st.session_state.page = page
    
    if page == "🏠 Home":
        render_home()
    elif page == "📝 Create Team":
        render_create_team()
    elif page == "📋 My Teams":
        render_my_teams()
    elif page == "👥 All Teams":
        render_all_teams()
    elif page == "🏆 Leaderboard":
        render_overall_leaderboard()
    elif page == "📊 Live Contest Stats":
        render_live_stats()
    elif page == "🔧 Admin":
        render_admin()


def get_leaderboard_position(match_id: str, username: str, scoring_rules) -> tuple[int, int]:
    teams = get_all_teams_for_match(match_id)
    player_points = get_player_points(match_id)
    
    if not teams or player_points.empty:
        return 0, len(teams)
    
    scores = []
    for team in teams:
        total = calculate_team_total(team.players, player_points, scoring_rules)
        scores.append((team.user_name, total))
    
    scores.sort(key=lambda x: x[1], reverse=True)
    
    for i, (name, _) in enumerate(scores, 1):
        if name == username:
            return i, len(scores)
    
    return 0, len(scores)


def render_home():
    render_home_countdown()
    
    live_matches = get_live_matches()
    completed_matches = get_completed_matches()
    
    entries = get_entries()
    if entries.empty or "UserName" not in entries.columns:
        user_entries = pd.DataFrame()
    else:
        user_entries = entries[entries["UserName"] == st.session_state.username]
    
    scoring_rules = get_scoring_rules()
    
    if live_matches:
        st.header("🔴 Live Matches")
        
        for match in live_matches:
            score = get_match_score(match.match_id)
            st.subheader(f"📺 {score}")
            st.caption(f"Status: {match.status}")
            
            teams = get_all_teams_for_match(match.match_id)
            player_points = get_player_points(match.match_id)
            
            teams_with_scores = []
            for team in teams:
                selections = get_team_selections(team.entry_id)
                
                if player_points is not None and not player_points.empty:
                    total_points = calculate_team_total(selections, player_points, scoring_rules)
                else:
                    total_points = 0.0
                
                teams_with_scores.append((team.user_name, total_points, selections, team.entry_id))
            
            teams_with_scores.sort(key=lambda x: x[1], reverse=True)
            
            if not teams_with_scores:
                st.info("No teams submitted for this match yet.")
            else:
                for rank, (username, total_points, selections, entry_id) in enumerate(teams_with_scores, 1):
                    with st.expander(f"#{rank} 👤 {username} - {total_points:.2f} pts"):
                        role_emoji = {"WK": "🧤", "BAT": "🏏", "AR": "🔄", "BWL": "🎳"}
                        
                        is_own_team = username == st.session_state.username
                        
                        if player_points is not None and not player_points.empty:
                            _, player_scores = calculate_team_with_player_scores(selections, player_points, scoring_rules)
                            player_scores_dict = {ps.player_name: ps for ps in player_scores}
                            
                            player_data = []
                            for s in sorted(selections, key=lambda x: x.pick_no):
                                multiplier = ""
                                if s.is_captain:
                                    multiplier = " 🏆 (2x)" if is_own_team else " (C)"
                                elif s.is_vice_captain:
                                    multiplier = " 🎖️ (1.5x)" if is_own_team else " (VC)"
                                
                                ps = player_scores_dict.get(s.player_name)
                                if ps:
                                    points = ps.points
                                    stats = []
                                    if ps.runs > 0:
                                        stats.append(f"{ps.runs} runs")
                                    if ps.wickets > 0:
                                        stats.append(f"{ps.wickets} wkts")
                                    if ps.catches > 0:
                                        stats.append(f"{ps.catches} ct")
                                    stats_str = ", ".join(stats) if stats else "-"
                                else:
                                    points = 0.0
                                    stats_str = "-"
                                
                                player_data.append({
                                    "Player": f"{role_emoji.get(s.role, '❓')} {s.player_name}{multiplier}",
                                    "Pts": f"{points:.1f}",
                                    "Stats": stats_str,
                                })
                            
                            st.dataframe(
                                pd.DataFrame(player_data),
                                hide_index=True,
                                use_container_width=True,
                            )
                        else:
                            for s in sorted(selections, key=lambda x: x.pick_no):
                                multiplier = ""
                                if s.is_captain:
                                    multiplier = " 🏆 (2x)" if is_own_team else " (C)"
                                elif s.is_vice_captain:
                                    multiplier = " 🎖️ (1.5x)" if is_own_team else " (VC)"
                                emoji = role_emoji.get(s.role, "❓")
                                st.markdown(f"{emoji} {s.player_name} ({s.role}){multiplier}")
            
            st.divider()
    else:
        st.header("🏠 Dashboard")
        st.info("No live matches at the moment.")
    
    if not user_entries.empty and completed_matches:
        st.divider()
        st.header("📊 Your Recent Match Scores")
        
        user_match_ids = set(str(m) for m in user_entries["MatchID"])
        recent_completed = [m for m in completed_matches if m.match_id in user_match_ids]
        
        if not recent_completed:
            st.info("No completed matches with your entries yet.")
        else:
            recent_completed = sorted(recent_completed, key=lambda x: x.start_time, reverse=True)[:5]
            
            for match in recent_completed:
                entry = user_entries[user_entries["MatchID"].astype(str) == match.match_id].iloc[0]
                entry_id = str(entry["EntryID"])
                
                selections = get_team_selections(entry_id)
                player_points = get_player_points(match.match_id)
                
                position, total_players = get_leaderboard_position(match.match_id, st.session_state.username, scoring_rules)
                
                if player_points.empty:
                    st.warning(f"No points data available for {match.match_name} yet.")
                    continue
                
                total_score, player_scores = calculate_team_with_player_scores(selections, player_points, scoring_rules)
                
                with st.expander(f"📌 {match.match_name} - {total_score:.2f} pts (Rank: #{position}/{total_players})"):
                    role_emoji = {"WK": "🧤", "BAT": "🏏", "AR": "🔄", "BWL": "🎳"}
                    
                    player_data = []
                    for ps in sorted(player_scores, key=lambda x: -x.points):
                        multiplier = ""
                        if ps.is_captain:
                            multiplier = " (C)"
                        elif ps.is_vice_captain:
                            multiplier = " (VC)"
                        
                        stats = []
                        if ps.runs > 0:
                            stats.append(f"{ps.runs} runs")
                        if ps.wickets > 0:
                            stats.append(f"{ps.wickets} wkts")
                        if ps.catches > 0:
                            stats.append(f"{ps.catches} ct")
                        
                        player_data.append({
                            "Player": f"{role_emoji.get(ps.role, '❓')} {ps.player_name}{multiplier}",
                            "Pts": f"{ps.points:.1f}",
                            "Stats": ", ".join(stats) if stats else "-",
                        })
                    
                    st.dataframe(
                        pd.DataFrame(player_data),
                        hide_index=True,
                        use_container_width=True,
                    )
    
    upcoming = get_upcoming_matches()
    if upcoming:
        st.divider()
        st.header("📅 Upcoming Matches")
        for match in upcoming[:3]:
            st.markdown(f"**{match.match_name}**")
            st.caption(f"Starts: {match.start_time.strftime('%Y-%m-%d %H:%M')}")


def render_create_team():
    st.header("📝 Create Team")
    
    upcoming_matches = get_upcoming_matches()
    
    if not upcoming_matches:
        st.warning("No upcoming matches found.")
        return
    
    upcoming_matches_sorted = sorted(upcoming_matches, key=lambda x: (
        x.start_time.timestamp() if x.start_time else float('inf')
    ))
    
    if "create_team_index" not in st.session_state:
        st.session_state.create_team_index = 0
    
    # Handle deep link redirection logic
    if st.session_state.get("shared_match_id"):
        shared_id = st.session_state.shared_match_id
        for i, m in enumerate(upcoming_matches_sorted):
            if m.match_id == shared_id:
                st.session_state.create_team_index = i
                break
        st.session_state.shared_match_id = None
    
    current_idx = st.session_state.create_team_index
    current_idx = max(0, min(current_idx, len(upcoming_matches_sorted) - 1))
    st.session_state.create_team_index = current_idx
    
    selected_match = upcoming_matches_sorted[current_idx]
    
    col_prev, col_title, col_next = st.columns([1, 3, 1])
    
    with col_prev:
        if st.button("⬅️ Prev", disabled=current_idx == 0, key="create_team_prev"):
            st.session_state.create_team_index = current_idx - 1
            st.session_state.selected_players = {}
            st.session_state.captain = None
            st.session_state.vice_captain = None
            st.rerun()
    
    with col_title:
        status_emoji = "🔴" if is_match_live(selected_match) else "📌"
        st.markdown(f"### {status_emoji} {selected_match.match_name}")
        st.caption(f"Starts at: {selected_match.start_time.strftime('%Y-%m-%d %H:%M') if selected_match.start_time else 'TBD'}")
        
        # Share Button - Only show for UPCOMING matches (not live, not started)
        match_started = selected_match.start_time and selected_match.start_time <= now_ist()
        is_live = is_match_live(selected_match)
        
        if not match_started and not is_live:
            base_url = st.secrets.get("general", {}).get("BASE_URL", "http://localhost:8501")
            share_url = f"{base_url}/?match_id={selected_match.match_id}"
            if st.button("🔗 Share Contest", key=f"share_{selected_match.match_id}"):
                st.code(f"Join my {selected_match.match_name} contest on Fantasy IPL!\n{share_url}", language="text")
                st.toast("Link generated! Copy it above.")
    
    with col_next:
        if st.button("Next ➡️", disabled=current_idx == len(upcoming_matches_sorted) - 1, key="create_team_next"):
            st.session_state.create_team_index = current_idx + 1
            st.session_state.selected_players = {}
            st.session_state.captain = None
            st.session_state.vice_captain = None
            st.rerun()
    
    existing_entry = entry_exists(st.session_state.username, selected_match.match_id)
    
    rules = get_rules()
    squad_players = get_match_squad(selected_match.match_id)
    
    if not squad_players:
        st.warning("No players available for this match.")
        return
    
    if st.session_state.selected_match_id != selected_match.match_id:
        st.session_state.selected_match_id = selected_match.match_id
        st.session_state.selected_players = {}
        st.session_state.captain = None
        st.session_state.vice_captain = None
        
        if existing_entry:
            selections = get_team_selections(str(existing_entry))
            player_id_map = {p.player_id: p for p in squad_players}
            for sel in selections:
                if sel.player_id in player_id_map:
                    st.session_state.selected_players[sel.player_id] = player_id_map[sel.player_id]
                if sel.is_captain:
                    st.session_state.captain = sel.player_id
                if sel.is_vice_captain:
                    st.session_state.vice_captain = sel.player_id
    elif existing_entry and not st.session_state.selected_players:
        selections = get_team_selections(str(existing_entry))
        player_id_map = {p.player_id: p for p in squad_players}
        for sel in selections:
            if sel.player_id in player_id_map:
                st.session_state.selected_players[sel.player_id] = player_id_map[sel.player_id]
            if sel.is_captain:
                st.session_state.captain = sel.player_id
            if sel.is_vice_captain:
                st.session_state.vice_captain = sel.player_id
    
    if "selected_match_id" not in st.session_state:
        st.session_state.selected_match_id = selected_match.match_id
    
    render_player_selection_fragment(squad_players, rules, selected_match)


def render_my_teams():
    st.header("📋 My Teams")
    
    entries = get_entries()
    if entries.empty or "UserName" not in entries.columns:
        user_entries = pd.DataFrame()
    else:
        user_entries = entries[entries["UserName"] == st.session_state.username]
    
    if user_entries.empty:
        st.info("You haven't submitted any teams yet.")
        return
    
    all_matches = get_matches()
    match_dict = {m.match_id: m for m in all_matches}
    
    user_entries["match_start_time"] = user_entries["MatchID"].apply(
        lambda x: match_dict.get(str(x)).start_time if match_dict.get(str(x)) and match_dict.get(str(x)).start_time else None
    )
    user_entries = user_entries.sort_values("match_start_time", ascending=False, na_position="last")
    
    rules = get_rules()
    
    for _, entry in user_entries.iterrows():
        entry_id = str(entry["EntryID"])
        match_id = str(entry["MatchID"])
        
        all_matches = get_matches()
        match = next((m for m in all_matches if m.match_id == match_id), None)
        match_name = match.match_name if match else match_id
        
        lock_time = match.lock_time if match else None
        is_locked = lock_time and now_ist() > lock_time
        
        with st.expander(f"📌 {match_name}"):
            selections = get_team_selections(entry_id)
            
            if not is_locked:
                st.warning("⏰ Match hasn't started yet - you can still edit")
            
            col1, col2 = st.columns([3, 1])
            
            with col1:
                team_stats = get_team_stats([
                    {
                        "player_id": s.player_id,
                        "player_name": s.player_name,
                        "role": s.role,
                        "real_team": s.real_team,
                        "is_captain": s.is_captain,
                        "is_vice_captain": s.is_vice_captain,
                    }
                    for s in selections
                ])
                
                st.markdown(f"**Captain:** 🏆 {team_stats['captain'] or 'Not set'}")
                st.markdown(f"**Vice-Captain:** 🎖️ {team_stats['vice_captain'] or 'Not set'}")
                
                role_emoji = {"WK": "🧤", "BAT": "🏏", "AR": "🔄", "BWL": "🎳"}
                
                for s in sorted(selections, key=lambda x: x.pick_no):
                    multiplier = ""
                    if s.is_captain:
                        multiplier = " 🏆 (2x)"
                    elif s.is_vice_captain:
                        multiplier = " 🎖️ (1.5x)"
                    emoji = role_emoji.get(s.role, "❓")
                    st.markdown(f"{emoji} {s.player_name} ({s.role}){multiplier}")
            
            with col2:
                st.markdown(f"**Submitted:**")
                st.caption(str(entry.get("SubmittedAt", "Unknown"))[:19])
                
                if not is_locked:
                    if st.button("🗑️ Delete", key=f"delete_{entry_id}"):
                        try:
                            delete_entry(entry_id)
                            st.success("Team deleted!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to delete: {e}")


def render_all_teams():
    st.header("👥 All Teams")
    
    all_matches = get_matches()
    
    if not all_matches:
        st.info("No matches found.")
        return
    
    all_matches_sorted = sorted(all_matches, key=lambda x: (
        x.start_time.timestamp() if x.start_time else float('inf')
    ))
    
    if "all_teams_index" not in st.session_state:
        now = now_ist()
        live_idx = 0
        for i, m in enumerate(all_matches_sorted):
            if is_match_live(m):
                live_idx = i
                break
            elif m.start_time and m.start_time < now:
                live_idx = i
        st.session_state.all_teams_index = live_idx
    
    current_idx = st.session_state.all_teams_index
    current_idx = max(0, min(current_idx, len(all_matches_sorted) - 1))
    st.session_state.all_teams_index = current_idx
    
    match = all_matches_sorted[current_idx]
    teams = get_all_teams_for_match(match.match_id)
    
    col_prev, col_title, col_next = st.columns([1, 2, 1])
    
    with col_prev:
        if st.button("⬅️ Prev", disabled=current_idx == 0, key="all_teams_prev"):
            st.session_state.all_teams_index = current_idx - 1
            st.rerun()
    
    with col_title:
        status_emoji = "🔴" if is_match_live(match) else "📌"
        match_time = match.start_time.strftime('%Y-%m-%d %H:%M') if match.start_time else "TBD"
        st.markdown(f"### {status_emoji} {match.match_name}")
        st.caption(f"{match_time} ({current_idx + 1}/{len(all_matches_sorted)})")
    
    with col_next:
        if st.button("Next ➡️", disabled=current_idx == len(all_matches_sorted) - 1, key="all_teams_next"):
            st.session_state.all_teams_index = current_idx + 1
            st.rerun()
    
    st.divider()
    
    now = now_ist()
    match_started = match.start_time and match.start_time <= now
    
    if not match_started:
        st.info(f"Teams will be visible after match starts ({match.start_time.strftime('%Y-%m-%d %H:%M')})")
        return
    
    if not teams:
        st.info("No teams submitted for this match yet.")
        return
    
    scoring_rules = get_scoring_rules()
    player_points = get_player_points(match.match_id)
    
    teams_with_scores = []
    for team in teams:
        selections = get_team_selections(team.entry_id)
        
        if player_points is not None and not player_points.empty:
            total_points = calculate_team_total(selections, player_points, scoring_rules)
        else:
            total_points = 0.0
        
        teams_with_scores.append((team.user_name, total_points, selections))
    
    teams_with_scores.sort(key=lambda x: x[1], reverse=True)
    
    for rank, (username, total_points, selections) in enumerate(teams_with_scores, 1):
        with st.expander(f"#{rank} 👤 {username} - {total_points:.2f} pts"):
            role_emoji = {"WK": "🧤", "BAT": "🏏", "AR": "🔄", "BWL": "🎳"}
            
            if player_points is not None and not player_points.empty:
                _, player_scores = calculate_team_with_player_scores(selections, player_points, scoring_rules)
                player_scores_dict = {ps.player_name: ps for ps in player_scores}
                
                player_data = []
                for s in sorted(selections, key=lambda x: x.pick_no):
                    multiplier = ""
                    if s.is_captain:
                        multiplier = " 🏆 (2x)"
                    elif s.is_vice_captain:
                        multiplier = " 🎖️ (1.5x)"
                    
                    ps = player_scores_dict.get(s.player_name)
                    if ps:
                        points = ps.points
                        stats = []
                        if ps.runs > 0:
                            stats.append(f"{ps.runs} runs")
                        if ps.wickets > 0:
                            stats.append(f"{ps.wickets} wkts")
                        if ps.catches > 0:
                            stats.append(f"{ps.catches} ct")
                        stats_str = ", ".join(stats) if stats else "-"
                    else:
                        points = 0.0
                        stats_str = "-"
                    
                    player_data.append({
                        "Player": f"{role_emoji.get(s.role, '❓')} {s.player_name}{multiplier}",
                        "Pts": f"{points:.1f}",
                        "Stats": stats_str,
                    })
                
                st.dataframe(
                    pd.DataFrame(player_data),
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                for s in sorted(selections, key=lambda x: x.pick_no):
                    multiplier = ""
                    if s.is_captain:
                        multiplier = " 🏆 (2x)"
                    elif s.is_vice_captain:
                        multiplier = " 🎖️ (1.5x)"
                    emoji = role_emoji.get(s.role, "❓")
                    st.markdown(f"{emoji} {s.player_name} ({s.role}){multiplier}")


@st.cache_data(ttl=300)
def get_cached_player_points():
    return get_all_player_points()

@st.cache_data(ttl=300)
def get_cached_matches():
    return get_matches()

@st.fragment
def render_player_selection_fragment(squad_players, rules, selected_match):
    role_emoji = {"WK": "🧤", "BAT": "🏏", "AR": "🔄", "BWL": "🎳"}

    # FIX #5: cached — won't re-fetch on every checkbox rerun
    all_player_points = get_cached_player_points()
    all_matches = get_cached_matches()

    player_tournament_points = {}
    player_last_5_matches = {}

    if not all_player_points.empty and "PlayerID" in all_player_points.columns and "TotalPts" in all_player_points.columns:
        all_player_points["TotalPts"] = pd.to_numeric(all_player_points["TotalPts"], errors="coerce").fillna(0)
        match_times = {m.match_id: m.start_time for m in all_matches}

        for player in squad_players:
            player_data = all_player_points[all_player_points["PlayerID"] == player.player_id].copy()
            if not player_data.empty:
                player_data["match_time"] = player_data["MatchID"].apply(
                    lambda x: match_times.get(str(x)) if match_times.get(str(x)) else None
                )
                player_data = player_data.sort_values("match_time", na_position="last")
                total_pts = player_data["TotalPts"].sum()
                player_tournament_points[player.player_id] = total_pts

                past_matches = player_data[player_data["match_time"].notna() & (player_data["match_time"] < now_ist())]
                last_5 = past_matches.tail(5)
                match_details = []
                for _, row in last_5.iterrows():
                    match_id = str(row.get("MatchID", ""))
                    pts = float(row.get("TotalPts", 0))
                    runs = int(row.get("Runs", 0) or 0)
                    wkts = int(row.get("Wickets", 0) or 0)
                    catches = int(row.get("Catches", 0) or 0)
                    stats = []
                    if runs > 0: stats.append(f"{runs}r")
                    if wkts > 0: stats.append(f"{wkts}w")
                    if catches > 0: stats.append(f"{catches}c")
                    match_details.append(f"{match_id}: {pts:.1f}pts ({', '.join(stats)})" if stats else f"{match_id}: {pts:.1f}pts")
                player_last_5_matches[player.player_id] = match_details

    selected_list = []
    for pid, player in st.session_state.selected_players.items():
        selected_list.append({
            "player_id": pid,
            "player_name": player.player_name,
            "role": player.role,
            "real_team": player.real_team,
            "credits": player.credits,
            "is_captain": pid == st.session_state.captain,
            "is_vice_captain": pid == st.session_state.vice_captain,
        })

    validation = validate_team(selected_list, rules)

    st.markdown("---")

    # FIX #2/#3: compute role_counts and all derived sums ONCE here, outside all loops
    # These are based on session_state which is stable within a single render pass
    role_counts = {"WK": 0, "BAT": 0, "AR": 0, "BWL": 0}
    team_counts = {}
    for pid in st.session_state.selected_players:
        p = st.session_state.selected_players.get(pid)
        if p:
            role_counts[p.role] = role_counts.get(p.role, 0) + 1
            team_counts[p.real_team] = team_counts.get(p.real_team, 0) + 1

    bat_bwl_sum = role_counts.get('BAT', 0) + role_counts.get('BWL', 0)
    wk_ar_sum = role_counts.get('WK', 0) + role_counts.get('AR', 0)
    bat_ar_wk_sum = role_counts.get('BAT', 0) + role_counts.get('AR', 0) + role_counts.get('WK', 0)
    bwl_ar_wk_sum = role_counts.get('BWL', 0) + role_counts.get('AR', 0) + role_counts.get('WK', 0)
    bat_ar_bwl_sum = role_counts.get('BAT', 0) + role_counts.get('AR', 0) + role_counts.get('BWL', 0)
    wk_bat_bwl_sum = role_counts.get('WK', 0) + role_counts.get('BAT', 0) + role_counts.get('BWL', 0)
    current_count = len(st.session_state.selected_players)

    role_tabs = st.tabs(["🧤 Wicket Keepers", "🏏 Batsmen", "🔄 All Rounders", "🎳 Bowlers"])
    roles = ["WK", "BAT", "AR", "BWL"]

    captain_options = ["-- Select C --"] + [p["player_name"] for p in selected_list]
    vc_options = ["-- Select VC --"] + [p["player_name"] for p in selected_list]

    current_captain_idx = 0
    if st.session_state.captain:
        for i, p in enumerate(selected_list):
            if p["player_id"] == st.session_state.captain:
                current_captain_idx = i + 1
                break

    current_vc_idx = 0
    if st.session_state.vice_captain:
        for i, p in enumerate(selected_list):
            if p["player_id"] == st.session_state.vice_captain:
                current_vc_idx = i + 1
                break

    # FIX #4: on_change callbacks for captain/VC — avoids mid-render session_state writes
    def update_captain(role):
        val = st.session_state.get(f"cap_select_{role}")
        if val and val != "-- Select C --":
            for p in selected_list:
                if p["player_name"] == val:
                    st.session_state.captain = p["player_id"]
                    return
        st.session_state.captain = None

    def update_vc(role):
        val = st.session_state.get(f"vc_select_{role}")
        if val and val != "-- Select VC --":
            for p in selected_list:
                if p["player_name"] == val:
                    st.session_state.vice_captain = p["player_id"]
                    return
        st.session_state.vice_captain = None

    for role_idx, role in enumerate(roles):
        with role_tabs[role_idx]:
            role_players = [p for p in squad_players if p.role == role]
            role_players.sort(key=lambda p: player_tournament_points.get(p.player_id, 0), reverse=True)
            
            if not role_players:
                st.info(f"No {role} players available for this match.")
                continue
            
            wk_selected = role_counts.get('WK', 0)
            ar_selected = role_counts.get('AR', 0)
            
            if role == "WK" and wk_selected >= 4 and ar_selected == 0:
                st.warning("⚠️ At least 1 all-rounder needs to be selected")
            if role == "AR" and ar_selected >= 4 and wk_selected == 0:
                st.warning("⚠️ At least 1 wicketkeeper needs to be selected")
            
            teams_in_role = list(set(p.real_team for p in role_players))
            num_teams = len(teams_in_role)
            num_cols = max(3, num_teams)
            team_cols = st.columns(num_cols)

            for team_idx, team in enumerate(sorted(teams_in_role)):
                team_players = [p for p in role_players if p.real_team == team]
                team_count = team_counts.get(team, 0)
                team_at_max = team_count >= 7

                with team_cols[team_idx]:
                    team_color = "#ef4444" if team_at_max else "inherit"
                    st.markdown(f"### {team} <span style='color:{team_color}'>({team_count}/7)</span>", unsafe_allow_html=True)

                    for player in team_players:
                        checkbox_key = f"player_{player.player_id}"
                        is_selected = player.player_id in st.session_state.selected_players

                        tourney_pts = player_tournament_points.get(player.player_id, 0)
                        c_marker = " C" if player.player_id == st.session_state.captain else ""
                        vc_marker = " VC" if player.player_id == st.session_state.vice_captain else ""
                        label = f"{player.player_name} ({tourney_pts:.0f} pts){c_marker}{vc_marker}"
                        if not player.in_starting_xi:
                            label = f"{label} ⚠️"

                        last_5 = player_last_5_matches.get(player.player_id, [])
                        tooltip_parts = []
                        if not player.in_starting_xi:
                            tooltip_parts.append("Not playing in today's match")
                        if last_5:
                            tooltip_parts.append("Last 5 matches:")
                            tooltip_parts.extend(last_5)
                        tooltip = "\n".join(tooltip_parts) if tooltip_parts else None

                        # FIX #2/#3: use the single role_counts computed at top — no recomputation here
                        max_per_role = 6
                        role_at_max = role_counts.get(player.role, 0) >= max_per_role
                        bat_bwl_at_max = bat_bwl_sum >= 9
                        wk_ar_at_max = wk_ar_sum >= 5
                        bat_ar_wk_at_max = bat_ar_wk_sum >= 8
                        bwl_ar_wk_at_max = bwl_ar_wk_sum >= 8
                        bat_ar_bwl_at_max = bat_ar_bwl_sum >= 10
                        wk_bat_bwl_at_max = wk_bat_bwl_sum >= 10
                        
                        no_ar_without_wk = role_counts.get('WK', 0) >= 4 and role_counts.get('AR', 0) == 0 and player.role == 'WK' and not is_selected
                        no_wk_without_ar = role_counts.get('AR', 0) >= 4 and role_counts.get('WK', 0) == 0 and player.role == 'AR' and not is_selected
                        
                        is_disabled = (
                            (st.session_state.is_submitting) or
                            (current_count >= rules.max_players and not is_selected) or
                            (role_at_max and not is_selected) or
                            (team_at_max and not is_selected) or
                            (bat_bwl_at_max and player.role in ['BAT', 'BWL'] and not is_selected) or
                            (wk_ar_at_max and player.role in ['WK', 'AR'] and not is_selected) or
                            (bat_ar_wk_at_max and player.role in ['BAT', 'AR', 'WK'] and not is_selected) or
                            (bwl_ar_wk_at_max and player.role in ['BWL', 'AR', 'WK'] and not is_selected) or
                            (bat_ar_bwl_at_max and player.role in ['BAT', 'AR', 'BWL'] and not is_selected) or
                            (wk_bat_bwl_at_max and player.role in ['WK', 'BAT', 'BWL'] and not is_selected) or
                            no_ar_without_wk or no_wk_without_ar
                        )

                        new_state = st.checkbox(label, value=is_selected, disabled=is_disabled, key=checkbox_key, help=tooltip)

                        if new_state != is_selected:
                            if new_state:
                                if current_count < rules.max_players:
                                    st.session_state.selected_players[player.player_id] = player
                            else:
                                if player.player_id in st.session_state.selected_players:
                                    del st.session_state.selected_players[player.player_id]
                                if st.session_state.captain == player.player_id:
                                    st.session_state.captain = None
                                if st.session_state.vice_captain == player.player_id:
                                    st.session_state.vice_captain = None
                            # FIX #1: rerun is still needed so is_disabled updates for other checkboxes
                            # But it's correctly gated inside `if new_state != is_selected` so only fires on actual change
                            try:
                                st.rerun(scope="fragment")
                            except Exception:
                                st.rerun()

            # Warnings use top-level sums — correct since role_counts is computed once per render
            total_selected = len(st.session_state.selected_players)
            team_full_and_valid = (
                total_selected == 11 and 
                role_counts.get('WK', 0) >= 1 and 
                role_counts.get('BAT', 0) >= 3 and 
                role_counts.get('AR', 0) >= 1 and 
                role_counts.get('BWL', 0) >= 3
            )
            
            if not team_full_and_valid:
                current_role_count = role_counts.get(role, 0)
                if role == "BAT" and current_role_count >= 6:
                    st.warning("⚠️ Minimum 3 and maximum 6 batsmen can be selected")
                if role == "BWL" and current_role_count >= 6:
                    st.warning("⚠️ Minimum 3 and maximum 6 bowlers can be selected")
                if bat_bwl_sum >= 9 and role in ["BAT", "BWL"]:
                    st.warning("⚠️ At least 1 wicketkeeper and 1 all-rounder needs to be selected")
                if wk_ar_sum >= 5 and role in ["WK", "AR"]:
                    st.warning("⚠️ At least 3 batsmen and 3 bowlers need to be selected")
                if bat_ar_wk_sum >= 8 and role in ["BAT", "AR", "WK"]:
                    st.warning("⚠️ Minimum 3 bowlers need to be selected")
                if bwl_ar_wk_sum >= 8 and role in ["BWL", "AR", "WK"]:
                    st.warning("⚠️ At least 3 batsmen need to be selected")
                if bat_ar_bwl_sum >= 10 and role in ["BAT", "AR", "BWL"]:
                    st.warning("⚠️ At least 1 wicketkeeper needs to be selected")
                if wk_bat_bwl_sum >= 10 and role in ["WK", "BAT", "BWL"]:
                    st.warning("⚠️ At least 1 all-rounder needs to be selected")

            if num_teams < 3:
                with team_cols[2]:
                    st.markdown("### Captain / VC")
                    st.selectbox(
                        "🏆 Captain", options=captain_options, index=current_captain_idx,
                        key=f"cap_select_{role}",
                        on_change=update_captain, args=(role,)   # FIX #4
                    )
                    st.selectbox(
                        "🎖️ Vice-Capt", options=vc_options, index=current_vc_idx,
                        key=f"vc_select_{role}",
                        on_change=update_vc, args=(role,)        # FIX #4
                    )

                    def set_submitting():
                        st.session_state.is_submitting = True

                    st.divider()
                    if not validation.is_valid:
                        st.error(f"{len(validation.errors)} issues")
                    if st.button("✅ Submit Team", disabled=not validation.is_valid or st.session_state.is_submitting, type="primary", key=f"submit_btn_{role}", on_click=set_submitting):
                        players_data = []
                        for pid, player in st.session_state.selected_players.items():
                            players_data.append({
                                "player_id": pid,
                                "player_name": player.player_name,
                                "role": player.role,
                                "real_team": player.real_team,
                                "credits": player.credits,
                                "is_captain": pid == st.session_state.captain,
                                "is_vice_captain": pid == st.session_state.vice_captain,
                            })
                        try:
                            entry_id = save_entry(st.session_state.username, selected_match.match_id, players_data)
                            st.session_state.is_submitting = False
                            st.session_state.page = "📋 My Teams"
                            st.success(f"Team submitted! Entry ID: {entry_id}")
                            st.rerun()
                        except Exception as e:
                            st.session_state.is_submitting = False
                            entry_id = f"E{len(st.session_state.get('pending_writes', [])) + 1}"
                            pending_entry = {
                                "id": str(uuid.uuid4()),
                                "type": "team_submission",
                                "username": st.session_state.username,
                                "match_id": selected_match.match_id,
                                "entries_data": {
                                    "entry_id": entry_id,
                                    "username": st.session_state.username,
                                    "match_id": selected_match.match_id,
                                    "submitted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                },
                                "selections_data": players_data,
                                "attempts": 0,
                                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "last_attempt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "error": str(e)[:200]
                            }
                            if "pending_writes" not in st.session_state:
                                st.session_state.pending_writes = []
                            st.session_state.pending_writes.append(pending_entry)
                            st.error(f"Failed to submit team: {e}. Added to retry queue.")


def process_auto_retry():
    pending = st.session_state.get("pending_writes", [])
    if not pending:
        return
    
    processed = False
    for i in range(min(2, len(pending))):
        if i >= len(pending):
            break
        if pending[i].get("attempts", 0) >= 5:
            pending.pop(i)
            processed = True
    
    if processed:
        st.rerun()


def render_admin():
    process_auto_retry()
    st.header("🔧 Admin Panel")
    st.subheader("Failed Writes Queue")
    
    pending = st.session_state.get("pending_writes", [])
    
    if not pending:
        st.success("No failed writes in queue!")
    else:
        st.info(f"Pending entries: {len(pending)}")
        
        for i, entry in enumerate(pending):
            with st.expander(f"Entry {i+1}: {entry.get('username', 'N/A')} - {entry.get('match_id', 'N/A')} (Attempts: {entry.get('attempts', 0)})"):
                st.write(f"**Type:** {entry.get('type', 'N/A')}")
                st.write(f"**Created:** {entry.get('created_at', 'N/A')}")
                st.write(f"**Last Attempt:** {entry.get('last_attempt', 'N/A')}")
                st.write(f"**Error:** {entry.get('error', 'N/A')}")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Retry Now", key=f"retry_{i}"):
                        retry_entry(i)
                with col2:
                    if st.button("Remove", key=f"remove_{i}"):
                        st.session_state.pending_writes.pop(i)
                        st.rerun()
        
        st.divider()
        
        if st.button("Retry All Pending", type="primary"):
            for i in range(len(st.session_state.pending_writes) - 1, -1, -1):
                retry_entry(i)
            st.rerun()
        
        st.divider()
        if st.button("Download Failed Writes (CSV)"):
            download_failed_writes_csv()


def retry_entry(index: int):
    pending = st.session_state.get("pending_writes", [])
    if index >= len(pending):
        return
    
    entry = pending[index]
    entry["attempts"] += 1
    entry["last_attempt"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        if entry.get("type") == "team_submission":
            from lib.google_sheets import save_entry
            
            entries_data = entry.get("entries_data", {})
            selections_data = entry.get("selections_data", [])
            
            if not entry_exists(entries_data.get("username"), entries_data.get("match_id")):
                entry_id = save_entry(
                    entries_data.get("username"),
                    entries_data.get("match_id"),
                    selections_data
                )
                st.session_state.pending_writes.pop(index)
                st.success(f"Retry successful! Entry ID: {entry_id}")
            else:
                entry["error"] = "Entry already exists in sheet"
                entry["attempts"] = 5
    except Exception as e:
        entry["error"] = str(e)[:200]
        if entry["attempts"] >= 5:
            st.warning(f"Entry {index + 1} removed after 5 failed attempts")
            st.session_state.pending_writes.pop(index)


def download_failed_writes_csv():
    import io
    
    pending = st.session_state.get("pending_writes", [])
    if not pending:
        st.warning("No failed writes to download")
        return
    
    lines = []
    lines.append("=== Entries ===")
    lines.append("EntryID,UserName,MatchID,SubmittedAt")
    
    for entry in pending:
        if entry.get("type") == "team_submission":
            entries_data = entry.get("entries_data", {})
            lines.append(f"{entries_data.get('entry_id', '')},{entries_data.get('username', '')},{entries_data.get('match_id', '')},{entries_data.get('submitted_at', '')}")
    
    lines.append("")
    lines.append("=== FantasySelections ===")
    lines.append("EntryID,PlayerID,PlayerName,Role,RealTeam,Credits,IsCaptain,IsViceCaptain")
    
    for entry in pending:
        if entry.get("type") == "team_submission":
            entries_data = entry.get("entries_data", {})
            entry_id = entries_data.get("entry_id", "")
            selections_data = entry.get("selections_data", [])
            for sel in selections_data:
                lines.append(f"{entry_id},{sel.get('player_id', '')},{sel.get('player_name', '')},{sel.get('role', '')},{sel.get('real_team', '')},{sel.get('credits', '')},{sel.get('is_captain', '')},{sel.get('is_vice_captain', '')}")
    
    csv_content = "\n".join(lines)
    st.download_button(
        label="Download CSV",
        data=csv_content,
        file_name="failed_writes.csv",
        mime="text/csv"
    )


def render_overall_leaderboard():
    st.header("🏆 Overall Leaderboard") 
    
    with st.spinner("Fetching rankings..."):
        df = get_overall_leaderboard()
    
    if df.empty:
        st.info("No completed match rankings available yet. Wait for a match to finish!")
        return
    
    # Add Rank column
    df.insert(0, "Rank", range(1, len(df) + 1))
    
    # Custom styling for the table
    def format_rank(rank):
        if rank == 1: return "🥇 1"
        if rank == 2: return "🥈 2"
        if rank == 3: return "🥉 3"
        return str(rank)
    
    df["Rank"] = df["Rank"].apply(format_rank)
    
    # Display the full leaderboard
    st.dataframe(
        df,
        column_config={
            "Rank": st.column_config.TextColumn("Rank", width="small"),
            "UserName": st.column_config.TextColumn("User", width="medium"),
            "TotalPoints": st.column_config.NumberColumn("Total Points", format="%.2f"),
            "Entries": st.column_config.NumberColumn("Entries", format="%d"),
            "Top3Finishes": st.column_config.NumberColumn("Top 3 Finishes", format="%d", help="Number of times in the top 3 of a single match"),
        },
        hide_index=True,
        use_container_width=True,
    )


def render_live_stats():
    st.header("📊 Live Contest Stats")
    
    live_matches = get_live_matches()
    if not live_matches:
        st.info("No matches are currently live. Check back once a match starts!")
        return
        
    if len(live_matches) > 1:
        match_names = [m.match_name for m in live_matches]
        selected_match_name = st.selectbox("Select Live Match", match_names)
        match = next(m for m in live_matches if m.match_name == selected_match_name)
    else:
        match = live_matches[0]
        st.subheader(f"📍 {match.match_name}")
    
    tab_stats, tab_compare = st.tabs(["📊 Player Stats", "🔄 Compare Entries"])
    
    with tab_stats:
        with st.spinner("Loading live stats..."):
            df = get_player_stats_for_match(match.match_id)
            
        if df.empty:
            st.warning("No player statistics available for this match yet.")
        else:
            # Formatting for display
            display_df = df.copy()
            
            # Add status emoji
            def get_role_emoji(role):
                return {"WK": "🧤", "BAT": "🏏", "AR": "🔄", "BWL": "🎳"}.get(role, "❓")
                
            display_df["Player"] = display_df.apply(lambda r: f"{get_role_emoji(r['Role'])} {r['PlayerName']}", axis=1)
            
            # Reorder and rename columns
            display_df = display_df[["Player", "Team", "TotalPts", "SelectedBy"]]
            display_df.columns = ["Player Name", "Team", "Points Scored", "Selected By"]
            
            # Metrics for quick overview
            m_cols = st.columns(3)
            with m_cols[0]:
                top_scorer = df.iloc[0]
                st.metric("Top Scorer", top_scorer["PlayerName"], f"{top_scorer['TotalPts']:.0f} pts")
            with m_cols[1]:
                most_selected = df.loc[df["SelectedBy"].idxmax()]
                st.metric("Most Selected", most_selected["PlayerName"], f"{most_selected['SelectedBy']} picks")
            with m_cols[2]:
                total_participants = df["SelectedBy"].sum() / 11 # approximate
                st.metric("Contestants", f"{total_participants:.0f}")
                
            st.divider()
            
            # Display the table
            st.dataframe(
                display_df,
                column_config={
                    "Player Name": st.column_config.TextColumn("Player Name", width="large"),
                    "Team": st.column_config.TextColumn("Team", width="small"),
                    "Points Scored": st.column_config.NumberColumn("Points", format="%.1f", help="Points scored in this match so far"),
                    "Selected By": st.column_config.NumberColumn("Selected By", format="%d", help="How many participants picked this player"),
                },
                hide_index=True,
                use_container_width=True,
            )

    with tab_compare:
        all_teams = get_all_teams_for_match(match.match_id)
        if not all_teams:
            st.info("No teams submitted for this match.")
        else:
            # 1. Find Current User's Team
            my_team = next((t for t in all_teams if t.user_name.lower() == st.session_state.username.lower()), None)
            
            if not my_team:
                st.warning("You haven't submitted a team for this match. Comparison is only available between your team and others.")
            else:
                other_teams = [t for t in all_teams if t.user_name.lower() != st.session_state.username.lower()]
                
                if not other_teams:
                    st.info("No other participants to compare with yet.")
                else:
                    other_user = st.selectbox("Select contestant to compare with", [t.user_name for t in other_teams])
                    their_team = next(t for t in other_teams if t.user_name == other_user)
                    
                    # Get scoring rules and player points for calculation
                    scoring_rules = get_scoring_rules()
                    player_points_df = get_player_points(match.match_id)
                    player_points_dict = {row["PlayerID"]: row["TotalPts"] for _, row in player_points_df.iterrows()} if not player_points_df.empty else {}
                    
                    def get_points(p_id, is_c, is_vc):
                        pts = float(player_points_dict.get(p_id, 0))
                        if is_c: return pts * 2
                        if is_vc: return pts * 1.5
                        return pts

                    # 2. Comparison Logic
                    my_players = {p.player_id: p for p in my_team.players}
                    their_players = {p.player_id: p for p in their_team.players}
                    
                    # Section 1: Different Players
                    my_unique = [p for p_id, p in my_players.items() if p_id not in their_players]
                    their_unique = [p for p_id, p in their_players.items() if p_id not in my_players]
                    
                    # Section 2: Same Players, Different Roles
                    role_diff = []
                    for p_id, p in my_players.items():
                        if p_id in their_players:
                            tp = their_players[p_id]
                            if p.is_captain != tp.is_captain or p.is_vice_captain != tp.is_vice_captain:
                                role_diff.append((p, tp))
                                
                    # Section 3: Same Players, Same Roles
                    common = []
                    for p_id, p in my_players.items():
                        if p_id in their_players:
                            tp = their_players[p_id]
                            if p.is_captain == tp.is_captain and p.is_vice_captain == tp.is_vice_captain:
                                common.append(p)

                    st.markdown("### 🔍 Side-by-Side Comparison")
                    
                    # Display Differences
                    with st.expander("🛡️ Different Players", expanded=True):
                        c1, c2 = st.columns(2)
                        my_pts = sum(get_points(p.player_id, p.is_captain, p.is_vice_captain) for p in my_unique)
                        their_pts = sum(get_points(p.player_id, p.is_captain, p.is_vice_captain) for p in their_unique)
                        diff = my_pts - their_pts
                        
                        with c1:
                            st.markdown(f"**Your Unique Picks** ({my_pts:.1f} pts)")
                            for p in my_unique:
                                role = " (C)" if p.is_captain else " (VC)" if p.is_vice_captain else ""
                                st.caption(f"• {p.player_name}{role} - {get_points(p.player_id, p.is_captain, p.is_vice_captain):.1f}")
                        with c2:
                            st.markdown(f"**{other_user}'s Unique Picks** ({their_pts:.1f} pts)")
                            for p in their_unique:
                                role = " (C)" if p.is_captain else " (VC)" if p.is_vice_captain else ""
                                st.caption(f"• {p.player_name}{role} - {get_points(p.player_id, p.is_captain, p.is_vice_captain):.1f}")
                        
                        if diff != 0:
                            color = "green" if diff > 0 else "red"
                            lead = "ahead" if diff > 0 else "behind"
                            st.markdown(f"<p style='text-align:center; color:{color}; font-weight:bold;'>You are {abs(diff):.1f} pts {lead} in this section</p>", unsafe_allow_html=True)

                    with st.expander("🔄 Same Players, Different Roles", expanded=True):
                        if not role_diff:
                            st.info("No players shared with different roles.")
                        else:
                            c1, c2 = st.columns(2)
                            my_r_pts = sum(get_points(p.player_id, p.is_captain, p.is_vice_captain) for p, _ in role_diff)
                            their_r_pts = sum(get_points(tp.player_id, tp.is_captain, tp.is_vice_captain) for _, tp in role_diff)
                            r_diff = my_r_pts - their_r_pts
                            
                            with c1:
                                st.markdown(f"**Your Role Picks** ({my_r_pts:.1f} pts)")
                                for p, tp in role_diff:
                                    role = " (C)" if p.is_captain else " (VC)" if p.is_vice_captain else " (Normal)"
                                    st.caption(f"• {p.player_name}{role} - {get_points(p.player_id, p.is_captain, p.is_vice_captain):.1f}")
                            with c2:
                                st.markdown(f"**{other_user}'s Role Picks** ({their_r_pts:.1f} pts)")
                                for p, tp in role_diff:
                                    role = " (C)" if tp.is_captain else " (VC)" if tp.is_vice_captain else " (Normal)"
                                    st.caption(f"• {tp.player_name}{role} - {get_points(tp.player_id, tp.is_captain, tp.is_vice_captain):.1f}")
                            
                            if r_diff != 0:
                                color = "green" if r_diff > 0 else "red"
                                lead = "ahead" if r_diff > 0 else "behind"
                                st.markdown(f"<p style='text-align:center; color:{color}; font-weight:bold;'>You are {abs(r_diff):.1f} pts {lead} on role picks</p>", unsafe_allow_html=True)

                    with st.expander("🤝 Common Players (Same Role)", expanded=False):
                        if not common:
                            st.info("No players shared with identical roles.")
                        else:
                            c1, c2 = st.columns(2)
                            with c1:
                                for p in common[:len(common)//2 + 1]:
                                    role = " (C)" if p.is_captain else " (VC)" if p.is_vice_captain else ""
                                    st.caption(f"• {p.player_name}{role} - {get_points(p.player_id, p.is_captain, p.is_vice_captain):.1f}")
                            with c2:
                                for p in common[len(common)//2 + 1:]:
                                    role = " (C)" if p.is_captain else " (VC)" if p.is_vice_captain else ""
                                    st.caption(f"• {p.player_name}{role} - {get_points(p.player_id, p.is_captain, p.is_vice_captain):.1f}")


if __name__ == "__main__":
    main()
