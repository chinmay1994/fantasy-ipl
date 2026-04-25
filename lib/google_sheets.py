import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Optional
import pytz
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

IST = pytz.timezone('Asia/Kolkata')
IST_OFFSET = timedelta(hours=5, minutes=30)


def now_ist() -> datetime:
    return datetime.now(IST)


def to_ist(dt: datetime) -> datetime:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return IST.localize(dt)
    return dt.astimezone(IST)


def is_match_live(match: Match) -> bool:
    if match.status and match.status.lower() == 'live':
        return True
    if match.status and match.status.lower() == 'complete':
        return False
    
    now = now_ist()
    
    if match.lock_time and match.start_time:
        lock_time_ist = to_ist(match.lock_time)
        start_time_ist = to_ist(match.start_time)
        
        if lock_time_ist <= now <= start_time_ist + timedelta(hours=6):
            return True
    
    return False


def is_match_completed(match: Match) -> bool:
    if match.status and match.status.lower() == 'complete':
        return True
    
    now = now_ist()
    
    if match.lock_time:
        lock_time_ist = to_ist(match.lock_time)
        if lock_time_ist < now and match.status.lower() != 'live':
            return True
    
    return False


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
    st.cache_data.clear()


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


# TTL Constants (in seconds)
TTL_LIVE = 60      # Matches, PlayerPoints, Leaderboard
TTL_DATA = 300     # Entries, Selections, Users
TTL_STATIC = 3600  # Rules, Squads, Players

@st.cache_data(ttl=TTL_LIVE, show_spinner=False)
def get_all_records_live(sheet_name: str) -> pd.DataFrame:
    return _fetch_all_records(sheet_name)

@st.cache_data(ttl=TTL_DATA, show_spinner=False)
def get_all_records_data(sheet_name: str) -> pd.DataFrame:
    return _fetch_all_records(sheet_name)

@st.cache_data(ttl=TTL_STATIC, show_spinner=False)
def get_all_records_static(sheet_name: str) -> pd.DataFrame:
    return _fetch_all_records(sheet_name)

def _fetch_all_records(sheet_name: str) -> pd.DataFrame:
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

def get_all_records(sheet_name: str) -> pd.DataFrame:
    """Central dispatcher for tiered caching"""
    live_sheets = ["Matches", "PlayerPoints", "Leaderboard", "BallByBall", "OverSummary"]
    static_sheets = ["Rules", "MatchSquad", "Players", "Matches_Archive"]
    
    if sheet_name in live_sheets:
        return get_all_records_live(sheet_name)
    elif sheet_name in static_sheets:
        return get_all_records_static(sheet_name)
    else:
        return get_all_records_data(sheet_name)

# Attach clear method for backward compatibility
def _clear_all_records_cache():
    get_all_records_live.clear()
    get_all_records_data.clear()
    get_all_records_static.clear()
get_all_records.clear = _clear_all_records_cache


@st.cache_data(ttl=TTL_STATIC, show_spinner=False)
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


@st.cache_data(ttl=TTL_STATIC)
@st.cache_data(ttl=TTL_STATIC)
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


@st.cache_data(ttl=TTL_LIVE)
def get_matches() -> list[Match]:
    df = get_all_records("Matches")
    matches = []
    
    for _, row in df.iterrows():
        try:
            start_time = row.get("StartTime", "")
            if isinstance(start_time, str) and start_time:
                start_time = pd.to_datetime(start_time)
                if start_time.tzinfo is None:
                    start_time = IST.localize(start_time)
            
            lock_time = row.get("LockTime", "")
            if isinstance(lock_time, str) and lock_time:
                lock_time = pd.to_datetime(lock_time)
                if lock_time.tzinfo is None:
                    lock_time = IST.localize(lock_time)
            
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


@st.cache_data(ttl=60)
def get_upcoming_matches() -> list[Match]:
    all_matches = get_matches()
    now = now_ist()
    upcoming = []
    
    for m in all_matches:
        status_lower = m.status.lower() if m.status else ""
        
        if status_lower == 'open' and m.lock_time:
            lock_time_ist = to_ist(m.lock_time)
            if lock_time_ist > now:
                upcoming.append(m)
    
    return upcoming


def get_live_matches() -> list[Match]:
    all_matches = get_matches()
    live = []
    
    for m in all_matches:
        if is_match_live(m):
            live.append(m)
    
    return live


def get_completed_matches() -> list[Match]:
    all_matches = get_matches()
    completed = []
    
    for m in all_matches:
        if is_match_completed(m):
            completed.append(m)
    
    return completed


TEAM_NAMES = {
    "GT": "Gujarat Titans",
    "MI": "Mumbai Indians",
    "CSK": "Chennai Super Kings",
    "RCB": "Royal Challengers Bengaluru",
    "PBKS": "Punjab Kings",
    "KKR": "Kolkata Knight Riders",
    "RR": "Rajasthan Royals",
    "LSG": "Lucknow Super Giants",
    "DC": "Delhi Capitals",
    "SRH": "Sunrisers Hyderabad",
}

@st.cache_data(ttl=60)
def get_match_score(match_id: str) -> str:
    matches_df = get_all_records("Matches")
    match_row = matches_df[matches_df.get("MatchID", "") == match_id]
    if match_row.empty:
        return ""
    
    team_a = str(match_row.iloc[0].get("TeamA", "")).strip()
    team_b = str(match_row.iloc[0].get("TeamB", "")).strip()
    team_a_full = TEAM_NAMES.get(team_a, team_a)
    team_b_full = TEAM_NAMES.get(team_b, team_b)
    
    bbb_df = get_all_records("BallByBall")
    innings_df = bbb_df[bbb_df.get("MatchID", "") == match_id]
    if innings_df.empty:
        return ""
    
    current_innings = int(innings_df["Innings"].max())
    
    # Determine batting team from latest ball
    squad_df = get_all_records("MatchSquad")
    squad_match = squad_df[squad_df.get("MatchID", "") == match_id]
    
    latest_ball = innings_df.iloc[-1]
    latest_batter = str(latest_ball.get("BatterID", "")).strip()
    
    batter_row = squad_match[squad_match.get("PlayerID", "") == latest_batter]
    batting_team = str(batter_row.iloc[0].get("RealTeam", "")).strip() if not batter_row.empty else team_a
    
    def calc_innings_score(innings_num):
        inn_df = innings_df[innings_df["Innings"] == str(innings_num)]
        if inn_df.empty:
            return None
        try:
            runs = int(inn_df["TotalRuns"].astype(float).sum())
        except:
            runs = 0
        try:
            runs_bat = int(inn_df["RunsBat"].astype(float).sum())
        except:
            runs_bat = 0
        try:
            extras = int(inn_df["Extras"].astype(float).sum())
        except:
            extras = 0
        total = runs_bat + extras
        try:
            wickets = len(inn_df[inn_df["WicketFlag (1/0)"].astype(str) == '1'])
        except:
            wickets = 0
        try:
            # Ensure Over and Ball are numeric for correct sorting and calculation
            inn_df = inn_df.copy()
            inn_df["Over"] = pd.to_numeric(inn_df["Over"], errors='coerce')
            inn_df["Ball"] = pd.to_numeric(inn_df["Ball"], errors='coerce')
            
            # Sort by Over and Ball to find the actual latest delivery
            sorted_df = inn_df.dropna(subset=["Over", "Ball"]).sort_values(["Over", "Ball"])
            
            if sorted_df.empty:
                return None
                
            latest = sorted_df.iloc[-1]
            over_val = int(latest["Over"])
            ball_val = int(latest["Ball"])
            
            # Standard cricket notation: (Over-1).Ball
            # If Ball is 6, it's a completed over.
            if ball_val >= 6:
                overs, balls = over_val, 0
            else:
                overs, balls = over_val - 1, ball_val
        except Exception as e:
            # Fallback to simple max over if sorting fails
            try:
                max_over = pd.to_numeric(inn_df["Over"], errors='coerce').max()
                overs = int(max_over)
                balls = int((max_over - overs) * 10)
            except:
                overs, balls = 0, 0
        return f"({runs}/{wickets}, {overs}.{balls} overs)"
    
    score_inn1 = calc_innings_score(1)
    score_inn2 = calc_innings_score(2)
    
    if current_innings == 1:
        # During 1st innings, show batting team with score vs other team
        if batting_team == team_a:
            return f"{team_a_full} {score_inn1} vs {team_b_full}"
        else:
            return f"{team_b_full} {score_inn1} vs {team_a_full}"
    else:
        # 2nd innings: batting team first, then vs, then first innings team
        if batting_team == team_a:
            # Team A batting 2nd
            return f"{team_a_full} {score_inn2} vs {team_b_full} {score_inn1}"
        else:
            # Team B batting 2nd
            return f"{team_b_full} {score_inn2} vs {team_a_full} {score_inn1}"


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
        
        in_xi = False
        if isinstance(starting_xi, str):
            if starting_xi.strip() == "1":
                in_xi = True
            elif starting_xi.strip() == "0":
                in_xi = False
            elif starting_xi.strip() == "":
                in_xi = True
        elif starting_xi and (starting_xi == 1 or starting_xi == 1.0):
            in_xi = True
        
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


@st.cache_data(ttl=TTL_DATA)
def get_entries() -> pd.DataFrame:
    return get_all_records("Entries")


@st.cache_data(ttl=TTL_DATA)
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
            credits=float(row.get("Credits")) if row.get("Credits") and str(row.get("Credits")).strip() and not pd.isna(row.get("Credits")) else 0.0,
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
    
    # Second-layer validation to prevent corrupt data (e.g. 10 players or missing C/VC)
    from lib.validators import validate_team
    rules = get_rules()
    validation = validate_team(players, rules)
    if not validation.is_valid:
        error_msg = f"Team validation failed: {', '.join(validation.errors)}"
        raise Exception(error_msg)
    
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
    
    current_row_count = len(selections_worksheet.get_all_values())
    
    rows_to_append = []
    
    for i, player in enumerate(players, 1):
        rows_to_append.append([
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
        ])
    
    if rows_to_append:
        selections_worksheet.append_rows(rows_to_append, value_input_option='USER_ENTERED')
    
    if rows_to_append:
        start_row = current_row_count + 1
        end_row = start_row + len(rows_to_append) - 1
        
        formulas = []
        for i in range(len(rows_to_append)):
            row = start_row + i
            formulas.append([
                f'=IF(A{row}="","",IF(COUNTIFS(MatchSquad!$A:$A,B{row},MatchSquad!$B:$B,E{row})>0,1,0))',
                f'=IF(A{row}="","",SUMIFS(PlayerPoints!$U:$U,PlayerPoints!$A:$A,B{row},PlayerPoints!$B:$B,E{row}))',
                f'=IF(J{row}=1,Rules!$B$9,IF(K{row}=1,Rules!$B$10,1))',
                f'=IF(A{row}="","",M{row}*N{row})',
                f'=IF(AND(A{row}<>"",E{row}<>""),IF(COUNTIFS($A$2:A{row},A{row},$E$2:E{row},E{row})=1,1,0),0)',
            ])
        
        selections_worksheet.update(f'L{start_row}:P{end_row}', formulas, value_input_option='USER_ENTERED')
    
    # Update Validation and Leaderboard formulas
    try:
        validation_ws = get_worksheet("Validation")
        leaderboard_ws = get_worksheet("Leaderboard")
        
        if validation_ws and leaderboard_ws:
            # Fetch fresh entry count without cache
            entries_ws = get_worksheet("Entries")
            all_entries = entries_ws.get_all_values()
            entry_row = len(all_entries)
            r = entry_row
            
            v_formulas = [[
                f'=Entries!A{r}',
                f'=Entries!B{r}',
                f'=Entries!C{r}',
                f'=IF(A{r}="","","")',
                f'=IF(A{r}="","",COUNTIFS(FantasySelections!$A:$A,A{r}))',
                f'=IF(A{r}="","",SUMIFS(FantasySelections!$P:$P,FantasySelections!$A:$A,A{r}))',
                f'=IF(A{r}="","",COUNTIFS(FantasySelections!$A:$A,A{r},FantasySelections!$G:$G,"WK"))',
                f'=IF(A{r}="","",COUNTIFS(FantasySelections!$A:$A,A{r},FantasySelections!$G:$G,"BAT"))',
                f'=IF(A{r}="","",COUNTIFS(FantasySelections!$A:$A,A{r},FantasySelections!$G:$G,"AR"))',
                f'=IF(A{r}="","",COUNTIFS(FantasySelections!$A:$A,A{r},FantasySelections!$G:$G,"BWL"))',
                f'=IF(A{r}="","",SUMIFS(FantasySelections!$I:$I,FantasySelections!$A:$A,A{r}))',
                f'=IF(A{r}="","",COUNTIFS(FantasySelections!$A:$A,A{r},FantasySelections!$J:$J,1))',
                f'=IF(A{r}="","",COUNTIFS(FantasySelections!$A:$A,A{r},FantasySelections!$K:$K,1))',
                f'=IFERROR(VLOOKUP(B{r},Matches!$A:$E,4,FALSE()),"")',
                f'=IFERROR(VLOOKUP(B{r},Matches!$A:$E,5,FALSE()),"")',
                f'=IF(A{r}="","",COUNTIFS(FantasySelections!$A:$A,A{r},FantasySelections!$H:$H,N{r}))',
                f'=IF(A{r}="","",COUNTIFS(FantasySelections!$A:$A,A{r},FantasySelections!$H:$H,O{r}))',
                f'=IF(A{r}="","",MAX(P{r},Q{r}))',
                f'=IF(A{r}="","",SUMIFS(FantasySelections!$L:$L,FantasySelections!$A:$A,A{r}))',
                f'=IF(A{r}="","",IF(AND(E{r}=Rules!$B$2,F{r}=Rules!$B$2,G{r}>=Rules!$B$3,H{r}>=Rules!$B$4,I{r}>=Rules!$B$5,J{r}>=Rules!$B$6,K{r}<=Rules!$B$8,L{r}=1,M{r}=1,R{r}<=Rules!$B$7,S{r}=Rules!$B$2),"VALID","INVALID"))'
            ]]
            
            l_formulas = [[
                f'=Validation!A{r}',
                f'=Validation!B{r}',
                f'=Validation!C{r}',
                f'=Validation!T{r}',
                f'=IF(A{r}="","",SUMIFS(FantasySelections!$O:$O,FantasySelections!$A:$A,A{r}))',
                f'=IF(D{r}<>"VALID","",COUNTIFS($B:$B,B{r},$E:$E,">"&E{r})+1)'
            ]]
            
            # Check if we need to append or update
            # For simplicity, we'll append if the row is new
            v_data = validation_ws.get_all_values()
            if len(v_data) < r:
                validation_ws.append_row(v_formulas[0], value_input_option='USER_ENTERED')
            else:
                validation_ws.update(f'A{r}:T{r}', v_formulas, value_input_option='USER_ENTERED')
                
            l_data = leaderboard_ws.get_all_values()
            if len(l_data) < r:
                leaderboard_ws.append_row(l_formulas[0], value_input_option='USER_ENTERED')
            else:
                leaderboard_ws.update(f'A{r}:F{r}', l_formulas, value_input_option='USER_ENTERED')
                
    except Exception as e:
        print(f"Warning: Failed to update Validation/Leaderboard formulas: {e}")
        
    # Surgical Cache Clearing
    get_all_records_data.clear()
    get_all_records_live.clear()
    get_entries.clear()
    get_fantasy_selections.clear()
    get_overall_leaderboard.clear()
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


@st.cache_data(ttl=TTL_LIVE, show_spinner=False)
def get_player_points(match_id: str) -> pd.DataFrame:
    df = get_all_records("PlayerPoints")
    return df[df["MatchID"] == match_id]


@st.cache_data(ttl=86400, show_spinner=False)
def get_all_player_points() -> pd.DataFrame:
    df = get_all_records("PlayerPoints")
    return df


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


import bcrypt

@st.cache_data(ttl=TTL_DATA, show_spinner=False)
def get_users() -> pd.DataFrame:
    return get_all_records("Users")


def add_user(username: str, password: str, is_admin: bool = False) -> bool:
    ws = get_spreadsheet().worksheet("Users")
    
    try:
        users = ws.get_all_values()
        
        for row in users[1:]:
            if row[0].lower() == username.lower():
                return False
        
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        is_admin_val = "TRUE" if is_admin else "FALSE"
        ws.append_row([username, hashed, is_admin_val], value_input_option="USER_ENTERED")
        clear_all_caches()
        return True
    except Exception as e:
        print(f"Error adding user: {e}")
        users = ws.get_all_values()
        for row in users[1:]:
            if row[0].lower() == username.lower():
                return False
        raise e


def verify_user(username: str, password: str) -> tuple[bool, bool]:
    ws = get_spreadsheet().worksheet("Users")
    users = ws.get_all_values()
    
    for row in users[1:]:
        if row[0].lower() == username.lower():
            stored_hash = row[1]
            is_admin = len(row) > 2 and row[2].strip().upper() == "TRUE"
            return bcrypt.checkpw(password.encode(), stored_hash.encode()), is_admin
    
    return False, False
    

@st.cache_data(ttl=TTL_LIVE, show_spinner=False)
def get_overall_leaderboard() -> pd.DataFrame:
    """
    Aggregates scores across completed matches only.
    Returns DataFrame with: UserName, TotalPoints, Entries, Top3Finishes
    """
    try:
        # Get completed match IDs
        matches_df = get_all_records("Matches")
        if matches_df.empty:
            return pd.DataFrame()
            
        completed_match_ids = set(
            matches_df[matches_df["Status"].astype(str).str.lower() == "complete"]["MatchID"].astype(str).tolist()
        )
        
        if not completed_match_ids:
            return pd.DataFrame()

        df = get_all_records("Leaderboard")
        if df.empty:
            return pd.DataFrame()
            
        # Filter for completed matches and valid teams only
        valid_df = df[
            (df["Status"].astype(str).str.upper() == "VALID") & 
            (df["MatchID"].astype(str).isin(completed_match_ids))
        ].copy()
        
        if valid_df.empty:
            return pd.DataFrame()
            
        # Ensure TotalPoints and Rank are numeric
        valid_df["TotalPoints"] = pd.to_numeric(valid_df["TotalPoints"], errors="coerce").fillna(0)
        valid_df["Rank"] = pd.to_numeric(valid_df["Rank"], errors="coerce").fillna(999)
        
        # Add a helper column for Top 3 Finishes
        valid_df["IsTop3"] = (valid_df["Rank"] <= 3).astype(int)
        
        # Group by UserName
        overall = valid_df.groupby("UserName").agg({
            "TotalPoints": "sum",
            "EntryID": "count",
            "IsTop3": "sum"
        }).reset_index()
        
        overall.columns = ["UserName", "TotalPoints", "Entries", "Top3Finishes"]
        
        # Sort by total points descending
        overall = overall.sort_values(by="TotalPoints", ascending=False).reset_index(drop=True)
        
        return overall
    except Exception as e:
        st.error(f"Error fetching overall leaderboard: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=TTL_LIVE, show_spinner=False)
def get_player_stats_for_match(match_id: str) -> pd.DataFrame:
    """
    Returns statistics for all players in a match:
    Points scored and selection frequency by participants.
    """
    try:
        # 1. Get Match Squad (all eligible players)
        squad = get_match_squad(match_id)
        if not squad:
            return pd.DataFrame()
            
        # Create base dataframe from squad
        stats = pd.DataFrame([{
            "PlayerID": p.player_id,
            "PlayerName": p.player_name,
            "Team": p.real_team,
            "Role": p.role,
            "InXI": p.in_starting_xi
        } for p in squad])
        
        # 2. Get Player Points
        points_df = get_player_points(match_id)
        if not points_df.empty:
            points_df = points_df[["PlayerID", "TotalPts"]].copy()
            points_df["TotalPts"] = pd.to_numeric(points_df["TotalPts"], errors="coerce").fillna(0)
            stats = stats.merge(points_df, on="PlayerID", how="left")
        else:
            stats["TotalPts"] = 0
            
        stats["TotalPts"] = stats["TotalPts"].fillna(0)
        
        # 3. Get Selection Frequency
        # We'll use FantasySelections sheet directly for speed
        all_selections = get_fantasy_selections()
        if not all_selections.empty and "MatchID" in all_selections.columns:
            match_selections = all_selections[all_selections["MatchID"].astype(str) == str(match_id)].copy()
            
            # Ensure captain/vc columns are numeric
            c_col = "IsCaptain (1/0)"
            vc_col = "IsViceCaptain (1/0)"
            match_selections[c_col] = pd.to_numeric(match_selections[c_col], errors='coerce').fillna(0).astype(int)
            match_selections[vc_col] = pd.to_numeric(match_selections[vc_col], errors='coerce').fillna(0).astype(int)
            
            agg_stats = match_selections.groupby("PlayerID").agg({
                "PlayerID": "count",
                c_col: "sum",
                vc_col: "sum"
            }).rename(columns={
                "PlayerID": "SelectedBy", 
                c_col: "CaptainCount", 
                vc_col: "VCCount"
            }).reset_index()
            
            stats = stats.merge(agg_stats, on="PlayerID", how="left")
        else:
            stats["SelectedBy"] = 0
            stats["CaptainCount"] = 0
            stats["VCCount"] = 0
            
        stats["SelectedBy"] = stats["SelectedBy"].fillna(0).astype(int)
        stats["CaptainCount"] = stats["CaptainCount"].fillna(0).astype(int)
        stats["VCCount"] = stats["VCCount"].fillna(0).astype(int)
        
        # 4. Final sorting and cleanup
        stats = stats.sort_values(by="TotalPts", ascending=False).reset_index(drop=True)
        
        return stats
        
    except Exception as e:
        st.error(f"Error fetching player stats: {e}")
        return pd.DataFrame()
