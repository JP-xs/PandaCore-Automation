"""
core/__init__.py
================

Paquete del núcleo técnico (Core) del proyecto JPxs-LightPanda-AI.

Este motor es agnóstico a la interfaz: solo se encarga de hablar con Lightpanda
(Chrome DevTools Protocol) y con las APIs de IA (OpenAI / Anthropic). No conoce
botones ni pantallas visuales. La UI (Worktree 2, Streamlit) se comunica con él
exclusivamente por HTTP a través de los endpoints expuestos en core/main.py.
"""

from core.config import settings

__all__ = ["settings"]
