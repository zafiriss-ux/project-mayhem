"""
TITAN Periodization Manager
Race goal and training phase management based on scientific periodization principles
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Literal


class PeriodizationManager:
    """
    Race goal and training phase management.

    Manages athlete training goals and automatically calculates training phases
    based on race date proximity. Implements classical periodization model:
    - BASE: Aerobic foundation building (>70 days out)
    - BUILD: Progressive overload (35-70 days)
    - PEAK: Race-specific intensity (10-35 days)
    - TAPER: Fatigue reduction, freshness optimization (1-10 days)
    - POST_RACE: Recovery and adaptation (after race)

    Based on periodization research by:
    - Bompa & Haff (2009) - Periodization: Theory and Methodology
    - Issurin (2010) - New horizons for the methodology and physiology of training periodization
    """

    def __init__(self, athlete_profile):
        """
        Initialize periodization manager.

        Args:
            athlete_profile: UniversalAthleteProfile instance
        """
        self.athlete = athlete_profile
        self.goals: List[Dict[str, Any]] = []
        self.current_goal: Optional[Dict[str, Any]] = None
        self.completed_goals: List[Dict[str, Any]] = []

    def add_goal(
        self,
        distance_km: float,
        target_time_str: str,
        race_date_str: str
    ) -> Dict[str, Any]:
        """
        Add a new race goal.

        Args:
            distance_km: Race distance in kilometers
            target_time_str: Target finish time (e.g., "1:30:00")
            race_date_str: Race date in format "YYYY-MM-DD"

        Returns:
            Dictionary containing the created goal

        Example:
            >>> pm.add_goal(21.1, "1:30:00", "2026-04-26")
        """
        goal = {
            "goal_id": f"GOAL_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "distance_km": distance_km,
            "target_time": target_time_str,
            "race_date": datetime.strptime(race_date_str, "%Y-%m-%d"),
            "status": "ACTIVE",
            "created": datetime.now()
        }

        self.goals.append(goal)
        self.current_goal = goal

        # Update athlete profile
        self.athlete.current_goal = f"{distance_km}K in {target_time_str}"
        self.athlete.race_day = goal["race_date"]
        self.athlete.target_time = target_time_str

        return goal

    def calculate_phase(
        self,
        race_date: datetime
    ) -> Literal["POST_RACE", "TAPER", "PEAK", "BUILD", "BASE"]:
        """
        Calculate current training phase based on days to race.

        Training phases follow classical periodization:
        - BASE (>70 days): High volume, low intensity, aerobic foundation
        - BUILD (35-70 days): Progressive overload, threshold work
        - PEAK (10-35 days): Race-specific intensity, sharpening
        - TAPER (1-10 days): Volume reduction, maintain intensity
        - POST_RACE (after): Recovery, adaptation, deload

        Args:
            race_date: Target race date

        Returns:
            Training phase as string

        Scientific Basis:
            - Taper duration: 10-14 days optimal (Bosquet et al., 2007)
            - Peak phase: 3-5 weeks race-specific work (Daniels, 2005)
            - Build phase: 4-6 weeks progressive overload
            - Base phase: 8+ weeks foundation building
        """
        today = datetime.now()
        days_to_race = (race_date - today).days

        if days_to_race < 0:
            return "POST_RACE"
        elif days_to_race <= 10:
            return "TAPER"
        elif days_to_race <= 35:
            return "PEAK"
        elif days_to_race <= 70:
            return "BUILD"
        else:
            return "BASE"

    def complete_goal(
        self,
        goal_id: str,
        actual_time_str: str
    ) -> Optional[Dict[str, Any]]:
        """
        Mark a goal as completed and generate next goal suggestions.

        Args:
            goal_id: ID of the completed goal
            actual_time_str: Actual finish time

        Returns:
            Dictionary with completed goal info and suggestions for next goals,
            or None if goal not found

        Suggestion Logic:
            - IMPROVE: Same distance, faster time (2-5% improvement)
            - STEP_UP: Double the distance (e.g., 10K → Half Marathon)
        """
        # Find the goal
        goal = next((g for g in self.goals if g["goal_id"] == goal_id), None)
        if not goal:
            return None

        # Mark as completed
        goal["status"] = "COMPLETED"
        goal["actual_time"] = actual_time_str
        goal["completion_date"] = datetime.now()

        # Move to completed list
        self.completed_goals.append(goal)
        self.goals = [g for g in self.goals if g["goal_id"] != goal_id]

        # Generate suggestions for next goals
        dist = goal["distance_km"]
        suggestions = [
            {
                "type": "IMPROVE",
                "distance": dist,
                "description": f"Improve {dist}K time by 2-5 percent"
            },
            {
                "type": "STEP_UP",
                "distance": dist * 2,
                "description": f"Step up to {dist * 2}K"
            }
        ]

        return {
            "completed": goal,
            "suggestions": suggestions
        }
