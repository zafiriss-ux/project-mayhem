#!/usr/bin/env python3
"""
TITAN v51 - Complete System Check
Tests all modules and functionality
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test all critical imports"""
    print("🔍 Testing imports...")
    errors = []
    
    # Science modules
    modules_to_test = [
        ('titan.science', 'ACWREngine'),
        ('titan.science', 'HRVGuidedEngine'),
        ('titan.science', 'TSBEngine'),
        ('titan.science', 'DriftEngine'),
        ('titan.science', 'BiomechanicsAnalysis'),
        ('titan.science', 'RCPEngine'),
        ('titan.science', 'TRIMPEngine'),
        ('titan.science', 'GlycogenModel'),
        ('titan.science', 'GlycogenEngine'),
        ('titan.science', 'LactateLogic'),
        ('titan.science', 'FatigueEngine'),
        ('titan.science', 'ReadinessEngine'),
        ('titan.science', 'CriticalSpeedEngine'),
        ('titan.science', 'EfficiencyEngine'),
        ('titan.science', 'DurabilityEngine'),
        ('titan.science', 'AdaptiveMemory'),
        # Core modules
        ('titan.core', 'athlete'),
        ('titan.core', 'database'),
        ('titan.core', 'equipment'),
        ('titan.core', 'periodization'),
        # Utils
        ('titan.utils', 'MathCore'),
        ('titan.utils.constants', 'SESSION_TYPES'),
        # Features
        ('titan.features', 'weekly_planner'),
        ('titan.features', 'optimal_time_calculator'),
        ('titan.features', 'nutrition_optimizer'),
        # Integrations
        ('titan.integrations', 'garmin_sync'),
        ('titan.integrations', 'weather_api'),
        ('titan.integrations', 'telegram_bot'),
        # Orchestration
        ('titan.orchestration', 'daily_coach'),
    ]
    
    for module_path, item in modules_to_test:
        try:
            module = __import__(module_path, fromlist=[item])
            getattr(module, item)
            print(f'  ✅ {module_path}.{item}')
        except Exception as e:
            errors.append(f'{module_path}.{item}: {e}')
            print(f'  ❌ {module_path}.{item}: {e}')
    
    return len(errors) == 0, errors

def test_instantiation():
    """Test that key classes can be instantiated"""
    print("\n🔍 Testing instantiation...")
    errors = []
    
    try:
        from titan.science import HRVGuidedEngine, TSBEngine, ACWREngine
        hrv = HRVGuidedEngine()
        tsb = TSBEngine()
        print('  ✅ Science engines instantiate')
    except Exception as e:
        errors.append(f'Science engines: {e}')
        print(f'  ❌ Science engines: {e}')
    
    try:
        from titan.integrations.garmin_sync import GarminSync
        from titan.integrations.weather_api import WeatherAPI
        from titan.integrations.telegram_bot import TitanTelegramBot
        
        garmin = GarminSync()
        weather = WeatherAPI()
        telegram = TitanTelegramBot()
        print('  ✅ Integration classes instantiate')
    except Exception as e:
        errors.append(f'Integrations: {e}')
        print(f'  ❌ Integrations: {e}')
    
    return len(errors) == 0, errors

def test_basic_functionality():
    """Test basic functionality of key classes"""
    print("\n🔍 Testing functionality...")
    errors = []
    
    try:
        from titan.science.hrv_engine import HRVGuidedEngine
        hrv = HRVGuidedEngine()
        hrv.add_hrv_measurement('2026-02-16', 45.0)
        hrv.add_hrv_measurement('2026-02-17', 47.0)
        print('  ✅ HRV engine works')
    except Exception as e:
        errors.append(f'HRV: {e}')
        print(f'  ❌ HRV: {e}')
    
    try:
        from titan.science.tsb_engine import TSBEngine
        tsb = TSBEngine()
        tsb.add_daily_load('2026-02-16', 150.0)
        tsb.add_daily_load('2026-02-17', 160.0)
        ctl = tsb.calculate_ctl()
        print('  ✅ TSB engine works')
    except Exception as e:
        errors.append(f'TSB: {e}')
        print(f'  ❌ TSB: {e}')
    
    try:
        from titan.science.acwr_engine import ACWREngine
        acwr, status, rec = ACWREngine.calculate_acwr(800.0, 120.0)
        assert acwr is not None
        print('  ✅ ACWR engine works')
    except Exception as e:
        errors.append(f'ACWR: {e}')
        print(f'  ❌ ACWR: {e}')
    
    try:
        from titan.science.drift_engine import DriftEngine
        drift = DriftEngine.compute_drift(150, 157)
        assert drift > 0
        print('  ✅ Drift engine works')
    except Exception as e:
        errors.append(f'Drift: {e}')
        print(f'  ❌ Drift: {e}')
    
    try:
        from titan.science.biomechanics import BiomechanicsAnalysis
        score, status, issues = BiomechanicsAnalysis.analyze_form(175, 9.5, 250)
        assert score > 0
        print('  ✅ Biomechanics works')
    except Exception as e:
        errors.append(f'Biomechanics: {e}')
        print(f'  ❌ Biomechanics: {e}')
    
    return len(errors) == 0, errors

def test_threading():
    """Test that classes are thread-aware"""
    print("\n🔍 Testing threading awareness...")
    errors = []
    
    try:
        from titan.integrations.garmin_sync import GarminSync
        garmin = GarminSync()
        # Check thread attributes exist
        assert hasattr(garmin, '_sync_thread')
        assert hasattr(garmin, '_stop_sync')
        print('  ✅ Garmin thread-aware')
    except Exception as e:
        errors.append(f'Garmin threading: {e}')
        print(f'  ❌ Garmin threading: {e}')
    
    try:
        from titan.integrations.weather_api import WeatherAPI
        weather = WeatherAPI()
        assert hasattr(weather, '_update_thread')
        assert hasattr(weather, '_stop_update')
        print('  ✅ Weather thread-aware')
    except Exception as e:
        errors.append(f'Weather threading: {e}')
        print(f'  ❌ Weather threading: {e}')
    
    try:
        from titan.integrations.telegram_bot import TitanTelegramBot
        telegram = TitanTelegramBot()
        assert hasattr(telegram, '_scheduler_thread')
        assert hasattr(telegram, '_stop_bot')
        print('  ✅ Telegram thread-aware')
    except Exception as e:
        errors.append(f'Telegram threading: {e}')
        print(f'  ❌ Telegram threading: {e}')
    
    return len(errors) == 0, errors

def main():
    print("""
╔═══════════════════════════════════════════════════════════╗
║              TITAN v51 - SYSTEM CHECK                    ║
╚═══════════════════════════════════════════════════════════╝
""")
    
    all_passed = True
    
    # Test 1: Imports
    passed, errors = test_imports()
    if not passed:
        all_passed = False
        print(f"\n❌ Import test failed ({len(errors)} errors)")
    else:
        print("\n✅ All imports successful")
    
    # Test 2: Instantiation
    passed, errors = test_instantiation()
    if not passed:
        all_passed = False
        print(f"\n❌ Instantiation test failed ({len(errors)} errors)")
    else:
        print("\n✅ All classes instantiate")
    
    # Test 3: Functionality
    passed, errors = test_basic_functionality()
    if not passed:
        all_passed = False
        print(f"\n❌ Functionality test failed ({len(errors)} errors)")
    else:
        print("\n✅ All functionality works")
    
    # Test 4: Threading
    passed, errors = test_threading()
    if not passed:
        all_passed = False
        print(f"\n❌ Threading test failed ({len(errors)} errors)")
    else:
        print("\n✅ All threading works")
    
    # Final summary
    print("\n" + "="*60)
    if all_passed:
        print("🎉 ALL SYSTEMS OPERATIONAL")
        print("="*60)
        print("\n✅ TITAN v51 is ready for deployment!")
        return 0
    else:
        print("⚠️ SOME TESTS FAILED")
        print("="*60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
