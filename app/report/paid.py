"""Informe de pago: los hallazgos de las reglas más el criterio experto de Claude.

Pendiente: el prompt de criterio destilado (prompts/criterio.md) a partir del system prompt v3,
el checklist v4 y los principios, sin nombres de clientes. Mientras no exista, este módulo solo
prepara el material que recibirá Claude, para medir tamaño y coste por informe.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.ads.models import AccountData
from app.rules.engine import RuleResult

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "criterio.md"


def build_payload(data: AccountData, result: RuleResult) -> dict:
    """Material compacto para Claude: perfil, campañas con actividad y hallazgos de las reglas.

    Las campañas pausadas sin actividad no se envían: no cambian el informe y encarecen la llamada.
    """
    camps = [
        {
            "nombre": c.name, "estado": c.status, "canal": c.channel, "coste": round(c.cost, 2),
            "coste_7d": round(c.cost_7d, 2) if c.cost_7d is not None else None,
            "clics": c.clicks, "impresiones": c.impressions, "conversiones": round(c.conversions, 1),
            "valor": round(c.conv_value, 2), "puja": c.bidding_strategy,
            "inicio": c.start_date.isoformat() if c.start_date else None,
        }
        for c in data.active_or_spending
    ]
    return {
        "moneda": data.currency,
        "ventana_dias": data.period_days,
        "perfil": data.profile.__dict__,
        "campanas": camps,
        "campanas_pausadas_sin_actividad": len(data.campaigns) - len(camps),
        "hallazgos_reglas": [
            {"paso": f.step, "regla": f.rule, "gravedad": f.severity, "detalle": f.detail} for f in result.by_severity()
        ],
        "no_observado": [{"paso": n.step, "que": n.what, "por_que": n.why} for n in result.not_observed],
    }


def payload_size_chars(data: AccountData, result: RuleResult) -> int:
    return len(json.dumps(build_payload(data, result), ensure_ascii=False))


def generate(data: AccountData, result: RuleResult) -> str:
    if not PROMPT_PATH.exists():
        raise NotImplementedError("Falta prompts/criterio.md (destilado del conocimiento de Agent RichADs).")
    import anthropic

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=4000,
        system=PROMPT_PATH.read_text(encoding="utf-8"),
        messages=[{"role": "user", "content": json.dumps(build_payload(data, result), ensure_ascii=False)}],
    )
    return msg.content[0].text
