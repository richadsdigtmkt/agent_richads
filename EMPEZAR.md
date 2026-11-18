# Primera prueba en vivo (Windows)

1. Copia en esta carpeta el archivo `client_secret_....json` que descargaste de Google Cloud. La app lo lee sola y no se sube nunca al repositorio.
2. Abre PowerShell en esta carpeta y ejecuta, una sola vez:

```
python -m pip install -r requirements.txt
```

3. Para arrancar la app:

```
python -m uvicorn app.web.main:app --port 8000
```

4. Abre http://localhost:8000 en Chrome, pulsa "Conectar Google Ads" y entra con la cuenta de la MCC.
   Google avisará de que la app no está verificada: "Configuración avanzada" y "Ir a RichAds (no seguro)".
5. Escribe el ID de la cuenta (por ejemplo la de Betten), rellena el formulario y pulsa "Ver diagnóstico gratuito".

Para pararla: Ctrl+C en PowerShell.
