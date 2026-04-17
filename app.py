import streamlit as st
import pandas as pd
from datetime import datetime
import hmac
import base64
import time
from streamlit_cookies_manager import EncryptedCookieManager
from lib.google_sheets import (
    get_matches,
    get_upcoming_matches,
    get_live_matches,
    get_completed_matches,
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
)
from lib.validators import validate_team, get_team_stats
from lib.scoring import calculate_team_total, calculate_team_with_player_scores


SECRET_KEY = "fantasy_ipl_secret_key_2024"

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
    page_icon="🏏",
    layout="wide",
)


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

COOKIE_PASSWORD = "fantasy_ipl_secret_2024"

cookies = EncryptedCookieManager(prefix="ipl-di/", password=COOKIE_PASSWORD)
if not cookies.ready():
    st.stop()

if not st.session_state.username:
    stored_token = cookies.get("fantasy_ipl_user")
    if stored_token:
        username = verify_session_token(stored_token)
        if username:
            st.session_state.username = username


def main():
    st.title("🏏 Fantasy IPL")
    
    if not st.session_state.username:
        with st.container():
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                tab_login, tab_signup = st.tabs(["Login", "Sign Up"])
                
                with tab_login:
                    st.subheader("Enter your username to continue")
                    with st.form("login_form"):
                        username = st.text_input(
                            "Username",
                            placeholder="Enter your username",
                            label_visibility="collapsed",
                            key="username_input",
                        )
                        password = st.text_input(
                            "Password",
                            type="password",
                            placeholder="Enter your password",
                            label_visibility="collapsed",
                            key="password_input",
                        )
                        if st.form_submit_button("Login", use_container_width=True):
                            if username and password:
                                if verify_user(username, password):
                                    st.session_state.username = username
                                    token = create_session_token(username)
                                    cookies["fantasy_ipl_user"] = token
                                    cookies.save()
                                    st.rerun()
                                else:
                                    st.error("Invalid username or password")
                            elif not username:
                                st.warning("Please enter your username")
                            elif not password:
                                st.warning("Please enter your password")
                
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
    
    if st.sidebar.button("🔄 Refresh Data"):
        clear_all_caches()
        st.rerun()
    
    if st.sidebar.button("🚪 Logout"):
        st.session_state.username = ""
        cookies["fantasy_ipl_user"] = ""
        cookies.save()
        st.rerun()
    
    if "page" not in st.session_state:
        st.session_state.page = "🏠 Home"
    
    pages = ["🏠 Home", "📝 Create Team", "📋 My Teams", "🏆 All Teams"]
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
    elif page == "🏆 All Teams":
        render_all_teams()


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
            st.subheader(f"📺 {match.match_name}")
            st.caption(f"Status: {match.status}")
            
            if not user_entries.empty:
                entry = user_entries[user_entries["MatchID"].astype(str) == match.match_id]
                if not entry.empty:
                    entry_id = str(entry.iloc[0]["EntryID"])
                    selections = get_team_selections(entry_id)
                    player_points = get_player_points(match.match_id)
                    position, total_players = get_leaderboard_position(match.match_id, st.session_state.username, scoring_rules)
                    
                    if player_points is not None and not player_points.empty:
                        total_score, player_scores = calculate_team_with_player_scores(selections, player_points, scoring_rules)
                        
                        with st.expander(f"📊 Your Score: {total_score:.2f} pts (Rank: #{position}/{total_players})"):
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
                    else:
                        st.info("Waiting for points data...")
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
        match_time = selected_match.start_time.strftime('%Y-%m-%d %H:%M') if selected_match.start_time else "TBD"
        st.markdown(f"### {status_emoji} {selected_match.match_name}")
        st.caption(f"{match_time} ({current_idx + 1}/{len(upcoming_matches_sorted)})")
    
    with col_next:
        if st.button("Next ➡️", disabled=current_idx == len(upcoming_matches_sorted) - 1, key="create_team_next"):
            st.session_state.create_team_index = current_idx + 1
            st.session_state.selected_players = {}
            st.session_state.captain = None
            st.session_state.vice_captain = None
            st.rerun()
    
    st.divider()
    
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
    st.header("🏆 All Teams")
    
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
    
    col_prev, col_title, col_next = st.columns([1, 3, 1])
    
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


@st.fragment
def render_player_selection_fragment(squad_players, rules, selected_match):
    role_emoji = {"WK": "🧤", "BAT": "🏏", "AR": "🔄", "BWL": "🎳"}
    
    all_player_points = get_all_player_points()
    
    player_tournament_points = {}
    player_last_5_matches = {}
    
    if not all_player_points.empty and "PlayerID" in all_player_points.columns and "TotalPts" in all_player_points.columns:
        all_player_points["TotalPts"] = pd.to_numeric(all_player_points["TotalPts"], errors="coerce").fillna(0)
        
        all_matches = get_matches()
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
                    if runs > 0:
                        stats.append(f"{runs}r")
                    if wkts > 0:
                        stats.append(f"{wkts}w")
                    if catches > 0:
                        stats.append(f"{catches}c")
                    
                    match_details.append(f"{match_id}: {pts:.1f}pts ({', '.join(stats)})" if stats else f"{match_id}: {pts:.1f}pts")
                
                player_last_5_matches[player.player_id] = match_details
    
    st.divider()
    
    role_tabs = st.tabs(["🧤 Wicket Keepers", "🏏 Batsmen", "🔄 All Rounders", "🎳 Bowlers"])
    
    roles = ["WK", "BAT", "AR", "BWL"]
    
    for role_idx, role in enumerate(roles):
        with role_tabs[role_idx]:
            role_players = [p for p in squad_players if p.role == role]
            role_players.sort(key=lambda p: player_tournament_points.get(p.player_id, 0), reverse=True)
            
            if not role_players:
                st.info(f"No {role} players available for this match.")
                continue
            
            teams_in_role = list(set(p.real_team for p in role_players))
            
            team_cols = st.columns(len(teams_in_role))
            
            for team_idx, team in enumerate(sorted(teams_in_role)):
                team_players = [p for p in role_players if p.real_team == team]
                
                with team_cols[team_idx]:
                    st.markdown(f"### {team}")
                    
                    for player in team_players:
                        checkbox_key = f"player_{player.player_id}"
                        is_selected = player.player_id in st.session_state.selected_players
                        
                        tourney_pts = player_tournament_points.get(player.player_id, 0)
                        label = f"{player.player_name} ({tourney_pts:.0f} pts)"
                        
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
                        
                        current_count = len(st.session_state.selected_players)
                        is_disabled = current_count >= rules.max_players and not is_selected
                        
                        new_state = st.checkbox(label, value=is_selected, disabled=is_disabled, key=checkbox_key, help=tooltip)
                        
                        if new_state != is_selected:
                            if new_state:
                                if current_count < rules.max_players:
                                    st.session_state.selected_players[player.player_id] = player
                                    st.rerun(scope="fragment")
                            else:
                                if player.player_id in st.session_state.selected_players:
                                    del st.session_state.selected_players[player.player_id]
                                if st.session_state.captain == player.player_id:
                                    st.session_state.captain = None
                                if st.session_state.vice_captain == player.player_id:
                                    st.session_state.vice_captain = None
                                st.rerun(scope="fragment")
    
    st.divider()
    
    selected_player_ids = list(st.session_state.selected_players.keys())
    
    right_col1, right_col2 = st.columns([3, 1])
    
    with right_col1:
        role_counts = {"WK": 0, "BAT": 0, "AR": 0, "BWL": 0}
        team_counts = {}
        
        for pid in selected_player_ids:
            player = st.session_state.selected_players.get(pid)
            if player:
                role_counts[player.role] = role_counts.get(player.role, 0) + 1
                team_counts[player.real_team] = team_counts.get(player.real_team, 0) + 1
        
        st.markdown("### Team Stats")
        st.markdown(f"**Selected:** {len(selected_player_ids)}/{rules.max_players}")
        
        stat_col1, stat_col2 = st.columns(2)
        with stat_col1:
            st.markdown("**By Role**")
            for role, count in role_counts.items():
                min_req = getattr(rules, f"min_{role.lower()}")
                status = "✅" if count >= min_req else "❌"
                st.markdown(f"{status} {role}: {count}/{min_req}")
        
        with stat_col2:
            st.markdown("**By Team**")
            for team, count in team_counts.items():
                status = "⚠️" if count > rules.max_from_one_team else "✅"
                st.markdown(f"{status} {team}: {count}")
    
    with right_col2:
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
        
        captain_options = ["-- Select --"] + [p["player_name"] for p in selected_list]
        vc_options = ["-- Select --"] + [p["player_name"] for p in selected_list]
        
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
        
        captain_name = st.selectbox("🏆 Captain", options=captain_options, index=current_captain_idx, key="captain_select")
        if captain_name != "-- Select --":
            for p in selected_list:
                if p["player_name"] == captain_name:
                    st.session_state.captain = p["player_id"]
                    break
        else:
            st.session_state.captain = None
        
        vc_name = st.selectbox("🎖️ Vice-Captain", options=vc_options, index=current_vc_idx, key="vc_select")
        if vc_name != "-- Select --":
            for p in selected_list:
                if p["player_name"] == vc_name:
                    st.session_state.vice_captain = p["player_id"]
                    break
        else:
            st.session_state.vice_captain = None
    
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
    
    st.divider()
    
    validation = validate_team(selected_list, rules)
    
    if not validation.is_valid:
        for error in validation.errors:
            st.error(error)
        submit_disabled = True
    else:
        submit_disabled = False
    
    if st.button("✅ Submit Team", disabled=submit_disabled, type="primary"):
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
            st.session_state.page = "📋 My Teams"
            st.success(f"Team submitted! Entry ID: {entry_id}")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to submit team: {e}")


if __name__ == "__main__":
    main()
