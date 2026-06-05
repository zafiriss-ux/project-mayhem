import pytest

from titan.science.biomechanics import BiomechanicsAnalysis


@pytest.mark.unit
def test_stride_length_returns_expected_value_for_valid_inputs():
    assert BiomechanicsAnalysis.stride_length(speed_m_s=4.0, cadence_spm=180) == 1.33


@pytest.mark.unit
def test_stride_length_returns_zero_when_cadence_is_zero():
    assert BiomechanicsAnalysis.stride_length(speed_m_s=4.0, cadence_spm=0) == 0.0


@pytest.mark.unit
def test_stride_length_returns_zero_when_cadence_is_negative():
    assert BiomechanicsAnalysis.stride_length(speed_m_s=4.0, cadence_spm=-180) == 0.0


@pytest.mark.unit
def test_stride_length_returns_zero_when_speed_is_zero():
    assert BiomechanicsAnalysis.stride_length(speed_m_s=0.0, cadence_spm=180) == 0.0


@pytest.mark.unit
def test_stride_length_returns_zero_when_speed_is_negative():
    assert BiomechanicsAnalysis.stride_length(speed_m_s=-4.0, cadence_spm=180) == 0.0


@pytest.mark.unit
def test_stride_length_returns_zero_when_speed_and_cadence_are_non_positive():
    assert BiomechanicsAnalysis.stride_length(speed_m_s=0.0, cadence_spm=-1) == 0.0
