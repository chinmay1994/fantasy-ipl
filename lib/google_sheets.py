import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Optional
import gspread
from google.oauth2 import service_account
from lib.models import (
    Match,
    Player,
    MatchSquadPlayer,
    FantasySelection,
    FantasyTeam,
    Rules,
    ScoringRules,
    PlayerPoints,
)


@st.cache_resource(ttl=300)
def get_gspread_client():
    try:
        service_account_info = {
            "type": st.secrets["google"]["type"],
            "project_id": st.secrets["google"]["project_id"],
            "private_key_id": st.secrets["google"]["private_key_id"],
            "private_key": st.secrets["google"]["private_key"],
            "client_email": st.secrets["google"]["client_email"],
            "client_id": st.secrets["google"]["client_id"],
            "auth_uri": st.secrets["google"]["auth_uri"],
            "token_uri": st.secrets["google"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["google"]["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["google"]["client_x509_cert_url"],
        }
        creds = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"],
        )
        return gspread.authorize(creds)
    except Exception:
        return None


def clear_all_caches():
    get_gspread_client.clear()
    get_rules.clear()
    get_scoring_rules.clear()
    get_matches.clear()
    get_upcoming_matches.clear()
    get_all_records.clear()
    get_match_squad.clear()
    get_entries.clear()
    get_player_points.clear()


def get_spreadsheet():
    client = get_gspread_client()
    if client is None:
        return None
    
    try:
        spreadsheet_url = st.secrets["general"]["spreadsheet"]
        spreadsheet_id = spreadsheet_url.split("/d/")[1].split("/")[0]
        return client.open_by_key(spreadsheet_id)
    except Exception as e:
        st.error(f"Failed to open spreadsheet: {e}")
        return None


def get_worksheet(sheet_name: str):
    spreadsheet = get_spreadsheet()
    if spreadsheet is None:
        return None
    try:
        return spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        st.error(f"Worksheet '{sheet_name}' not found")
        return None


@st.cache_data(ttl=300)
def get_all_records(sheet_name: str) -> pd.DataFrame:
    worksheet = get_worksheet(sheet_name)
    if worksheet is None:
        return pd.DataFrame()
    try:
        data = worksheet.get_all_values()
        if not data:
            return pd.DataFrame()
        if len(data) == 1:
            return pd.DataFrame(columns=data[0])
        return pd.DataFrame(data[1:], columns=data[0])
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def get_rules() -> Rules:
    df = get_all_records("Rules")
    rules = Rules()
    
    for _, row in df.iterrows():
        key = str(row.get("Contest Controls", "")).strip().lower().replace(" ", "_").replace("-", "_")
        value = str(row.get("Unnamed: 1", "")).strip()
        
        if not value:
            continue
            
        try:
            if key == "max_players_per_fantasy_team":
                rules.max_players = int(value)
            elif key == "min_wk":
                rules.min_wk = int(value)
            elif key == "min_bat":
                rules.min_bat = int(value)
            elif key == "min_ar":
                rules.min_ar = int(value)
            elif key == "min_bwl":
                rules.min_bwl = int(value)
            elif key == "max_from_one_real_team":
                rules.max_from_one_team = int(value)
            elif key == "salary_cap":
                rules.salary_cap = float(value)
            elif key == "captain_multiplier":
                rules.captain_multiplier = float(value)
            elif key == "vice_captain_multiplier":
                rules.vice_captain_multiplier = float(value)
        except (ValueError, TypeError):
            continue
    
    return rules


@st.cache_data(ttl=300)
@st.cache_data(ttl=300)
def get_scoring_rules() -> ScoringRules:
    df = get_all_records("Rules")
    scoring = ScoringRules()
    
    for _, row in df.iterrows():
        key = str(row.get("Contest Controls", "")).strip().lower().replace(" ", "_").replace("-", "_")
        value = str(row.get("Unnamed: 1", "")).strip()
        
        if not value:
            continue
            
        try:
            if key == "bat_run":
                scoring.bat_run = float(value)
            elif key == "four_bonus":
                scoring.four_bonus = float(value)
            elif key == "six_bonus":
                scoring.six_bonus = float(value)
            elif key == "30_run_bonus":
                scoring.run_30_bonus = float(value)
            elif key == "50_run_bonus":
                scoring.run_50_bonus = float(value)
            elif key == "100_run_bonus":
                scoring.run_100_bonus = float(value)
            elif key == "wicket":
                scoring.wicket = float(value)
            elif key == "3_wicket_bonus":
                scoring.wicket_3_bonus = float(value)
            elif key == "4_wicket_bonus":
                scoring.wicket_4_bonus = float(value)
            elif key == "maiden_over":
                scoring.maiden_over = float(value)
            elif key == "catch":
                scoring.catch = float(value)
            elif key == "stumping":
                scoring.stumping = float(value)
            elif key == "run_out_direct":
                scoring.run_out_direct = float(value)
            elif key == "run_out_assist":
                scoring.run_out_assist = float(value)
            elif key == "duck_penalty":
                scoring.duck_penalty = float(value)
        except (ValueError, TypeError):
            continue
    
    return scoring


@st.cache_data(ttl=300)
def get_matches() -> list[Match]:
    df = get_all_records("Matches")
    matches = []
    
    for _, row in df.iterrows():
        try:
            start_time = row.get("StartTime", "")
            if isinstance(start_time, str):
                start_time = pd.to_datetime(start_time)
            
            lock_time = row.get("LockTime", "")
            if isinstance(lock_time, str):
                lock_time = pd.to_datetime(lock_time)
            
            matches.append(Match(
                match_id=str(row.get("MatchID", "")),
                match_name=str(row.get("MatchName", "")),
                start_time=start_time,
                team_a=str(row.get("TeamA", "")),
                team_b=str(row.get("TeamB", "")),
                status=str(row.get("Status", "Upcoming")),
                lock_time=lock_time,
            ))
        except Exception:
            continue
    
    return matches


@st.cache_data(ttl=300)
def get_upcoming_matches() -> list[Match]:
    all_matches = get_matches()
    now = datetime.now()
    return [m for m in all_matches if m.lock_time and m.lock_time > now]


def get_live_matches() -> list[Match]:
    all_matches = get_matches()
    now = datetime.now()
    live = []
    for m in all_matches:
        if m.lock_time and m.start_time:
            if m.start_time <= now <= m.start_time + pd.Timedelta(hours=6):
                if m.status.lower() not in ['complete']:
                    live.append(m)
    return live


def get_completed_matches() -> list[Match]:
    all_matches = get_matches()
    now = datetime.now()
    return [m for m in all_matches if m.status.lower() == 'complete' or (m.lock_time and m.lock_time < now)]


@st.cache_data(ttl=300, show_spinner=False)
def get_match_squad(match_id: str) -> list[MatchSquadPlayer]:
    df = get_all_records("MatchSquad")
    if df.empty or "MatchID" not in df.columns:
        return []
    df = df[df["MatchID"] == match_id]
    
    players = []
    for _, row in df.iterrows():
        credits_val = row.get("Credits", "")
        try:
            credits = float(credits_val) if credits_val and str(credits_val).strip() else 0.0
        except (ValueError, TypeError):
            credits = 0.0
        
        starting_xi = row.get("InStartingXI (1/0)", "")
        try:
            in_xi = bool(int(starting_xi)) if starting_xi and str(starting_xi).strip() else False
        except (ValueError, TypeError):
            in_xi = False
        
        players.append(MatchSquadPlayer(
            match_id=str(row.get("MatchID", "")),
            player_id=str(row.get("PlayerID", "")),
            player_name=str(row.get("PlayerName", "")),
            role=str(row.get("Role", "")),
            real_team=str(row.get("RealTeam", "")),
            credits=credits,
            in_starting_xi=in_xi,
        ))
    
    return players


@st.cache_data(ttl=60)
def get_entries() -> pd.DataFrame:
    return get_all_records("Entries")


@st.cache_data(ttl=60)
def get_fantasy_selections() -> pd.DataFrame:
    return get_all_records("FantasySelections")


def get_user_entries(username: str) -> pd.DataFrame:
    entries = get_entries()
    if entries.empty or "UserName" not in entries.columns:
        return pd.DataFrame()
    return entries[entries["UserName"] == username]


def get_team_selections(entry_id: str) -> list[FantasySelection]:
    df = get_fantasy_selections()
    if df.empty or "EntryID" not in df.columns:
        return []
    df = df[df["EntryID"].astype(str) == str(entry_id)]
    if df.empty:
        return []
    df = df.sort_values("PickNo")
    
    selections = []
    for _, row in df.iterrows():
        is_captain_val = row.get("IsCaptain (1/0)", 0)
        is_captain = str(is_captain_val) == "1" if is_captain_val else False
        
        is_vc_val = row.get("IsViceCaptain (1/0)", 0)
        is_vice_captain = str(is_vc_val) == "1" if is_vc_val else False
        
        selections.append(FantasySelection(
            entry_id=str(row.get("EntryID", "")),
            match_id=str(row.get("MatchID", "")),
            user_name=str(row.get("UserName", "")),
            pick_no=int(row.get("PickNo", 0)),
            player_id=str(row.get("PlayerID", "")),
            player_name=str(row.get("PlayerName", "")),
            role=str(row.get("Role", "")),
            real_team=str(row.get("RealTeam", "")),
            credits=float(row.get("Credits", 0)) if not pd.isna(row.get("Credits")) else 0.0,
            is_captain=is_captain,
            is_vice_captain=is_vice_captain,
        ))
    
    return selections


def entry_exists(username: str, match_id: str) -> Optional[str]:
    worksheet = get_worksheet("Entries")
    if worksheet is None:
        return None
    try:
        data = worksheet.get_all_values()
        if len(data) <= 1:
            return None
        headers = data[0]
        if "UserName" not in headers or "MatchID" not in headers:
            return None
        user_idx = headers.index("UserName")
        match_idx = headers.index("MatchID")
        entry_idx = headers.index("EntryID")
        
        for row in data[1:]:
            if len(row) <= max(user_idx, match_idx, entry_idx):
                continue
            if row[user_idx] == username and str(row[match_idx]) == str(match_id):
                return str(row[entry_idx])
    except Exception:
        pass
    return None


def save_entry(username: str, match_id: str, players: list[dict]) -> str:
    worksheet = get_worksheet("Entries")
    selections_worksheet = get_worksheet("FantasySelections")
    
    if worksheet is None or selections_worksheet is None:
        raise Exception("Could not access worksheets")
    
    existing_entry_id = entry_exists(username, match_id)
    
    if existing_entry_id:
        delete_entry_selections(existing_entry_id)
        entry_id = existing_entry_id
    else:
        all_entries = get_entries()
        if all_entries.empty:
            max_entry_id = 0
        else:
            max_entry_id = all_entries["EntryID"].astype(str).str.replace("E", "").astype(int).max()
        entry_id = f"E{max_entry_id + 1}"
        
        worksheet.append_row([
            entry_id,
            match_id,
            username,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "",
        ])
    
    for i, player in enumerate(players, 1):
        selections_worksheet.append_row([
            entry_id,
            match_id,
            username,
            i,
            player["player_id"],
            player["player_name"],
            player["role"],
            player["real_team"],
            player.get("credits", 0),
            1 if player.get("is_captain") else 0,
            1 if player.get("is_vice_captain") else 0,
            1,
            0,
            player.get("multiplier", 1.0),
            0,
            1,
        ])
    
    clear_all_caches()
    return entry_id


def delete_entry_selections(entry_id: str):
    worksheet = get_worksheet("FantasySelections")
    if worksheet is None:
        return
    
    try:
        data = worksheet.get_all_values()
        if len(data) <= 1:
            return
        
        headers = data[0]
        if "EntryID" not in headers:
            return
        
        entry_idx = headers.index("EntryID")
        rows_to_delete = []
        
        for i, row in enumerate(data[1:], start=2):
            if len(row) <= entry_idx:
                continue
            if str(row[entry_idx]) == str(entry_id):
                rows_to_delete.append(i)
        
        for row_num in sorted(rows_to_delete, reverse=True):
            try:
                worksheet.delete_rows(row_num)
            except Exception:
                pass
    except Exception:
        pass


def delete_entry(entry_id: str):
    delete_entry_selections(entry_id)
    
    worksheet = get_worksheet("Entries")
    if worksheet is None:
        return
    
    try:
        data = worksheet.get_all_values()
        if len(data) <= 1:
            return
        
        headers = data[0]
        if "EntryID" not in headers:
            return
        
        entry_idx = headers.index("EntryID")
        rows_to_delete = []
        
        for i, row in enumerate(data[1:], start=2):
            if len(row) <= entry_idx:
                continue
            if str(row[entry_idx]) == str(entry_id):
                rows_to_delete.append(i)
        
        for row_num in sorted(rows_to_delete, reverse=True):
            try:
                worksheet.delete_rows(row_num)
            except Exception:
                pass
    except Exception:
        pass
    
    clear_all_caches()


@st.cache_data(ttl=300, show_spinner=False)
def get_player_points(match_id: str) -> pd.DataFrame:
    df = get_all_records("PlayerPoints")
    return df[df["MatchID"] == match_id]


def get_all_teams_for_match(match_id: str) -> list[FantasyTeam]:
    entries = get_entries()
    if entries.empty or "MatchID" not in entries.columns:
        return []
    match_entries = entries[entries["MatchID"].astype(str) == str(match_id)]
    
    teams = []
    for _, row in match_entries.iterrows():
        entry_id = str(row["EntryID"])
        selections = get_team_selections(entry_id)
        
        teams.append(FantasyTeam(
            entry_id=entry_id,
            match_id=str(row["MatchID"]),
            user_name=str(row["UserName"]),
            submitted_at=pd.to_datetime(row.get("SubmittedAt", datetime.now())),
            players=selections,
        ))
    
    return teams
