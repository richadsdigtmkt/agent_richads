"""Motor de reglas: cálculos fijos sobre los datos de la cuenta, sin IA.

Cada regla devuelve cero o más Findings. Un Finding tiene dos capas:
- symptom: lo que ve el informe gratuito (síntoma y área, sin cifras ni causa).
- detail + metrics: lo que entra en el informe de pago (cifras, causa probable, qué hacer).
La numeración `step` es la del checklist v4 / system prompt v3, para poder citar el caso que la sostiene.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from app.ads.models import AccountData

SEVERITY_WEIGHT = {"alta": 15, "media": 7, "baja": 3, "info": 0}


@dataclass
class Finding:
    rule: str
    step: str
    area: str  # tracking, estructura, gasto, busqueda, calidad, datos, terreno
    severity: str  # alta, media, baja, info
    symptom: str
    detail: str
    metrics: dict = field(default_factory=dict)


@dataclass
class NotObserved:
    step: str
    what: str
    why: str


@dataclass
class RuleResult:
    findings: list[Finding]
    not_observed: list[NotObserved]

    @property
    def score(self) -> int:
        penalty = sum(SEVERITY_WEIGHT[f.severity] for f in self.findings)
        return max(0, 100 - penalty)

    def by_severity(self) -> list[Finding]:
        order = {"alta": 0, "media": 1, "baja": 2, "info": 3}
        return sorted(self.findings, key=lambda f: order[f.severity])


Rule = Callable[[AccountData], list[Finding]]
_RULES: list[Rule] = []


def rule(fn: Rule) -> Rule:
    _RULES.append(fn)
    return fn


def run_rules(data: AccountData) -> RuleResult:
    from app.rules import checks  # noqa: F401  (registra las reglas)

    findings: list[Finding] = []
    for fn in _RULES:
        findings.extend(fn(data))
    return RuleResult(findings=findings, not_observed=checks.not_observed(data))
