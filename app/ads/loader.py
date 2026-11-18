"""Convierte filas de la API (JSON camelCase) en AccountData."""

from __future__ import annotations

from datetime import date

from app.ads import queries
from app.ads.client import AdsApiError, AdsClient
from app.ads.models import AccountData, Campaign, ConversionAction, Keyword, Profile, SearchTerm

MICROS = 1_000_000


def _get(row: dict, path: str, default=None):
    cur = row
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _date(v) -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def load_account(client: AdsClient, customer_id: str, profile: Profile | None = None) -> AccountData:
    today = date.today()
    cust = client.search(customer_id, queries.CUSTOMER)
    currency = _get(cust[0], "customer.currencyCode", "") if cust else ""

    base = client.search(customer_id, queries.CAMPAIGNS_BASE)
    campaigns: dict[str, Campaign] = {}
    for r in base:
        cid = str(_get(r, "campaign.id"))
        campaigns[cid] = Campaign(
            id=cid,
            name=_get(r, "campaign.name", ""),
            status=_get(r, "campaign.status", ""),
            channel=_get(r, "campaign.advertisingChannelType", ""),
        )

    skipped: list[str] = []
    for field, key, attr, kind in queries.CAMPAIGN_OPTIONAL_FIELDS:
        if attr == "start_date" and any(c.start_date for c in campaigns.values()):
            continue
        try:
            rows = client.search(customer_id, queries.CAMPAIGN_OPTIONAL.format(field=field))
        except AdsApiError:
            skipped.append(field)
            continue
        for r in rows:
            c = campaigns.get(str(_get(r, "campaign.id")))
            if c:
                v = _get(r, f"campaign.{key}")
                setattr(c, attr, _date(v) if kind == "date" else v)

    for r in client.search(customer_id, queries.CAMPAIGN_METRICS.format(window="LAST_30_DAYS")):
        c = campaigns.get(str(_get(r, "campaign.id")))
        if not c:
            continue
        c.impressions = int(_num(_get(r, "metrics.impressions")))
        c.clicks = int(_num(_get(r, "metrics.clicks")))
        c.cost = _num(_get(r, "metrics.costMicros")) / MICROS
        c.conversions = _num(_get(r, "metrics.conversions"))
        c.conv_value = _num(_get(r, "metrics.conversionsValue"))

    try:
        for r in client.search(customer_id, queries.IMPRESSION_SHARE.format(window="LAST_30_DAYS")):
            c = campaigns.get(str(_get(r, "campaign.id")))
            if c:
                bl = _get(r, "metrics.searchBudgetLostImpressionShare")
                rl = _get(r, "metrics.searchRankLostImpressionShare")
                c.budget_lost_is = _num(bl, None) if bl is not None else None
                c.rank_lost_is = _num(rl, None) if rl is not None else None
    except AdsApiError:
        skipped.append("impression_share")

    for c in campaigns.values():
        c.cost_7d = 0.0
        c.conversions_7d = 0.0
    for r in client.search(customer_id, queries.CAMPAIGN_METRICS.format(window="LAST_7_DAYS")):
        c = campaigns.get(str(_get(r, "campaign.id")))
        if c:
            c.cost_7d = _num(_get(r, "metrics.costMicros")) / MICROS
            c.conversions_7d = _num(_get(r, "metrics.conversions"))

    def _safe(query: str, name: str) -> list[dict]:
        try:
            return client.search(customer_id, query)
        except AdsApiError:
            skipped.append(name)
            return []

    keywords = [
        Keyword(
            campaign=_get(r, "campaign.name", ""),
            ad_group=_get(r, "adGroup.name", ""),
            text=_get(r, "adGroupCriterion.keyword.text", ""),
            match_type=_get(r, "adGroupCriterion.keyword.matchType", ""),
            quality_score=_get(r, "adGroupCriterion.qualityInfo.qualityScore"),
            clicks=int(_num(_get(r, "metrics.clicks"))),
            impressions=int(_num(_get(r, "metrics.impressions"))),
            cost=_num(_get(r, "metrics.costMicros")) / MICROS,
            conversions=_num(_get(r, "metrics.conversions")),
        )
        for r in _safe(queries.KEYWORDS.format(window="LAST_30_DAYS"), "keywords")
    ]

    terms_rows = _safe(queries.SEARCH_TERMS.format(window="LAST_30_DAYS"), "search_terms")
    terms = [
        SearchTerm(
            campaign=_get(r, "campaign.name", ""),
            term=_get(r, "searchTermView.searchTerm", ""),
            status=_get(r, "searchTermView.status", ""),
            clicks=int(_num(_get(r, "metrics.clicks"))),
            impressions=int(_num(_get(r, "metrics.impressions"))),
            cost=_num(_get(r, "metrics.costMicros")) / MICROS,
            conversions=_num(_get(r, "metrics.conversions")),
        )
        for r in terms_rows
    ]

    try:
        actions = [
            ConversionAction(
                name=_get(r, "conversionAction.name", ""),
                status=_get(r, "conversionAction.status", ""),
                type=_get(r, "conversionAction.type", ""),
                category=_get(r, "conversionAction.category", ""),
                counting_type=_get(r, "conversionAction.countingType", ""),
                primary=bool(_get(r, "conversionAction.primaryForGoal", False)),
                lookback_days=_get(r, "conversionAction.clickThroughLookbackWindowDays"),
            )
            for r in client.search(customer_id, queries.CONVERSION_ACTIONS)
        ]
    except AdsApiError:
        actions = None

    return AccountData(
        customer_id=customer_id.replace("-", ""),
        currency=currency,
        period_days=30,
        today=today,
        campaigns=list(campaigns.values()),
        keywords=keywords,
        search_terms=terms,
        conversion_actions=actions,
        profile=profile or Profile(),
        search_terms_capped=len(terms_rows) >= 2000,
        skipped_queries=skipped,
    )
