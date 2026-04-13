from typing import Optional
from dataclasses import dataclass
from lib.models import Rules


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str]
    warnings: list[str]

    def __bool__(self):
        return self.is_valid


def validate_team(
    selected_players: list[dict],
    rules: Rules,
) -> ValidationResult:
    errors = []
    warnings = []
    
    if len(selected_players) != rules.max_players:
        errors.append(
            f"Must select exactly {rules.max_players} players "
            f"(currently {len(selected_players)})"
        )
        return ValidationResult(is_valid=False, errors=errors, warnings=warnings)
    
    wk_count = sum(1 for p in selected_players if p["role"] == "WK")
    bat_count = sum(1 for p in selected_players if p["role"] == "BAT")
    ar_count = sum(1 for p in selected_players if p["role"] == "AR")
    bwl_count = sum(1 for p in selected_players if p["role"] == "BWL")
    
    if wk_count < rules.min_wk:
        errors.append(f"Minimum {rules.min_wk} Wicket-Keeper required (have {wk_count})")
    
    if bat_count < rules.min_bat:
        errors.append(f"Minimum {rules.min_bat} Batsman required (have {bat_count})")
    
    if ar_count < rules.min_ar:
        errors.append(f"Minimum {rules.min_ar} All-Rounder required (have {ar_count})")
    
    if bwl_count < rules.min_bwl:
        errors.append(f"Minimum {rules.min_bwl} Bowler required (have {bwl_count})")
    
    from collections import Counter
    team_counts = Counter(p["real_team"] for p in selected_players)
    
    for team, count in team_counts.items():
        if count > rules.max_from_one_team:
            errors.append(
                f"Maximum {rules.max_from_one_team} players from {team} allowed "
                f"(have {count})"
            )
    
    captains = [p for p in selected_players if p.get("is_captain")]
    if len(captains) != 1:
        errors.append("Must have exactly 1 Captain")
    
    vice_captains = [p for p in selected_players if p.get("is_vice_captain")]
    if len(vice_captains) != 1:
        errors.append("Must have exactly 1 Vice-Captain")
    
    if captains and vice_captains:
        if captains[0]["player_id"] == vice_captains[0]["player_id"]:
            errors.append("Captain and Vice-Captain must be different players")
    
    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def get_team_stats(selected_players: list[dict]) -> dict:
    from collections import Counter
    
    return {
        "total_players": len(selected_players),
        "wk_count": sum(1 for p in selected_players if p["role"] == "WK"),
        "bat_count": sum(1 for p in selected_players if p["role"] == "BAT"),
        "ar_count": sum(1 for p in selected_players if p["role"] == "AR"),
        "bwl_count": sum(1 for p in selected_players if p["role"] == "BWL"),
        "team_breakdown": dict(Counter(p["real_team"] for p in selected_players)),
        "captain": next((p["player_name"] for p in selected_players if p.get("is_captain")), None),
        "vice_captain": next((p["player_name"] for p in selected_players if p.get("is_vice_captain")), None),
    }
