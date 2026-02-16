"""Lactate Threshold Logic - LT1/LT2 Estimation without Lactate Meter"""
class LactateLogic:
    @staticmethod
    def estimate_lt1(hr_percent_max: float, drift_percent: float) -> str:
        """LT1 ≈ drift < 3% + HR < 75-78% HRmax"""
        if drift_percent < 3.0 and hr_percent_max <= 78.0:
            return "LT1_ZONE: TRUE (Pure aerobic)"
        return "LT1_ZONE: FALSE"
    
    @staticmethod
    def estimate_lt2(hr_stable: bool, rpe: float) -> str:
        """LT2 ≈ tempo → HR stable & RPE 6-7"""
        if hr_stable and 6.0 <= rpe <= 7.0:
            return "LT2_APPROX: TRUE (Threshold hit)"
        return "LT2_APPROX: FALSE"
    
    @staticmethod
    def tempo_volume_decision(is_lt2_true: bool) -> str:
        """Decide if full tempo volume is safe"""
        if is_lt2_true:
            return "TEMPO VOLUME: OK (Full planned volume)"
        return "TEMPO VOLUME: DOWNGRADE (Cut reps or distance)"
