from dataclasses import dataclass
from typing import Optional
from lib.models import ScoringRules, PlayerPoints, FantasySelection


def calculate_batting_points(
    runs: int,
    fours: int,
    sixes: int,
    rules: ScoringRules,
) -> tuple[float, float]:
    batting_pts = runs * rules.bat_run
    batting_pts += fours * rules.four_bonus
    batting_pts += sixes * rules.six_bonus
    
    bonus_pts = 0.0
    if runs >= 100:
        bonus_pts += rules.run_100_bonus
        bonus_pts += rules.run_50_bonus
        bonus_pts += rules.run_30_bonus
    elif runs >= 50:
        bonus_pts += rules.run_50_bonus
        bonus_pts += rules.run_30_bonus
    elif runs >= 30:
        bonus_pts += rules.run_30_bonus
    
    return batting_pts, bonus_pts


def calculate_bowling_points(
    wickets: int,
    maidens: int,
    rules: ScoringRules,
) -> tuple[float, float]:
    bowling_pts = wickets * rules.wicket
    
    bonus_pts = 0.0
    if wickets >= 4:
        bonus_pts += rules.wicket_4_bonus
    elif wickets >= 3:
        bonus_pts += rules.wicket_3_bonus
    
    bowling_pts += maidens * rules.maiden_over
    
    return bowling_pts, bonus_pts


def calculate_fielding_points(
    catches: int,
    stumpings: int,
    run_out_direct: int,
    run_out_assist: int,
    rules: ScoringRules,
) -> float:
    return (
        catches * rules.catch +
        stumpings * rules.stumping +
        run_out_direct * rules.run_out_direct +
        run_out_assist * rules.run_out_assist
    )


def calculate_player_points(
    player_stats: PlayerPoints,
    scoring_rules: ScoringRules,
    multiplier: float = 1.0,
    is_dismissed_for_zero: bool = False,
) -> float:
    batting_pts, bat_bonus = calculate_batting_points(
        player_stats.runs,
        player_stats.fours,
        player_stats.sixes,
        scoring_rules,
    )
    
    if is_dismissed_for_zero and player_stats.runs == 0:
        batting_pts += scoring_rules.duck_penalty
    
    bowling_pts, bowl_bonus = calculate_bowling_points(
        player_stats.wickets,
        player_stats.maidens,
        scoring_rules,
    )
    
    fielding_pts = calculate_fielding_points(
        player_stats.catches,
        player_stats.stumpings,
        player_stats.run_out_direct,
        player_stats.run_out_assist,
        scoring_rules,
    )
    
    total = (batting_pts + bat_bonus + bowling_pts + bowl_bonus + fielding_pts) * multiplier
    
    return round(total, 2)


def calculate_team_total(
    selections: list[FantasySelection],
    player_points_df,
    scoring_rules: ScoringRules,
) -> float:
    total = 0.0
    
    for selection in selections:
        player_id = selection.player_id
        match_id = selection.match_id
        
        player_stats = player_points_df[
            (player_points_df["player_id"] == player_id) &
            (player_points_df["match_id"] == match_id)
        ]
        
        if player_stats.empty:
            continue
        
        row = player_stats.iloc[0]
        stats = PlayerPoints(
            match_id=str(row.get("match_id", "")),
            player_id=str(row.get("player_id", "")),
            player_name=str(row.get("player_name", "")),
            role=str(row.get("role", "")),
            real_team=str(row.get("team", "")),
            in_starting_xi=bool(row.get("in_starting_xi", 0)),
            runs=int(row.get("runs", 0)),
            fours=int(row.get("fours", 0)),
            sixes=int(row.get("sixes", 0)),
            wickets=int(row.get("wickets", 0)),
            catches=int(row.get("catches", 0)),
            stumpings=int(row.get("stumpings", 0)),
            run_out_direct=int(row.get("run_out_direct", 0)),
            run_out_assist=int(row.get("run_out_assist", 0)),
            maidens=int(row.get("maidens", 0)),
            batting_pts=float(row.get("batting_pts", 0)),
            bat_bonus_pts=float(row.get("bat_bonus_pts", 0)),
            bowling_pts=float(row.get("bowling_pts", 0)),
            bowling_bonus_pts=float(row.get("bowling_bonus_pts", 0)),
            fielding_pts=float(row.get("fielding_pts", 0)),
            total_pts=float(row.get("total_pts", 0)),
        )
        
        multiplier = 1.0
        if selection.is_captain:
            multiplier = 2.0
        elif selection.is_vice_captain:
            multiplier = 1.5
        
        is_dismissed = row.get("runs", 0) == 0 and row.get("in_starting_xi", 0) == 1
        
        player_total = calculate_player_points(
            stats,
            scoring_rules,
            multiplier,
            is_dismissed,
        )
        
        total += player_total
    
    return round(total, 2)


@dataclass
class PlayerScore:
    player_name: str
    role: str
    match_id: str
    player_id: str
    is_captain: bool
    is_vice_captain: bool
    runs: int = 0
    wickets: int = 0
    catches: int = 0
    points: float = 0.0


def calculate_team_with_player_scores(
    selections: list[FantasySelection],
    player_points_df,
    scoring_rules: ScoringRules,
) -> tuple[float, list[PlayerScore]]:
    total = 0.0
    player_scores = []
    
    for selection in selections:
        player_id = selection.player_id
        match_id = selection.match_id
        
        player_stats = player_points_df[
            (player_points_df["player_id"] == player_id) &
            (player_points_df["match_id"] == match_id)
        ]
        
        multiplier = 1.0
        if selection.is_captain:
            multiplier = 2.0
        elif selection.is_vice_captain:
            multiplier = 1.5
        
        runs = 0
        wickets = 0
        catches = 0
        
        if not player_stats.empty:
            row = player_stats.iloc[0]
            runs = int(row.get("runs", 0))
            wickets = int(row.get("wickets", 0))
            catches = int(row.get("catches", 0))
            
            stats = PlayerPoints(
                match_id=str(row.get("match_id", "")),
                player_id=str(row.get("player_id", "")),
                player_name=str(row.get("player_name", "")),
                role=str(row.get("role", "")),
                real_team=str(row.get("team", "")),
                in_starting_xi=bool(row.get("in_starting_xi", 0)),
                runs=runs,
                fours=int(row.get("fours", 0)),
                sixes=int(row.get("sixes", 0)),
                wickets=wickets,
                catches=catches,
                stumpings=int(row.get("stumpings", 0)),
                run_out_direct=int(row.get("run_out_direct", 0)),
                run_out_assist=int(row.get("run_out_assist", 0)),
                maidens=int(row.get("maidens", 0)),
                batting_pts=0, bat_bonus_pts=0, bowling_pts=0,
                bowling_bonus_pts=0, fielding_pts=0, total_pts=0,
            )
            
            is_dismissed = runs == 0 and row.get("InStartingXI", 0) == 1
            player_total = calculate_player_points(stats, scoring_rules, multiplier, is_dismissed)
        else:
            player_total = 0.0
        
        total += player_total
        
        player_scores.append(PlayerScore(
            player_name=selection.player_name,
            role=selection.role,
            match_id=selection.match_id,
            player_id=selection.player_id,
            is_captain=selection.is_captain,
            is_vice_captain=selection.is_vice_captain,
            runs=runs,
            wickets=wickets,
            catches=catches,
            points=player_total,
        ))
    
    return round(total, 2), player_scores
