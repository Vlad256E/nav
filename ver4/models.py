from dataclasses import dataclass, field
from collections import defaultdict
from typing import Dict, List, Set, Any

@dataclass
class FlightData:
    """Хранит все данные, полученные в результате парсинга лог-файла."""
    icao_times: Dict[str, Dict[str, float]] = field(default_factory=dict)
    icao_altitude: Dict[str, List[tuple]] = field(default_factory=lambda: defaultdict(list))
    icao_gnss_altitude: Dict[str, List[tuple]] = field(default_factory=lambda: defaultdict(list))
    icao_speed: Dict[str, List[tuple]] = field(default_factory=lambda: defaultdict(list))
    icao_callsigns: Dict[str, str] = field(default_factory=dict)
    icao_selected_altitude: Dict[str, List[tuple]] = field(default_factory=lambda: defaultdict(list))
    icao_altitude_difference: Dict[str, List[tuple]] = field(default_factory=lambda: defaultdict(list))
    icao_baro_correction: Dict[str, List[tuple]] = field(default_factory=lambda: defaultdict(list))
    icao_has_selected_alt: Dict[str, bool] = field(default_factory=dict)
    adsb_icao_list: Set[str] = field(default_factory=set)
    icao_positions: Dict[str, List[tuple]] = field(default_factory=lambda: defaultdict(list))
    icao_courses: Dict[str, List[tuple]] = field(default_factory=lambda: defaultdict(list))
    icao_dfs: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    icao_nic: Dict[str, List[tuple]] = field(default_factory=lambda: defaultdict(list))
    icao_nacp: Dict[str, List[tuple]] = field(default_factory=lambda: defaultdict(list))
    icao_gva: Dict[str, List[tuple]] = field(default_factory=lambda: defaultdict(list))
    icao_sil: Dict[str, List[tuple]] = field(default_factory=lambda: defaultdict(list))
    icao_nacv: Dict[str, List[tuple]] = field(default_factory=lambda: defaultdict(list))
    icao_nic_baro: Dict[str, Any] = field(default_factory=dict)