"""
ui/app.py
=========

Panel visual (Frontend/Interfaz) del proyecto JPxs-LightPanda-AI.

Construido con Streamlit. Permite:
  - Ingresar una o más URLs para extraer.
  - Elegir el proveedor y modelo de IA (OpenAI GPT-4o-mini o Anthropic Claude 3.5 Sonnet).
  - Llamar al Motor Core (FastAPI) mediante HTTP para extraer + analizar.
  - Visualizar el HTML/texto extraído, el reporte de IA y tablas de datos.
  - Exportar resultados a CSV.

Desacoplamiento:
  - Esta UI NO importa el código del Core. Se comunica únicamente por HTTP
    a través de la variable de entorno CORE_API_URL (definida en .env).
  - Así puede ejecutarse en OpenCloud mientras el Core corre localmente en WSL2,
    o viceversa, simplemente cambiando el .env.

Dependencias (requirements-ui.txt):
  - streamlit
  - requests
  - pandas
  - python-dotenv
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
from dotenv import load_dotenv
import streamlit as st

# --------------------------------------------------------------------------- #
# Carga de configuración desde .env
# --------------------------------------------------------------------------- #
load_dotenv()

CORE_API_URL = os.getenv("CORE_API_URL", "http://127.0.0.1:8000").rstrip("/")
DEFAULT_PROVIDER = os.getenv("DEFAULT_AI_PROVIDER", "openai")
DEFAULT_MODEL = os.getenv("DEFAULT_AI_MODEL", "gpt-4o-mini")

# --------------------------------------------------------------------------- #
# Configuración de la página Streamlit
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="JPxs-LightPanda-AI",
    page_icon="🐼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS personalizado para un aspecto más moderno y profesional
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 800;
        color: #1f77b4;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #6c757d;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 0.5rem;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    .stAlert {
        border-radius: 0.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Cliente HTTP hacia el Motor Core
# --------------------------------------------------------------------------- #


class CoreClient:
    """Cliente ligero para consumir los endpoints del Motor Core (FastAPI)."""

    def __init__(self, base_url: str, timeout: float = 120.0) -> None:
        self.base_url = base_url
        self.timeout = timeout

    def health(self) -> Dict[str, Any]:
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "detail": str(exc)}

    def pipeline(
        self,
        url: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> Dict[str, Any]:
        """Ejecuta el pipeline completo: extracción + análisis de IA."""
        payload: Dict[str, Any] = {
            "url": url,
            "provider": provider,
            "model": model,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        resp = requests.post(
            f"{self.base_url}/pipeline",
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def extract(self, url: str) -> Dict[str, Any]:
        """Solo extrae HTML/texto de una URL (sin IA)."""
        resp = requests.post(
            f"{self.base_url}/extract",
            json={"url": url},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def analyze(
        self,
        text: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> Dict[str, Any]:
        """Solo analiza texto con IA (sin extracción)."""
        payload: Dict[str, Any] = {
            "text": text,
            "provider": provider,
            "model": model,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        resp = requests.post(
            f"{self.base_url}/analyze",
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()


# --------------------------------------------------------------------------- #
# Estado de la sesión
# --------------------------------------------------------------------------- #
if "results" not in st.session_state:
    st.session_state.results: List[Dict[str, Any]] = []
if "last_error" not in st.session_state:
    st.session_state.last_error: Optional[str] = None

# --------------------------------------------------------------------------- #
# Cabecera
# --------------------------------------------------------------------------- #
st.markdown('<div class="main-header">🐼 JPxs-LightPanda-AI</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Extracción web con Lightpanda + Análisis IA para proyectos de tesis</div>',
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Barra lateral de configuración
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("⚙️ Configuración")

    # Endpoint del Motor Core
    core_url = st.text_input(
        "URL del Motor Core (FastAPI)",
        value=CORE_API_URL,
        help="Ej: http://127.0.0.1:8000 (local) o http://<IP-VPS>:8000 (OpenCloud)",
    )

    # Proveedor de IA
    provider = st.selectbox(
        "Proveedor de IA",
        options=["openai", "anthropic"],
        index=0 if DEFAULT_PROVIDER == "openai" else 1,
        help="openai → GPT-4o-mini (scraping masivo) | anthropic → Claude 3.5 Sonnet (análisis jurídico profundo)",
    )

    # Modelo según proveedor
    if provider == "openai":
        model_options = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]
        default_model = DEFAULT_MODEL if DEFAULT_PROVIDER == "openai" else "gpt-4o-mini"
    else:
        model_options = ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"]
        default_model = DEFAULT_MODEL if DEFAULT_PROVIDER == "anthropic" else "claude-3-5-sonnet-20241022"

    model = st.selectbox(
        "Modelo",
        options=model_options,
        index=model_options.index(default_model) if default_model in model_options else 0,
    )

    system_prompt = st.text_area(
        "Prompt de sistema (opcional)",
        value=(
            "Eres un asistente experto en análisis de datos para tesis académicas. "
            "Extrae la información relevante del contenido web, estructura los hallazgos, "
            "identifica citas jurídicas o datos técnicos, y presenta una conclusión clara."
        ),
        height=120,
    )

    temperature = st.slider(
        "Temperatura (creatividad)",
        min_value=0.0,
        max_value=1.0,
        value=0.3,
        step=0.1,
        help="Valores más bajos = respuestas más deterministas.",
    )
    max_tokens = st.number_input(
        "Máximo de tokens",
        min_value=256,
        max_value=8192,
        value=2000,
        step=256,
    )

    st.divider()

    # Estado del motor
    st.subheader("Estado del Motor")
    client = CoreClient(base_url=core_url)
    health = client.health()
    if health.get("status") == "ok":
        st.success("✅ Motor Core conectado")
    else:
        st.error(f"❌ Motor Core no disponible: {health.get('detail', 'desconocido')}")

    st.caption(f"Proveedor: {provider}  |  Modelo: {model}")

# --------------------------------------------------------------------------- #
# Área principal
# --------------------------------------------------------------------------- #
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("🔗 URL a analizar")
    url_input = st.text_input(
        "Ingresa la URL de la página web",
        placeholder="https://ejemplo.com/pagina-de-interes",
        help="Puede ser jurisprudencia, documentación de software o cualquier sitio público.",
    )

    run_pipeline = st.button(
        "▶️ Extraer y Analizar con IA",
        type="primary",
        use_container_width=True,
        disabled=not url_input.strip(),
    )

with col2:
    st.subheader("📋 Acciones rápidas")
    if st.button("🗑️ Limpiar resultados", use_container_width=True):
        st.session_state.results = []
        st.session_state.last_error = None
        st.rerun()

    if st.session_state.results:
        csv_data = pd.DataFrame(st.session_state.results).to_csv(index=False).encode("utf-8")
        st.download_button(
            "💾 Descargar resultados (CSV)",
            data=csv_data,
            file_name="jpxs_lightpanda_ai_resultados.csv",
            mime="text/csv",
            use_container_width=True,
        )

# --------------------------------------------------------------------------- #
# Ejecución del pipeline
# --------------------------------------------------------------------------- #
if run_pipeline and url_input.strip():
    with st.spinner("Conectando a Lightpanda y analizando con IA... esto puede tomar unos segundos."):
        try:
            result = client.pipeline(
                url=url_input.strip(),
                provider=provider,
                model=model,
                system_prompt=system_prompt or None,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            st.session_state.results.append(
                {
                    "url": url_input.strip(),
                    "provider": result.get("analysis", {}).get("provider", provider),
                    "model": result.get("analysis", {}).get("model", model),
                    "title": result.get("extraction", {}).get("title", ""),
                    "text": result.get("extraction", {}).get("text", ""),
                    "analysis": result.get("analysis", {}).get("content", ""),
                    "status": result.get("extraction", {}).get("status_code", 0),
                }
            )
            st.session_state.last_error = None
            st.success("✅ Extracción y análisis completados.")
        except Exception as exc:  # noqa: BLE001
            st.session_state.last_error = str(exc)
            st.error(f"❌ Error: {exc}")

if st.session_state.last_error:
    st.error(st.session_state.last_error)

# --------------------------------------------------------------------------- #
# Visualización de resultados
# --------------------------------------------------------------------------- #
if st.session_state.results:
    st.divider()
    st.subheader("📊 Resultados generados")

    for idx, res in enumerate(reversed(st.session_state.results)):
        real_idx = len(st.session_state.results) - 1 - idx
        with st.expander(
            f"Resultado {real_idx + 1}: {res.get('title') or res['url']}",
            expanded=(idx == 0),
        ):
            tabs = st.tabs(["🌐 Extracción", "🧠 Análisis IA", "📄 Datos brutos"])

            # Pestaña 1: Extracción
            with tabs[0]:
                st.markdown(f"**URL:** {res['url']}")
                st.markdown(f"**Estado HTTP:** {res.get('status', 'N/A')}")
                st.markdown("**Texto extraído (preview):**")
                st.text_area(
                    label="texto_extraido",
                    value=res.get("text", "")[:5000],
                    height=300,
                    label_visibility="collapsed",
                    key=f"texto_{real_idx}",
                )

            # Pestaña 2: Análisis IA
            with tabs[1]:
                st.markdown(f"**Proveedor:** {res.get('provider', 'N/A')}")
                st.markdown(f"**Modelo:** {res.get('model', 'N/A')}")
                st.markdown("**Reporte de IA:**")
                st.write(res.get("analysis", ""))

            # Pestaña 3: Datos brutos
            with tabs[2]:
                st.json(
                    {
                        "url": res["url"],
                        "title": res.get("title", ""),
                        "provider": res.get("provider", ""),
                        "model": res.get("model", ""),
                        "status_code": res.get("status", 0),
                        "texto_longitud": len(res.get("text", "")),
                        "analisis_longitud": len(res.get("analysis", "")),
                    }
                )

# --------------------------------------------------------------------------- #
# Pie de página
# --------------------------------------------------------------------------- #
st.divider()
st.markdown(
    "<div style='text-align: center; color: #888; font-size: 0.9rem;'>"
    "JPxs-LightPanda-AI  •  Motor: Lightpanda (CDP) + IA (OpenAI / Anthropic)  •  "
    "Arquitectura desacoplada para tesis y análisis de datos."
    "</div>",
    unsafe_allow_html=True,
)
