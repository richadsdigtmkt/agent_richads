import json
from datetime import date
from pathlib import Path

import pytest

from app.ads.models import AccountData, Campaign, Keyword, Profile, SearchTerm

FIX = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> AccountData:
    raw = json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))
    return AccountData(
        customer_id="0000000000",
        currency=raw["currency"],
        period_days=raw["period_days"],
        today=date.fromisoformat(raw["today"]),
        campaigns=[Campaign(id=str(i), **c) for i, c in enumerate(raw["campaigns"])],
        keywords=[Keyword(**k) for k in raw.get("keywords", [])],
        search_terms=[SearchTerm(**t) for t in raw.get("search_terms", [])],
        conversion_actions=None,
        profile=Profile(**raw.get("profile", {})),
        search_terms_capped=raw.get("search_terms_capped", False),
    )


@pytest.fixture
def relanzada() -> AccountData:
    """Ecommerce de cuidado del coche, DE: dos campañas relanzadas hace una semana (anonimizada)."""
    return load_fixture("caso_relanzada")


@pytest.fixture
def proxy() -> AccountData:
    """Lead-gen multirregión con cierre offline y conversiones proxy en PMax (anonimizada)."""
    return load_fixture("caso_proxy_multiregion")
