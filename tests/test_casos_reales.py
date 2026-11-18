"""Las reglas tienen que llegar a los hallazgos del registro de pruebas (17/11/2026).

Si un cambio en las reglas rompe uno de estos tests, el producto ha dejado de ver algo que
un consultor vio en una cuenta real.
"""

from app.report.free import build_free_report, render_text
from app.report.paid import build_payload
from app.rules.engine import run_rules


def rules_hit(result):
    return {f.rule: f for f in result.findings}


# --- Cuenta relanzada ------------------------------------------------------------

def test_relanzada_detecta_campanas_nuevas_y_pide_esperar(relanzada):
    hit = rules_hit(run_rules(relanzada))
    assert "new_campaigns" in hit
    assert hit["new_campaigns"].severity == "media"  # más del 50 % del gasto
    assert hit["new_campaigns"].metrics["spend_share"] > 0.95


def test_relanzada_cpa_sin_senal(relanzada):
    hit = rules_hit(run_rules(relanzada))
    assert set(hit["low_signal"].metrics["campaigns"]) == {
        "Shopping | AllProducts | DE | ACME", "Search | Brand | DE | ACME"}


def test_relanzada_composicion_marca(relanzada):
    f = rules_hit(run_rules(relanzada))["brand_composition"]
    assert round(f.metrics["spend_share"], 3) == 0.114
    assert round(f.metrics["conv_share"], 3) == 0.667
    assert round(f.metrics["value_share"], 3) == 0.887


def test_relanzada_higiene_es_informativa(relanzada):
    hit = rules_hit(run_rules(relanzada))
    assert hit["paused_backlog"].severity == "info"
    assert "paused_with_spend" not in hit


def test_relanzada_terminos_no_observados(relanzada):
    r = run_rules(relanzada)
    assert "terms_uncurated" not in rules_hit(r)


# --- Lead-gen con proxy ---------------------------------------------------------------

def test_proxy_detectado(proxy):
    f = rules_hit(run_rules(proxy))["proxy_pmax"]
    assert f.severity == "alta"
    assert round(f.metrics["pmax_conv_share"], 3) == 0.835
    assert round(f.metrics["pmax_spend_share"], 3) == 0.223
    assert 15 < f.metrics["search_cpa"] / f.metrics["pmax_cpa"] < 20


def test_proxy_terminos_sin_curar(proxy):
    f = rules_hit(run_rules(proxy))["terms_uncurated"]
    top_terms = [t[0] for t in f.metrics["terms"]]
    assert "equipo médico cerca de mi" in top_terms
    assert "soluciones para personas con movilidad reducida" in top_terms


def test_proxy_qs_bajo_con_gasto(proxy):
    f = rules_hit(run_rules(proxy))["qs_low_spend"]
    assert f.metrics["keywords"][0][0] == "cama para postrados"


def test_proxy_valor_irregular(proxy):
    assert "value_irregular" in rules_hit(run_rules(proxy))


def test_proxy_pausada_a_mitad_de_ventana_y_zombie(proxy):
    hit = rules_hit(run_rules(proxy))
    assert hit["paused_with_spend"].metrics["campaigns"] == ["SN | Arriendo Oxigenación y Medición | 6a y 7a Región"]
    assert hit["zombie_campaigns"].metrics["campaigns"] == ["YT | Nuevo contenido"]


def test_proxy_campanas_nuevas_de_audicion(proxy):
    f = rules_hit(run_rules(proxy))["new_campaigns"]
    assert f.severity == "info"  # poco gasto sobre el total
    assert "SN | Audicion | Audifonos | Santiago (RM)" in f.metrics["campaigns"]


# --- Informe gratuito: sin cifras ni causas ----------------------------------------------------

def test_informe_gratuito_no_lleva_cifras(proxy, relanzada):
    for data in (proxy, relanzada):
        text = render_text(build_free_report(run_rules(data)))
        body = text.split("\n", 1)[1]  # la primera línea es la puntuación
        body = body.rsplit("(", 1)[0]  # la última línea cita el número de puntos
        assert not any(ch.isdigit() for ch in body), body


def test_payload_de_pago_excluye_pausadas_sin_actividad(proxy):
    p = build_payload(proxy, run_rules(proxy))
    assert p["campanas_pausadas_sin_actividad"] == 44
    assert all(not c["nombre"].startswith("Pausada") for c in p["campanas"])


def test_relanzada_frase_cara_en_marca(relanzada):
    f = rules_hit(run_rules(relanzada))["match_type_cost_gap"]
    assert "acme" in f.metrics["keywords"] and "acme autopflege" in f.metrics["keywords"]


def test_relanzada_no_puntua(relanzada):
    r = build_free_report(run_rules(relanzada))
    assert r.level == "Demasiado pronto para puntuar"
