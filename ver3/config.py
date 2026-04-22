import numpy as np
from pathlib import Path

MAX_MESSAGE_LENGTH = 32
DATA_DIR = Path("data") # Папка, где лежат логи
DEFAULT_LOG_EXTENSION = ".t4433" # Расширение файлов логов

# словарь для преобразования режимов автопилота в понятные сокращения
MODE_MAP = {
    'U': 'AP',      # autopilot on
    '/': 'ALT',     # altitude hold
    'M': 'VNAV',    # vertical navigation
    'F': 'LNAV',    # lateral navigation
    'P': 'APP',     # approach mode
    'T': 'TCAS',    # tcas ra active
    'C': 'HDG'      # selected heading
}