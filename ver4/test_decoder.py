import unittest
from unittest.mock import patch
import decoder
from visual import NACP_TO_HFOM

class TestADSBDecoder(unittest.TestCase):
    """Переработанные тесты для анализатора ADS-B (версия 2)"""

    # ========== TC1: Проверка извлечения NIC (только для TC9) ==========
    @patch('pyModeS.df', return_value=17)
    @patch('pyModeS.adsb.typecode', return_value=9)
    def test_tc1_get_nic_tc9(self, mock_tc, mock_df):
        """NIC для Type Code 9 должен быть 11 (по таблице из Приложения Б)"""
        dummy_msg = "8D4840D6202CC371C32CE0576098"
        nic_value = decoder.get_nic(dummy_msg, 9)
        self.assertEqual(nic_value, 11)

    # ========== TC2: Проверка конвертации NACp → HFOM ==========
    def test_tc2_hfom_conversion(self):
        """NACp=10 должно соответствовать HFOM=10.0 метров"""
        self.assertEqual(NACP_TO_HFOM.get(10), 10.0)

    def test_tc2_hfom_edge_cases(self):
        """Граничные значения NACp"""
        self.assertEqual(NACP_TO_HFOM.get(11), 3.0)
        self.assertEqual(NACP_TO_HFOM.get(0), 20000.0)

    # ========== TC3: Устойчивость к ошибкам ==========
    def test_tc3_fault_tolerance_corrupted_hex(self):
        """Строка с недопустимым символом (Z) должна игнорироваться → None"""
        corrupted_line = "1614838637.123 DF 8D4840Z6202CC371C32"
        result = decoder.parse_ads_b_line(corrupted_line)
        self.assertIsNone(result)

    def test_tc3_missing_hex(self):
        """Строка без HEX-данных (только timestamp) → None"""
        line = "1614838637.123"
        result = decoder.parse_ads_b_line(line)
        self.assertIsNone(result)

    # ========== TC4: Определение метки формата сообщения ==========
    def test_tc4_format_label_generation(self):
        # 1. Длинное сообщение DF17
        msg_long = "8D4840D6202CC371C32CE0576098"
        self.assertEqual(decoder.get_format_label(msg_long, 17), "DF17(L)")

        # 2. Короткое сообщение DF5
        msg_short = "2A001910CA4428"
        self.assertEqual(decoder.get_format_label(msg_short, 5), "DF5(S)")

        # 3. Резервный механизм (по длине строки)
        self.assertEqual(decoder.get_format_label(msg_long, 99), "DF99(L)")

    # ========== TC5: Универсальность парсинга строк ==========
    def test_tc5_universal_parsing_with_df(self):
        """Строка с явным полем 'DF'"""
        line = "1614838637.123 DF 8D4840D6202CC371C32CE0576098"
        result = decoder.parse_ads_b_line(line)
        self.assertIsNotNone(result)
        msg, hex_str = result
        self.assertEqual(hex_str, "8D4840D6202CC371C32CE0576098")
        self.assertEqual(msg.timestamp, 1614838637.123)

    def test_tc5_universal_parsing_without_df(self):
        """Строка без 'DF' (сразу HEX)"""
        line = "1614838637.123 8D4840D6202CC371C32CE0576098"
        result = decoder.parse_ads_b_line(line)
        self.assertIsNotNone(result)
        msg, hex_str = result
        self.assertEqual(hex_str, "8D4840D6202CC371C32CE0576098")
        self.assertEqual(msg.timestamp, 1614838637.123)

if __name__ == '__main__':
    unittest.main()