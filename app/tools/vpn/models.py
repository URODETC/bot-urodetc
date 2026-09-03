from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class VpnUser:
    id: int
    username: str
    status: str
    expire_at: datetime
    traffic_limit_bytes: int
    used_traffic_bytes: int
    lifetime_used_traffic_bytes: int
    subscription_url: str
    uuid: str | None = None
    telegram_id: int | None = None


@dataclass(frozen=True)
class CreateVpnUser:
    username: str
    expire_at: datetime
    traffic_limit_bytes: int = 0
    telegram_id: int | None = None
    description: str | None = None
    active_internal_squads: tuple[str, ...] = ()


@dataclass(frozen=True)
class VpnUserUsage:
    username: str
    total_bytes: int


@dataclass(frozen=True)
class VpnNodeLoad:
    name: str
    connected: bool
    users_online: int
    cpu_count: int | None
    load_average_1m: float | None
    memory_used_bytes: int | None
    memory_total_bytes: int | None
    rx_bytes_per_second: int | None
    tx_bytes_per_second: int | None


@dataclass(frozen=True)
class VpnSystemStats:
    total_users: int
    users_online: int
    nodes_online: int
    lifetime_traffic_bytes: int
    panel_memory_used_bytes: int
    panel_memory_total_bytes: int


@dataclass(frozen=True)
class VpnWeeklyReport:
    period_start: date
    period_end: date
    generated_at: datetime
    total_traffic_bytes: int
    user_usage: tuple[VpnUserUsage, ...]
    nodes: tuple[VpnNodeLoad, ...]
    system: VpnSystemStats

