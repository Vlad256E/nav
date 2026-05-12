import pytest
from unittest.mock import patch

# Импортируем ваши модули, которые будем тестировать
import decoder
from visual import NACP_TO_HFOM

# ==========================================
# ТЕСТ-КЕЙС 1: Проверка извлечения NIC
# ==========================================
@patch('pyModeS.df', return_value=17)
@patch('pyModeS.adsb.typecode', return_value=9)
def test_tc1_get_nic_tc9(mock_tc, mock_df):
    """
    Проверка корректности извлечения значения NIC = 11 при Type Code = 9.
    """
    dummy_msg = "8D4840D6202CC371C32CE0576098"
    nic_value = decoder.get_nic(dummy_msg)
    
    assert nic_value == 11, f"Ожидался NIC=11, получено {nic_value}"

# ==========================================
# ТЕСТ-КЕЙС 2: Проверка конвертации NACp -> HFOM
# ==========================================
def test_tc2_hfom_conversion():
    """
    Проверка конвертации кодового значения NACp в метры (HFOM).
    """
    nacp_value = 10
    hfom_result = NACP_TO_HFOM.get(nacp_value, 20000.0) 
    
    assert hfom_result == 10.0, f"Ожидалось HFOM=10.0, получено {hfom_result}"

# ==========================================
# ТЕСТ-КЕЙС 3: Устойчивость к ошибкам (битые HEX)
# ==========================================
def test_tc3_fault_tolerance_corrupted_hex():
    """
    Проверка игнорирования поврежденных HEX-строк.
    """
    corrupted_line = "1614838637.123 DF 8D4840Z6202CC371C32"
    result = decoder.parse_ads_b_line(corrupted_line)
    
    assert result is None, "Функция должна вернуть None при обработке битого HEX"

# ==========================================
# ТЕСТ-КЕЙС 5: Универсальность парсинга строк
# ==========================================
def test_tc5_universal_parsing():
    """
    Проверка обработки строк с разделителем DF/UF и без него.
    """
    line_with_df = "1614838637.123 DF 8D4840D6202CC371C32CE0576098"
    line_without_df = "1614838637.123 8D4840D6202CC371C32CE0576098"
    
    result1 = decoder.parse_ads_b_line(line_with_df)
    result2 = decoder.parse_ads_b_line(line_without_df)
    
    assert result1 is not None, "Не удалось распарсить строку с DF"
    assert result2 is not None, "Не удалось распарсить строку без DF"
    
    assert result1[2] == "8D4840D6202CC371C32CE0576098"
    assert result2[2] == "8D4840D6202CC371C32CE0576098"