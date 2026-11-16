# 🚀 Inicio Rápido — JPxs-LightPanda-AI (Motor Core)

Arquitectura:
```
Usuario → UI (Streamlit, :8501) → Core (FastAPI, :8000) → Lightpanda (CDP, :9222) → OpenCode (LLM gratis)
```

---

## 1. Instalar Lightpanda en Ubuntu / WSL2

Desde tu máquina Ubuntu (o WSL2), copia y pega:

```bash
chmod +x scripts/setup_lightpanda_ubuntu.sh
./scripts/setup_lightpanda_ubuntu.sh
```

Esto instalará Node.js, Lightpanda y lo dejará corriendo en:
```
http://127.0.0.1:9222   (CDP)
```

Verifica que responde:
```bash
curl http://127.0.0.1:9222/json/version
```

---

## 2. Configurar el Motor Core (FastAPI)

Desde el worktree `feature-panda-core`:

```bash
cd feature-panda-core

# Copia el archivo de entorno
cp .env.example .env

# Edita .env y pon tu API key de OpenCode real
# Abre el archivo y reemplaza:
#   OPENCODE_API_KEY=oc_sk_tu_clave_de_opencode_aqui
# por tu clave real: oc_sk_b141c826e7fa_b5_HGtEXcsKQhAYBwvD5qQoNqCIXzRoV
nano .env

# Instala dependencias de Python
pip install -r requirements-core.txt

# Arranca el servidor
python -m uvicorn core.main:app --host 0.0.0.0 --port 8000
```

O usa el script de arranque incluido:

```bash
chmod +x scripts/start_core.sh
./scripts/start_core.sh
```

---

## 3. Verificar que todo funciona

En otra terminal (o desde tu navegador):

```bash
# 1. Health check del Core
curl http://127.0.0.1:8000/health
# Respuesta esperada: {"status": "ok"}

# 2. Pipeline completo (extraer + analizar con OpenCode)
curl -X POST http://127.0.0.1:8000/pipeline \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://github.com/affaan-m/ecc",
    "prompt": "Eres un asistente experto en analisis de datos para tesis academicas. Extrae la informacion relevante del contenido web, estructura los hallazgos y presenta un reporte academico claro.",
    "provider": "open_code",
    "model": "nemotron-3.5-super-vl-2024-10-22",
    "temperature": 0.3,
    "max_tokens": 2000
  }'
```

Respuesta esperada (JSON con `extraction` y `analysis`):
```json
{
  "extraction": {
    "url": "https://github.com/affaan-m/ecc",
    "title": "...",
    "text": "...",
    "html": "...",
    "status_code": 200
  },
  "analysis": {
    "provider": "open_code",
    "model": "nemotron-3.5-super-vl-2024-10-22",
    "content": "... analisis generado por OpenCode ...",
    "usage": null
  }
}
```

---

## 4. Endpoints disponibles

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/health` | Estado del motor (`{"status": "ok"}`) |
| POST | `/extract` | Extrae título, texto y HTML de una URL (sin IA) |
| POST | `/analyze` | Analiza texto con OpenCode |
| POST | `/pipeline` | Extrae de URL + analiza con IA (ideal para tesis) |

---

## 5. Modelos gratuitos de OpenCode disponibles

- `nemotron-3.5-super-vl-2024-10-22` (por defecto)
- `beam-free`
- `deepseek-v4.1-flash-free`
- `nemotron-3.5-lightning-free`
- `glm-5.3-flash-free`
- `mimo-v2.6-flash-free`
- `crouton-alpha-free`
- `pulse-alpha-free`
- `flint-40b-free`
- `big-pickle`

Puedes cambiarlos en `.env` con `DEFAULT_AI_MODEL` o enviarlos en cada petición al endpoint `/pipeline`.

---

## 6. Comandos útiles

```bash
# Ver estado de Lightpanda (Ubuntu)
systemctl status lightpanda

# Ver logs de Lightpanda
tail -f ~/lightpanda/lightpanda.log

# Ver logs del Core
# (si lo iniciaste con uvicorn, los logs salen en la misma terminal)

# Detener todo
sudo systemctl stop lightpanda
# Y presiona Ctrl+C en la terminal de uvicorn
```
