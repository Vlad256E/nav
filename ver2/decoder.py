import numpy as np
import pyModeS as pms
from config import MAX_MESSAGE_LENGTH, MODE_MAP

# класс-контейнер для одного ads-b сообщения
class ADSBMessage:
    def __init__(self):
        self.timestamp = np.float64(0.0)
        self.message = np.zeros(MAX_MESSAGE_LENGTH, dtype=np.uint8)
        self.message_length = 0

# функция парсит одну строку из файла с данными
def parse_ads_b_line(line):
    # делим строку на части по пробелам
    parts = line.strip().split()
    if len(parts) < 2:
        return None
    try:
        # первую часть превращаем в число (время)
        timestamp = np.float64(parts[0])
    except ValueError:
        return None
    
    # проверка формата: если есть колонка DF/UF, смещаем чтение hex
    if len(parts) >= 3 and parts[1].upper() in ['DF', 'UF']:
        hex_parts = parts[2:]
    else:
        hex_parts = parts[1:]
    
    # остальные части соединяем в сплошную hex-строку
    message_spaced = ' '.join(hex_parts).upper().strip()
    message_str = message_spaced.replace(" ", "")
    
    if len(message_str) == 0 or not all(c in "0123456789ABCDEF" for c in message_str):
        return None
    
    # создаём объект-контейнер и заполняем его байтами
    msg = ADSBMessage()
    msg.timestamp = timestamp
    try:
        bytes_list = [int(message_str[i:i + 2], 16) for i in range(0, len(message_str), 2)]
        msg.message_length = min(len(bytes_list), MAX_MESSAGE_LENGTH)
        for i in range(msg.message_length):
            msg.message[i] = np.uint8(bytes_list[i])
    except:
        return None
        
    return msg, message_spaced, message_str

# универсальная функция извлечения высоты 
def get_altitude_any_df(msg_str, df):
    try:
        # если это ADS-B (DF17/18)
        if df in [17, 18]:
            tc = pms.adsb.typecode(msg_str)
            if 9 <= tc <= 18:
                return pms.adsb.altitude(msg_str)
        # если это Mode S ELS (DF0, 4, 16, 20)
        elif df in [0, 4, 16, 20]:
            return pms.common.altcode(msg_str)
    except:
        return None
    return None

# получение Squawk (кода ответчика)
def get_squawk(msg_str, df):
    try:
        # работает для DF5 и DF21
        if df in [5, 21]:
            return pms.common.idcode(msg_str)
    except:
        return None
    return None

# функция извлекает скорость из сообщения
def get_velocity(msg_str):
    try:
        # проверяем, что это ads-b сообщение
        df = pms.df(msg_str)
        if df not in [17, 18]: return None
        # проверяем, что это сообщение о скорости (тип 19)
        tc = pms.adsb.typecode(msg_str)
        if tc == 19:
            result = pms.adsb.velocity(msg_str)
            if result and result[0] is not None:
                return result[0]
        return None
    except:
        return None

# функция извлекает курс из сообщения
def get_course(msg_str):
    try:
        # проверяем, что это ads-b сообщение
        df = pms.df(msg_str)
        if df not in [17, 18]: return None
        # также проверяем, что это сообщение о скорости (тип 19)
        tc = pms.adsb.typecode(msg_str)
        if tc == 19:
            _, heading, _, _ = pms.adsb.velocity(msg_str)
            return heading
        return None
    except:
        return None

# функция извлекает выбранную на автопилоте высоту и режимы
def get_selected_altitude(msg_str):
    try:
        # проверяем, что это ads-b сообщение
        df = pms.df(msg_str)
        if df not in [17, 18]: return None
        # проверяем, что это сообщение о статусе (тип 29)
        tc = pms.adsb.typecode(msg_str)
        if tc != 29: return None
        sel_alt_info = pms.adsb.selected_altitude(msg_str)
        if sel_alt_info is None: return None
        selected_alt, raw_modes = sel_alt_info
        if selected_alt is not None and -2000 <= selected_alt <= 50000:
            # переводим режимы в понятные сокращения
            processed_modes = {MODE_MAP.get(m, m) for m in raw_modes}
            return selected_alt, processed_modes
        return None
    except Exception as e:
        return None

# функция получения разности высот
def get_altitude_difference(msg_str):
    try:
        # проверяем, что это ads-b сообщение
        df = pms.df(msg_str)
        if df not in [17, 18]: return None
        # проверяем, что это сообщение о скорости (тип 19)
        tc = pms.typecode(msg_str)
        if tc != 19:
            return None
        
        altitude_diff = pms.adsb.altitude_diff(msg_str)
        if altitude_diff is not None and -2500 <= altitude_diff <= 2500:
            return altitude_diff
        
        return None
    except Exception as e:
        return None

# функция получения барокоррекции
def get_baro_correction(msg_str):
    try:
        # проверяем, что это ads-b сообщение
        df = pms.df(msg_str)
        if df not in [17, 18]: return None
        # проверяем, что это сообщение о статусе (тип 29)
        tc = pms.adsb.typecode(msg_str)
        if tc != 29:
            return None
        
        baro_setting = pms.adsb.baro_pressure_setting(msg_str)
        
        if baro_setting is not None:
            # разумные пределы для атмосферного давления
            if 800 <= baro_setting <= 1100:
                return baro_setting
                
        return None
        
    except Exception as e:
        return None

# функция извлекает позывной (callsign)
def get_callsign(msg_str):
    try:
        # проверяем, что это ads-b сообщение
        df = pms.df(msg_str)
        if df not in [17, 18]: return None
        # проверяем, что это сообщение идентификации (тип 1-4)
        tc = pms.adsb.typecode(msg_str)
        if 1 <= tc <= 4:
            callsign = pms.adsb.callsign(msg_str)
            if not callsign: return None
            # очищаем позывной от лишних символов
            return ''.join(c for c in callsign if c.isalnum())
        return None
    except:
        return None

# вспомогательная функция для генерации метки формата сообщения
def get_format_label(msg_str, df):
    
    if df in [0, 4, 5, 11]:
        length_type = "S"
    elif df in [16, 17, 18, 19, 20, 21, 24]:
        length_type = "L"
    else:
        # если что-то не так, то пробуем сделать вывод по длине строки
        length_bits = len(msg_str) * 4
        if length_bits == 56:
            length_type = "S"
        elif length_bits == 112:
            length_type = "L"
        else:
            length_type = "?"
    
    label = f"DF{df}"
    return f"{label}({length_type})"