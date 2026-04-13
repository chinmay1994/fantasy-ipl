from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from enum import Enum


class PlayerRole(Enum):
    WK = "WK"
    BAT = "BAT"
    AR = "AR"
    BWL = "BWL"


class MatchStatus(Enum):
    UPCOMING = "Upcoming"
    LIVE = "Live"
    COMPLETE = "Complete"


@dataclass
class Player:
    player_id: str
    player_name: str
    role: str
    real_team: str
    credits: float = 0.0


@dataclass
class MatchSquadPlayer:
    match_id: str
    player_id: str
    player_name: str
    role: str
    real_team: str
    credits: float = 0.0
    in_starting_xi: bool = False


@dataclass
class Match:
    match_id: str
    match_name: str
    start_time: datetime
    team_a: str
    team_b: str
    status: str
    lock_time: datetime


@dataclass
class FantasySelection:
    entry_id: str
    match_id: str
    user_name: str
    pick_no: int
    player_id: str
    player_name: str
    role: str
    real_team: str
    credits: float
    is_captain: bool
    is_vice_captain: bool


@dataclass
class FantasyTeam:
    entry_id: str
    match_id: str
    user_name: str
    submitted_at: datetime
    players: list[FantasySelection]
    total_points: float = 0.0


@dataclass
class Rules:
    max_players: int = 11
    min_wk: int = 1
    min_bat: int = 1
    min_ar: int = 1
    min_bwl: int = 1
    max_from_one_team: int = 7
    salary_cap: float = 100.0
    captain_multiplier: float = 2.0
    vice_captain_multiplier: float = 1.5


@dataclass
class ScoringRules:
    bat_run: float = 1.0
    four_bonus: float = 1.0
    six_bonus: float = 2.0
    run_30_bonus: float = 4.0
    run_50_bonus: float = 10.0
    run_100_bonus: float = 20.0
    wicket: float = 25.0
    wicket_3_bonus: float = 10.0
    wicket_4_bonus: float = 20.0
    maiden_over: float = 12.0
    catch: float = 8.0
    stumping: float = 12.0
    run_out_direct: float = 12.0
    run_out_assist: float = 6.0
    duck_penalty: float = -2.0


@dataclass
class PlayerPoints:
    match_id: str
    player_id: str
    player_name: str
    role: str
    real_team: str
    in_starting_xi: bool
    runs: int
    fours: int
    sixes: int
    wickets: int
    catches: int
    stumpings: int
    run_out_direct: int
    run_out_assist: int
    maidens: int
    batting_pts: float
    bat_bonus_pts: float
    bowling_pts: float
    bowling_bonus_pts: float
    fielding_pts: float
    total_pts: float
