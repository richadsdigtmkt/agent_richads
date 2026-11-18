"""Modelos de datos de una cuenta de Google Ads, independientes de la fuente (API o fixtures)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Campaign:
    id: str
    name: str
    status: str  # ENABLED, PAUSED
    channel: str  # SEARCH, SHOPPING, PERFORMANCE_MAX, DISPLAY, VIDEO, DEMAND_GEN...
    impressions: int = 0
    clicks: int = 0
    cost: float = 0.0
    conversions: float = 0.0
    conv_value: float = 0.0
    cost_7d: float | None = None
    conversions_7d: float | None = None
    start_date: date | None = None
    bidding_strategy: str | None = None
    budget_lost_is: float | None = None
    rank_lost_is: float | None = None
    eu_political: str | None = None

    @property
    def active(self) -> bool:
        return self.status == "ENABLED"

    @property
    def has_activity(self) -> bool:
        return self.impressions > 0 or self.cost > 0


@dataclass
class Keyword:
    campaign: str
    ad_group: str
    text: str
    match_type: str
    quality_score: int | None
    clicks: int = 0
    impressions: int = 0
    cost: float = 0.0
    conversions: float = 0.0


@dataclass
class SearchTerm:
    campaign: str
    term: str
    status: str  # ADDED, EXCLUDED, NONE, ADDED_EXCLUDED
    clicks: int = 0
    impressions: int = 0
    cost: float = 0.0
    conversions: float = 0.0


@dataclass
class ConversionAction:
    name: str
    status: str
    type: str
    category: str
    counting_type: str  # ONE_PER_CLICK, MANY_PER_CLICK
    primary: bool
    lookback_days: int | None = None


@dataclass
class Profile:
    """Lo que el cliente declara en el formulario de alta."""

    business_type: str = "desconocido"  # leads, ecommerce, mixto, desconocido
    avg_ticket: float | None = None
    margin_band: str | None = None  # <20, 20-40, >40
    real_results_month: float | None = None
    channel_works: str | None = None  # si, no, no_se
    brand_terms: list[str] = field(default_factory=list)


@dataclass
class AccountData:
    customer_id: str
    currency: str
    period_days: int
    today: date
    campaigns: list[Campaign]
    keywords: list[Keyword] = field(default_factory=list)
    search_terms: list[SearchTerm] = field(default_factory=list)
    conversion_actions: list[ConversionAction] | None = None  # None = no leído
    profile: Profile = field(default_factory=Profile)
    search_terms_capped: bool = False
    skipped_queries: list[str] = field(default_factory=list)

    @property
    def active_or_spending(self) -> list[Campaign]:
        """Campañas que importan para el diagnóstico: activas o con actividad en la ventana."""
        return [c for c in self.campaigns if c.active or c.has_activity]

    @property
    def total_cost(self) -> float:
        return sum(c.cost for c in self.campaigns)

    @property
    def total_conversions(self) -> float:
        return sum(c.conversions for c in self.campaigns)

    @property
    def total_value(self) -> float:
        return sum(c.conv_value for c in self.campaigns)
