"""Consultas GAQL que alimentan el diagnóstico.

Pendiente de validar campo a campo contra la API en vivo (la versión se fija en config).
Si un campo cambia de nombre entre versiones, se corrige aquí y en loader.py.
"""

# Todas las campañas no eliminadas, sin métricas: sirve para la higiene (activas vs pausadas).
CAMPAIGNS_BASE = """
SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type
FROM campaign
WHERE campaign.status != 'REMOVED'
"""

# Métricas por campaña en una ventana. Las filas sin actividad no vuelven, que es lo que queremos.
CAMPAIGN_METRICS = """
SELECT campaign.id, metrics.impressions, metrics.clicks, metrics.cost_micros,
       metrics.conversions, metrics.conversions_value
FROM campaign
WHERE segments.date DURING {window} AND campaign.status != 'REMOVED'
"""

KEYWORDS = """
SELECT campaign.name, ad_group.name, ad_group_criterion.keyword.text,
       ad_group_criterion.keyword.match_type, ad_group_criterion.quality_info.quality_score,
       metrics.clicks, metrics.impressions, metrics.cost_micros, metrics.conversions
FROM keyword_view
WHERE segments.date DURING {window} AND metrics.impressions > 0
"""

SEARCH_TERMS = """
SELECT campaign.name, search_term_view.search_term, search_term_view.status,
       metrics.clicks, metrics.impressions, metrics.cost_micros, metrics.conversions
FROM search_term_view
WHERE segments.date DURING {window} AND metrics.clicks > 0
ORDER BY metrics.cost_micros DESC
LIMIT 2000
"""

CONVERSION_ACTIONS = """
SELECT conversion_action.name, conversion_action.status, conversion_action.type,
       conversion_action.category, conversion_action.counting_type,
       conversion_action.primary_for_goal, conversion_action.click_through_lookback_window_days
FROM conversion_action
WHERE conversion_action.status != 'REMOVED'
"""

CUSTOMER = """
SELECT customer.id, customer.descriptive_name, customer.currency_code
FROM customer
LIMIT 1
"""

# Campos opcionales de campaña: cada uno se pide aparte para que un nombre cambiado entre versiones
# de la API no tumbe el informe. (campo GAQL, clave JSON, atributo de Campaign, tipo)
CAMPAIGN_OPTIONAL_FIELDS = [
    ("campaign.start_date_time", "startDateTime", "start_date", "date"),
    ("campaign.start_date", "startDate", "start_date", "date"),
    ("campaign.bidding_strategy_type", "biddingStrategyType", "bidding_strategy", "str"),
    ("campaign.contains_eu_political_advertising", "containsEuPoliticalAdvertising", "eu_political", "str"),
]
CAMPAIGN_OPTIONAL = """
SELECT campaign.id, {field}
FROM campaign
WHERE campaign.status != 'REMOVED'
"""

IMPRESSION_SHARE = """
SELECT campaign.id, metrics.search_budget_lost_impression_share, metrics.search_rank_lost_impression_share
FROM campaign
WHERE segments.date DURING {window} AND campaign.advertising_channel_type = 'SEARCH'
"""
