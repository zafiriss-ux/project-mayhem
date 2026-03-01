"""
TITAN Equipment Manager
Shoe tracking, surface analysis, and training intent awareness
"""

from typing import Dict, Tuple, Optional


class EquipmentManager:
    """
    Shoe and surface management with training intent awareness.

    Tracks running shoe mileage, validates shoe selection for training type,
    and flags surface-related injury risks.

    Key Features:
    - Mileage tracking per shoe
    - Training intent validation (don't race in trainers, don't easy in super shoes)
    - Surface risk assessment (intervals on concrete = high impact)
    - Shoe lifecycle management (retirement at max km)

    Scientific Basis:
    - Shoe lifespan: 500-800km (Tenforde et al., 2020)
    - Shoe rotation reduces injury risk by 39% (Malisoux et al., 2013)
    - Surface hardness impacts loading rates (Dixon et al., 2000)
    """

    def __init__(self):
        """
        Initialize equipment manager with demo shoe database.

        In production, this would load from persistent storage.
        """
        # Demo database - In practice, these would be saved to JSON/DB
        self.shoes: Dict[str, Dict[str, any]] = {
            "1": {
                "name": "Daily Trainers (Pegasus)",
                "km": 450,
                "max_km": 800,
                "type": "DAILY"
            },
            "2": {
                "name": "Super Shoes (Vaporfly)",
                "km": 120,
                "max_km": 400,
                "type": "RACE"
            },
            "3": {
                "name": "Old Beaters",
                "km": 950,
                "max_km": 800,
                "type": "RECOVERY"
            }
        }

    def check_gear(
        self,
        session_type: str,
        shoe_id: str,
        surface: str
    ) -> Tuple[bool, str]:
        """
        Validate if equipment matches training intent and assess risks.

        Training Intent Logic:
        - Fast sessions (INTERVALS, TEMPO, HAMMER) require proper support
        - Recovery shoes should not be used for high-intensity work
        - Super shoes (race shoes) should be reserved for quality sessions

        Surface Risk Logic:
        - High-impact sessions on concrete increase injury risk
        - Prefer softer surfaces (track, grass, trail) for intervals

        Args:
            session_type: Type of training session (EASY, TEMPO, INTERVALS, etc.)
            shoe_id: ID of the shoe to be used
            surface: Running surface (TRACK, ROAD, TRAIL, CONCRETE, GRASS)

        Returns:
            Tuple of (is_allowed, message)
                - is_allowed: False if session should be blocked
                - message: Description of issue or approval

        Example:
            >>> em.check_gear("INTERVALS", "3", "CONCRETE")
            (False, "BLOCK: Cannot run Fast in Recovery shoes.")
        """
        shoe = self.shoes.get(shoe_id)
        if not shoe:
            return False, "Unknown Shoe"

        risk_flags = []

        # 1. Mileage Check
        # Shoes lose cushioning after max_km, increasing injury risk
        if shoe["km"] > shoe["max_km"]:
            risk_flags.append(f"SHOE EXPIRED ({shoe['km']}km). Risk of injury.")

        # 2. Type Mismatch (Intent Awareness)
        # Block dangerous mismatches (fast work in recovery shoes)
        if session_type in ["INTERVALS", "TEMPO", "HAMMER"] and shoe["type"] == "RECOVERY":
            return False, "BLOCK: Cannot run Fast in Recovery shoes."

        # Warn about wasteful usage (race shoes for easy runs)
        if session_type == "EASY" and shoe["type"] == "RACE":
            risk_flags.append("WASTE: Using Super Shoes for easy run.")

        # 3. Surface Logic
        # High-impact sessions on hard surfaces = injury risk
        if session_type == "INTERVALS" and surface == "CONCRETE":
            risk_flags.append("SURFACE RISK: High impact intervals on concrete.")

        if risk_flags:
            return True, " | ".join(risk_flags)

        return True, "GEAR OK"

    def add_shoe(
        self,
        shoe_id: str,
        name: str,
        shoe_type: str = "DAILY",
        max_km: int = 800
    ) -> None:
        """
        Add a new shoe to the equipment database.

        Args:
            shoe_id: Unique identifier for the shoe
            name: Descriptive name (e.g., "Nike Pegasus 40")
            shoe_type: Type of shoe ("DAILY", "RACE", "RECOVERY", "TRAIL")
            max_km: Maximum recommended mileage before retirement
        """
        self.shoes[shoe_id] = {
            "name": name,
            "km": 0,
            "max_km": max_km,
            "type": shoe_type
        }

    def update_mileage(self, shoe_id: str, distance_km: float) -> bool:
        """
        Update shoe mileage after a run.

        Args:
            shoe_id: ID of the shoe used
            distance_km: Distance run in this session

        Returns:
            True if update successful, False if shoe not found
        """
        if shoe_id not in self.shoes:
            return False

        self.shoes[shoe_id]["km"] += distance_km
        return True

    def get_shoe_status(self, shoe_id: str) -> Optional[Dict[str, any]]:
        """
        Get current status of a shoe.

        Args:
            shoe_id: ID of the shoe

        Returns:
            Dictionary with shoe info and health status, or None if not found
        """
        if shoe_id not in self.shoes:
            return None

        shoe = self.shoes[shoe_id]
        current_km = shoe["km"]
        max_km = shoe["max_km"]

        # Calculate remaining life
        remaining_km = max(0, max_km - current_km)
        health_pct = (1 - (current_km / max_km)) * 100 if max_km > 0 else 0

        status = "GOOD"
        if current_km > max_km:
            status = "EXPIRED"
        elif current_km > max_km * 0.8:
            status = "RETIRING"

        return {
            **shoe,
            "remaining_km": remaining_km,
            "health_pct": health_pct,
            "status": status
        }

    def list_all_shoes(self) -> Dict[str, Dict[str, any]]:
        """
        Get all shoes with their current status.

        Returns:
            Dictionary of all shoes with status information
        """
        return {
            shoe_id: self.get_shoe_status(shoe_id)
            for shoe_id in self.shoes
        }
