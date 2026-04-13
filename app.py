import streamlit as st
import pandas as pd
from datetime import datetime
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
    save_entry,
    delete_entry,
    entry_exists,
    get_team_selections,
    clear_all_caches,
)
from lib.validators import validate_team, get_team_stats
from lib.scoring import calculate_team_total, calculate_team_with_player_scores


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


def main():
    st.title("🏏 Fantasy IPL")
    
    if not st.session_state.username:
        with st.container():
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.subheader("Enter your username to continue")
                username = st.text_input(
                    "Username",
                    placeholder="Enter your username",
                    label_visibility="collapsed",
                    key="username_input",
                )
                if username:
                    st.session_state.username = username
                    st.rerun()
        st.stop()
    
    st.sidebar.success(f"Logged in as: **{st.session_state.username}**")
    
    if st.sidebar.button("🔄 Refresh Data"):
        clear_all_caches()
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
    user_entries = entries[entries["UserName"] == st.session_state.username]
    
    scoring_rules = get_scoring_rules()
    
    if live_matches:
        st.header("🔴 Live Matches")
        for match in live_matches:
            st.subheader(f"📺 {match.match_name}")
            st.caption(f"Status: {match.status}")
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
    
    match_options = {
        f"{m.match_name} ({m.start_time.strftime('%Y-%m-%d %H:%M')})": m
        for m in upcoming_matches
    }
    
    selected_match_name = st.selectbox(
        "Select Match",
        options=list(match_options.keys()),
        index=0,
        key="match_selector",
    )
    
    selected_match = match_options[selected_match_name]
    
    existing_entry = entry_exists(st.session_state.username, selected_match.match_id)
    if existing_entry:
        st.info(f"You already have an entry for this match. Go to 'My Teams' to edit it.")
    
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
    
    if "selected_match_id" not in st.session_state:
        st.session_state.selected_match_id = selected_match.match_id
    
    st.divider()
    
    left_col, right_col = st.columns([3, 1])
    
    with left_col:
        all_teams = list(set(p.real_team for p in squad_players))
        
        filter_col1, filter_col2, filter_col3 = st.columns([1, 1, 2])
        
        with filter_col1:
            role_filter = st.multiselect(
                "Role",
                options=["WK", "BAT", "AR", "BWL"],
                default=["WK", "BAT", "AR", "BWL"],
                key="role_filter",
            )
        
        with filter_col2:
            team_filter = st.multiselect(
                "Team",
                options=all_teams,
                default=all_teams,
                key="team_filter",
            )
        
        with filter_col3:
            search = st.text_input("🔍 Search", placeholder="Search player name...", key="player_search")
    
    filtered_players = [
        p for p in squad_players
        if p.role in role_filter
        and p.real_team in team_filter
        and (not search or search.lower() in p.player_name.lower())
    ]
    
    role_emoji = {"WK": "🧤", "BAT": "🏏", "AR": "🔄", "BWL": "🎳"}
    
    selected_player_ids = list(st.session_state.selected_players.keys())
    max_selected = len(selected_player_ids) >= rules.max_players
    
    players_per_row = 4
    players_per_col = (len(filtered_players) + players_per_row - 1) // players_per_row
    
    for i in range(players_per_col):
        cols = st.columns(players_per_row)
        for j in range(players_per_row):
            idx = i * players_per_row + j
            if idx < len(filtered_players):
                player = filtered_players[idx]
                is_selected = player.player_id in st.session_state.selected_players
                
                emoji = role_emoji.get(player.role, "❓")
                label = f"{emoji} {player.player_name} ({player.real_team})"
                if is_selected:
                    label = f"✅ {label}"
                
                is_disabled = max_selected and not is_selected
                
                with cols[j]:
                    if is_disabled:
                        st.checkbox(label, value=is_selected, disabled=True, key=f"player_{player.player_id}")
                    else:
                        if st.checkbox(label, value=is_selected, key=f"player_{player.player_id}"):
                            st.session_state.selected_players[player.player_id] = player
                        else:
                            if player.player_id in st.session_state.selected_players:
                                del st.session_state.selected_players[player.player_id]
                            
                            if st.session_state.captain == player.player_id:
                                st.session_state.captain = None
                            if st.session_state.vice_captain == player.player_id:
                                st.session_state.vice_captain = None
    
    with right_col:
        role_counts = {"WK": 0, "BAT": 0, "AR": 0, "BWL": 0}
        team_counts = {}
        
        for pid in selected_player_ids:
            player = st.session_state.selected_players.get(pid)
            if player:
                role_counts[player.role] = role_counts.get(player.role, 0) + 1
                team_counts[player.real_team] = team_counts.get(player.real_team, 0) + 1
        
        st.markdown("### Team Stats")
        st.markdown(f"**Selected:** {len(selected_player_ids)}/{rules.max_players}")
        
        st.markdown("**By Role**")
        for role, count in role_counts.items():
            min_req = getattr(rules, f"min_{role.lower()}")
            status = "✅" if count >= min_req else "❌"
            st.markdown(f"{status} {role}: {count} (min: {min_req})")
        
        st.markdown("**By Team**")
        for team, count in team_counts.items():
            status = "⚠️" if count > rules.max_from_one_team else "✅"
            st.markdown(f"{status} {team}: {count}")
    
    st.divider()
    
    selected_list = []
    for pid, player in st.session_state.selected_players.items():
        selected_list.append({
            "player_id": player.player_id,
            "player_name": player.player_name,
            "role": player.role,
            "real_team": player.real_team,
            "credits": player.credits,
            "is_captain": pid == st.session_state.captain,
            "is_vice_captain": pid == st.session_state.vice_captain,
        })
    
    captain_col, vc_col, submit_col = st.columns([1, 1, 1])
    
    captain_options = ["-- Select Captain --"] + [p["player_name"] for p in selected_list]
    vc_options = ["-- Select Vice-Captain --"] + [p["player_name"] for p in selected_list]
    
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
    
    with captain_col:
        captain_name = st.selectbox(
            "🏆 Captain (2x)",
            options=captain_options,
            index=current_captain_idx,
            key="captain_select",
        )
        if captain_name != "-- Select Captain --":
            for p in selected_list:
                if p["player_name"] == captain_name:
                    st.session_state.captain = p["player_id"]
                    break
        else:
            st.session_state.captain = None
    
    with vc_col:
        vc_name = st.selectbox(
            "🎖️ Vice-Captain (1.5x)",
            options=vc_options,
            index=current_vc_idx,
            key="vc_select",
        )
        if vc_name != "-- Select Vice-Captain --":
            for p in selected_list:
                if p["player_name"] == vc_name:
                    st.session_state.vice_captain = p["player_id"]
                    break
        else:
            st.session_state.vice_captain = None
    
    for p in selected_list:
        if p["player_id"] == st.session_state.captain:
            p["is_captain"] = True
            p["multiplier"] = 2.0
        elif p["player_id"] == st.session_state.vice_captain:
            p["is_vice_captain"] = True
            p["multiplier"] = 1.5
        else:
            p["multiplier"] = 1.0
    
    validation = validate_team(selected_list, rules)
    
    can_submit = (
        validation.is_valid and
        st.session_state.captain is not None and
        st.session_state.vice_captain is not None
    )
    
    with submit_col:
        st.markdown("")  
        st.markdown("")  
        
        if st.button(
            "🚀 Submit Team",
            type="primary",
            use_container_width=True,
            disabled=not can_submit,
        ):
            try:
                entry_id = save_entry(
                    st.session_state.username,
                    selected_match.match_id,
                    selected_list,
                )
                st.success(f"Team submitted successfully!")
                st.session_state.selected_players = {}
                st.session_state.captain = None
                st.session_state.vice_captain = None
                st.session_state.page = "📋 My Teams"
                st.rerun()
            except Exception as e:
                st.error(f"Failed to submit team: {e}")
    
    if selected_list:
        if not validation.is_valid:
            for error in validation.errors:
                st.error(error)
        elif len(selected_list) == rules.max_players:
            if not st.session_state.captain or not st.session_state.vice_captain:
                st.warning("Please select Captain and Vice-Captain to submit")


def render_my_teams():
    st.header("📋 My Teams")
    
    entries = get_entries()
    user_entries = entries[entries["UserName"] == st.session_state.username]
    
    if user_entries.empty:
        st.info("You haven't submitted any teams yet.")
        return
    
    rules = get_rules()
    
    for _, entry in user_entries.iterrows():
        entry_id = str(entry["EntryID"])
        match_id = str(entry["MatchID"])
        
        all_matches = get_matches()
        match = next((m for m in all_matches if m.match_id == match_id), None)
        match_name = match.match_name if match else match_id
        
        lock_time = match.lock_time if match else None
        is_locked = lock_time and datetime.now() > lock_time
        
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
    match_options = {m.match_name: m for m in all_matches}
    
    selected_match_name = st.selectbox(
        "Select Match",
        options=list(match_options.keys()),
        key="all_teams_match_select",
    )
    
    selected_match = match_options[selected_match_name]
    
    now = datetime.now()
    if selected_match.lock_time and now < selected_match.lock_time:
        st.warning(f"⏰ This match hasn't started yet. Teams will be visible after {selected_match.lock_time.strftime('%Y-%m-%d %H:%M')}")
        return
    
    teams = get_all_teams_for_match(selected_match.match_id)
    
    if not teams:
        st.info("No teams submitted for this match yet.")
        return
    
    scoring_rules = get_scoring_rules()
    player_points = get_player_points(selected_match.match_id)
    
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
            
            for s in sorted(selections, key=lambda x: x.pick_no):
                multiplier = ""
                if s.is_captain:
                    multiplier = " 🏆 (2x)"
                elif s.is_vice_captain:
                    multiplier = " 🎖️ (1.5x)"
                emoji = role_emoji.get(s.role, "❓")
                st.markdown(f"{emoji} {s.player_name} ({s.role}){multiplier}")


if __name__ == "__main__":
    main()
