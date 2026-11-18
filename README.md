# RichAds: diagnóstico de Google Ads

App web en la que una pyme conecta su cuenta de Google Ads con acceso de solo lectura y recibe un diagnóstico basado en el conocimiento de Agent RichADs. Gratis ve los síntomas; el informe de pago trae causas, cifras y plan de acción, revisado por Ricard antes de la entrega durante el lanzamiento.

Especificación: https://claude.ai/artifact/REAiMuY7Dv7JYUoK77qrZh

## Estado (18/11/2026)

| Parte | Estado |
| --- | --- |
| Conexión OAuth y cliente de la API (REST, UTF-8, solo lectura) | Hecho, sin probar en vivo: faltan las credenciales OAuth |
| Consultas GAQL | Escritas, pendientes de validar campo a campo contra la API |
| Motor de reglas (pasos 0, 0-bis, 1b, 2, 3, 4a-4c, 4e, 5, 8, 8f) | Hecho, 15 tests con dos cuentas reales anonimizadas |
| Informe gratuito (síntomas sin cifras ni causas) | Hecho |
| Informe de pago con Claude | Solo el material de entrada; falta el prompt destilado (`prompts/criterio.md`) |
| Cobro (Stripe), base de datos, despliegue (Cloud Run) | Pendiente |

## Estructura

```
app/ads/       cliente de la API, consultas GAQL, carga de datos y modelos
app/rules/     motor de reglas; cada regla cita el paso del checklist v4
app/report/    informe gratuito y material para el informe de pago
app/web/       web mínima (FastAPI): conectar, elegir cuenta, formulario de alta, informe
tests/         casos reales anonimizados del registro de pruebas
```

## Lo que necesita Ricard para la primera prueba en vivo

1. En Google Cloud, proyecto `teak-instrument-473721-s4` (el que ya tiene acceso Basic a la API de Google Ads): Google Auth Platform > Clients > Create client > tipo "Web application", con la URI de redirección `http://localhost:8000/auth/callback`.
2. Copiar `.env.example` a `.env` y pegar el client ID y el client secret. El `.env` no se sube al repositorio.
3. Mientras la app no esté verificada por Google, añadir en Audience como usuarios de prueba las cuentas de Google que vayan a conectar (máximo 100).

## Arrancar en local

```
pip install -r requirements.txt
uvicorn app.web.main:app --reload
pytest -q
```

## Regla de los tests

Los tests de `tests/test_casos_reales.py` reproducen hallazgos que un consultor vio en cuentas reales. Si un cambio en las reglas rompe uno, el producto ha dejado de ver algo. Los fixtures están anonimizados: sin IDs de cliente y con la marca sustituida por "Acme".
