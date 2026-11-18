"""Informe gratuito: puntuación y síntomas por área, sin cifras ni causas.

Regla de negocio: antes del encargo se describen síntomas y alcance, nunca la cadena causal ni las cifras.
Por eso aquí solo se usa Finding.symptom; detail y metrics quedan para el informe de pago.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.rules.engine import RuleResult

AREA_LABEL = {
    "tracking": "Medición de conversiones",
    "gasto": "Reparto del presupuesto",
    "busqueda": "Búsquedas que activan los anuncios",
    "calidad": "Calidad de anuncios y palabras clave",
    "estructura": "Estructura de la cuenta",
    "datos": "Datos disponibles",
    "terreno": "Configuración general",
}
AREA_ORDER = ["tracking", "gasto", "busqueda", "calidad", "estructura", "datos", "terreno"]
SEVERITY_LABEL = {"alta": "Importante", "media": "A revisar", "baja": "Menor"}


@dataclass
class FreeReport:
    score: int
    level: str
    areas: list[tuple[str, list[tuple[str, str]]]]  # (área, [(etiqueta de gravedad, síntoma)])
    not_observed: list[str]
    paid_findings: int


def build_free_report(result: RuleResult) -> FreeReport:
    visible = [f for f in result.by_severity() if f.severity != "info"]
    areas = []
    for area in AREA_ORDER:
        items = [(SEVERITY_LABEL[f.severity], f.symptom) for f in visible if f.area == area]
        if items:
            areas.append((AREA_LABEL[area], items))
    score = result.score
    level = "Buena" if score >= 80 else "Mejorable" if score >= 55 else "Con problemas importantes"
    new = next((f for f in result.findings if f.rule == "new_campaigns"), None)
    if new and new.metrics.get("spend_share", 0) >= 0.5:
        # La mayor parte del gasto lleva pocos días: una puntuación alta engañaría.
        level = "Demasiado pronto para puntuar"
    return FreeReport(
        score=score,
        level=level,
        areas=areas,
        not_observed=[n.what for n in result.not_observed],
        paid_findings=len(visible),
    )


def render_text(r: FreeReport) -> str:
    head = (f"Puntuación de la cuenta: {r.score}/100 ({r.level})" if r.level != "Demasiado pronto para puntuar"
            else f"Puntuación de la cuenta: {r.level}")
    lines = [head, ""]
    for area, items in r.areas:
        lines.append(area)
        for sev, symptom in items:
            lines.append(f"  [{sev}] {symptom}")
        lines.append("")
    if r.not_observed:
        lines.append("No revisado en este análisis: " + "; ".join(r.not_observed) + ".")
    lines.append(
        f"El informe completo explica la causa de cada punto, con cifras y un plan de acción priorizado "
        f"({r.paid_findings} puntos)."
    )
    return "\n".join(lines)
