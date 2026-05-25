import pyModeS as pms
from functools import lru_cache
from config import MODE_MAP

class ADSBMessage:
    __slots__ = ['timestamp']
    def __init__(self, timestamp):
        self.timestamp = timestamp

def parse_ads_b_line(line):
    parts = line.strip().split()
    if len(parts) < 2:
        return None
    
    try:
        timestamp = float(parts[0])
    except ValueError:
        return None
    
    if len(parts) >= 3 and parts[1].upper() in ('DF', 'UF'):
        hex_parts = parts[2:]
    else:
        hex_parts = parts[1:]
    
    message_str = ''.join(hex_parts).upper()
    if len(message_str) == 0 or not all(c in "0123456789ABCDEF" for c in message_str):
        return None
    
    msg = ADSBMessage(timestamp)
    return msg, message_str

# ---- КЭШИРУЕМЫЕ ФУНКЦИИ (обёртки над pyModeS) ----
@lru_cache(maxsize=16384)
def cached_icao(msg_str: str) -> str:
    return pms.icao(msg_str)

@lru_cache(maxsize=16384)
def cached_df(msg_str: str) -> int:
    return pms.df(msg_str)

@lru_cache(maxsize=16384)
def cached_typecode(msg_str: str) -> int:
    return pms.adsb.typecode(msg_str)

@lru_cache(maxsize=8192)
def cached_altitude_adsb(msg_str: str) -> int | None:
    try:
        return pms.adsb.altitude(msg_str)
    except (ValueError, IndexError, TypeError):
        return None

@lru_cache(maxsize=8192)
def cached_altcode(msg_str: str) -> int | None:
    try:
        return pms.common.altcode(msg_str)
    except (ValueError, IndexError, TypeError):
        return None

@lru_cache(maxsize=4096)
def cached_idcode(msg_str: str) -> str | None:
    try:
        return pms.common.idcode(msg_str)
    except (ValueError, IndexError, TypeError):
        return None

@lru_cache(maxsize=2048)
def cached_velocity(msg_str: str):
    try:
        return pms.adsb.velocity(msg_str)
    except (ValueError, IndexError, TypeError):
        return None

@lru_cache(maxsize=2048)
def cached_selected_altitude(msg_str: str):
    try:
        return pms.adsb.selected_altitude(msg_str)
    except (ValueError, IndexError, TypeError):
        return None

@lru_cache(maxsize=2048)
def cached_altitude_diff(msg_str: str):
    try:
        return pms.adsb.altitude_diff(msg_str)
    except (ValueError, IndexError, TypeError):
        return None

@lru_cache(maxsize=2048)
def cached_baro_pressure(msg_str: str):
    try:
        return pms.adsb.baro_pressure_setting(msg_str)
    except (ValueError, IndexError, TypeError):
        return None

@lru_cache(maxsize=4096)
def cached_callsign(msg_str: str):
    try:
        return pms.adsb.callsign(msg_str)
    except (ValueError, IndexError, TypeError):
        return None

@lru_cache(maxsize=8192)
def cached_oe_flag(msg_str: str) -> int:
    try:
        return pms.adsb.oe_flag(msg_str)
    except (ValueError, IndexError, TypeError):
        return 0

@lru_cache(maxsize=2048)
def cached_nic_baro(msg_str: str):
    try:
        return pms.adsb.nic_baro(msg_str)
    except (ValueError, IndexError, TypeError):
        return None

# ---- ОСНОВНЫЕ ФУНКЦИИ (используют кэшированные версии) ----
def get_altitude_any_df(msg_str, df):
    try:
        if df in (17, 18):
            tc = cached_typecode(msg_str)
            if 9 <= tc <= 18:
                return cached_altitude_adsb(msg_str)
        elif df in (0, 4, 16, 20):
            return cached_altcode(msg_str)
    except (ValueError, IndexError, TypeError):
        pass
    return None

def get_squawk(msg_str, df):
    try:
        if df in (5, 21):
            return cached_idcode(msg_str)
    except (ValueError, IndexError, TypeError):
        pass
    return None

def get_velocity_and_course(msg_str, tc):
    if tc != 19:
        return None, None
    res = cached_velocity(msg_str)
    if res:
        spd, trk, _, _ = res
        return spd, trk
    return None, None

def get_selected_altitude(msg_str, tc):
    if tc != 29:
        return None
    res = cached_selected_altitude(msg_str)
    if res:
        sel_alt, raw_modes = res
        if sel_alt is not None and -2000 <= sel_alt <= 50000:
            processed_modes = {MODE_MAP.get(m, m) for m in raw_modes}
            return sel_alt, processed_modes
    return None

def get_altitude_difference(msg_str, tc):
    if tc != 19:
        return None
    alt_diff = cached_altitude_diff(msg_str)
    if alt_diff is not None and -2500 <= alt_diff <= 2500:
        return alt_diff
    return None

def get_baro_correction(msg_str, tc):
    if tc != 29:
        return None
    baro = cached_baro_pressure(msg_str)
    if baro is not None and 800 <= baro <= 1100:
        return baro
    return None

def get_callsign(msg_str, tc):
    if not (1 <= tc <= 4):
        return None
    cs = cached_callsign(msg_str)
    if cs:
        return ''.join(c for c in cs if c.isalnum())
    return None

def get_nic(msg_str, tc):
    try:
        if 9 <= tc <= 18:
            nic_b = (int(msg_str[9], 16) & 1) if len(msg_str) > 9 else 0
            mapping = {
                9: 11, 10: 10,
                11: 9 if nic_b else 8,
                12: 7, 13: 6, 14: 5, 15: 4,
                16: 3 if nic_b else 2,
                17: 1, 18: 0
            }
            return mapping.get(tc)
        if 5 <= tc <= 8:
            mapping = {5: 11, 6: 10, 7: 9, 8: 8}
            return mapping.get(tc)
    except (ValueError, IndexError, TypeError):
        pass
    return None

def get_operational_status_params(msg_str, tc):
    if tc != 31:
        return None, None, None
    try:
        msg_int = int(msg_str, 16)
        me_field = (msg_int >> 24) & 0xFFFFFFFFFFFFFF
        nac_p = (me_field >> 8) & 0xF
        gva = (me_field >> 6) & 0x3
        sil = (me_field >> 4) & 0x3
        return nac_p, gva, sil
    except (ValueError, IndexError, TypeError):
        pass
    return None, None, None

def get_nac_v(msg_str, tc):
    if tc != 19:
        return None
    try:
        msg_int = int(msg_str, 16)
        me_field = (msg_int >> 24) & 0xFFFFFFFFFFFFFF
        return (me_field >> 43) & 0x7
    except (ValueError, IndexError, TypeError):
        pass
    return None

def get_nic_baro(msg_str, tc):
    if tc != 31:
        return None
    return cached_nic_baro(msg_str)

def get_format_label(msg_str, df):
    if df in (0, 4, 5, 11):
        return f"DF{df}(S)"
    if df in (16, 17, 18, 19, 20, 21, 24):
        return f"DF{df}(L)"
    length = len(msg_str)
    return f"DF{df}(S)" if length == 14 else f"DF{df}(L)" if length == 28 else f"DF{df}(?)"