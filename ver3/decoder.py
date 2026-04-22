import pyModeS as pms
from config import MODE_MAP

class ADSBMessage:
    __slots__ = ['timestamp'] # Оптимизация памяти для объектов
    def __init__(self, timestamp):
        self.timestamp = timestamp

def parse_ads_b_line(line):
    parts = line.strip().split()
    if len(parts) < 2: return None
    
    try:
        # Используем обычный float, он быстрее np.float64
        timestamp = float(parts[0])
    except ValueError:
        return None
    
    if len(parts) >= 3 and parts[1].upper() in ['DF', 'UF']:
        hex_parts = parts[2:]
    else:
        hex_parts = parts[1:]
    
    message_spaced = ' '.join(hex_parts).upper().strip()
    message_str = message_spaced.replace(" ", "")
    
    if len(message_str) == 0 or not all(c in "0123456789ABCDEF" for c in message_str):
        return None
    
    msg = ADSBMessage(timestamp)
    # Больше никакого парсинга в numpy-массивы!
    return msg, message_spaced, message_str

def get_altitude_any_df(msg_str, df):
    try:
        if df in [17, 18]:
            tc = pms.adsb.typecode(msg_str)
            if 9 <= tc <= 18: return pms.adsb.altitude(msg_str)
        elif df in [0, 4, 16, 20]:
            return pms.common.altcode(msg_str)
    except: pass
    return None

def get_squawk(msg_str, df):
    try:
        if df in [5, 21]: return pms.common.idcode(msg_str)
    except: pass
    return None

# Объединенная функция для скорости и курса (вызывает pyModeS 1 раз)
def get_velocity_and_course(msg_str, tc):
    if tc != 19: return None, None
    try:
        res = pms.adsb.velocity(msg_str)
        if res:
            spd, trk, _, _ = res
            return spd, trk
    except: pass
    return None, None

def get_selected_altitude(msg_str, tc):
    if tc != 29: return None
    try:
        sel_alt_info = pms.adsb.selected_altitude(msg_str)
        if sel_alt_info:
            selected_alt, raw_modes = sel_alt_info
            if selected_alt is not None and -2000 <= selected_alt <= 50000:
                processed_modes = {MODE_MAP.get(m, m) for m in raw_modes}
                return selected_alt, processed_modes
    except: pass
    return None

def get_altitude_difference(msg_str, tc):
    if tc != 19: return None
    try:
        altitude_diff = pms.adsb.altitude_diff(msg_str)
        if altitude_diff is not None and -2500 <= altitude_diff <= 2500:
            return altitude_diff
    except: pass
    return None

def get_baro_correction(msg_str, tc):
    if tc != 29: return None
    try:
        baro_setting = pms.adsb.baro_pressure_setting(msg_str)
        if baro_setting is not None and 800 <= baro_setting <= 1100:
            return baro_setting
    except: pass
    return None

def get_callsign(msg_str, tc):
    if not (1 <= tc <= 4): return None
    try:
        callsign = pms.adsb.callsign(msg_str)
        if callsign: return ''.join(c for c in callsign if c.isalnum())
    except: pass
    return None

def get_nic(msg_str, tc):
    try:
        if 9 <= tc <= 18:
            nic_b = int(msg_str[9], 16) & 1
            if tc == 9: return 11
            if tc == 10: return 10
            if tc == 11: return 9 if nic_b else 8
            if tc == 12: return 7
            if tc == 13: return 6
            if tc == 14: return 5
            if tc == 15: return 4
            if tc == 16: return 3 if nic_b else 2
            if tc == 17: return 1
            if tc == 18: return 0
        if 5 <= tc <= 8:
            mapping = {5: 11, 6: 10, 7: 9, 8: 8}
            return mapping.get(tc)
    except: pass
    return None

def get_operational_status_params(msg_str, tc):
    if tc != 31: return None, None, None
    try:
        msg_int = int(msg_str, 16)
        me_field = (msg_int >> 24) & 0xFFFFFFFFFFFFFF 
        nac_p = (me_field >> 8) & 0xF 
        gva = (me_field >> 6) & 0x3
        sil = (me_field >> 4) & 0x3
        return nac_p, gva, sil
    except: pass
    return None, None, None

def get_nac_v(msg_str, tc):
    if tc != 19: return None
    try:
        msg_int = int(msg_str, 16)
        me_field = (msg_int >> 24) & 0xFFFFFFFFFFFFFF
        return (me_field >> 43) & 0x7 
    except: pass
    return None

def get_nic_baro(msg_str, tc):
    if tc != 31: return None
    try: return pms.adsb.nic_baro(msg_str)
    except: pass
    return None

def get_format_label(msg_str, df):
    # Упрощенная и быстрая проверка
    if df in (0, 4, 5, 11): return f"DF{df}(S)"
    if df in (16, 17, 18, 19, 20, 21, 24): return f"DF{df}(L)"
    return f"DF{df}(S)" if len(msg_str) == 14 else f"DF{df}(L)" if len(msg_str) == 28 else f"DF{df}(?)"