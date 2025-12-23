import asyncio
import logging
import json
import os
from abc import ABC, abstractmethod
from datetime import datetime
from .utils.utilsForAgents import formato_tiempo
from agentscope.message import Msg
from agentscope.pipeline import MsgHub

logger = logging.getLogger("base_pipeline")

class BasePipeline(ABC):
    def __init__(self, timeout: int = 15):
        self._timeout = timeout
        self._lock_call = asyncio.Lock()
        self._lock_observe = asyncio.Lock()
        self._lock_broadcast = asyncio.Lock()
        
        self.hub = None
        self.agentes = []
        self.tema_sala = None

    # --- Métodos de ejecución protegidos ---
    async def _call_agent(self, agent, msg: Msg | None = None):
        try:
            async with self._lock_call:
                return await asyncio.wait_for(
                    agent(msg) if msg else agent(),
                    timeout=self._timeout
                )
        except asyncio.TimeoutError:
            logger.warning(f"[Timeout] agente={agent.name}")
            return None
        except Exception as e:
            logger.error(f"[Error LLM] agente={agent.name} err={e}")
            return None

    async def _observe_agent(self, agent, msg: Msg) -> bool:
        if not agent: return False
        try:
            async with self._lock_observe:
                await asyncio.wait_for(agent.observe(msg), timeout=self._timeout)
            return True
        except Exception as e:
            logger.error(f"[Observe error] agente={agent.name} err={e}")
            return False

    async def _broadcast(self, msg: Msg) -> bool:
        if not self.hub: return False
        try:
            async with self._lock_broadcast:
                await self.hub.broadcast(msg)
            return True
        except Exception as e:
            logger.error(f"[Broadcast error]: {e}")
            return False

    # --- Lógica de Sesión ---
    def _generar_prompt_inicio(self, usuarios_sala: list, idioma: str) -> str:
        """Genera el bloque de texto estándar incluyendo el TEMA de la sala."""
        participantes_text = "\n".join(f"- {u}" for u in usuarios_sala) if usuarios_sala else "Ninguno"
        
        return f"""
        === CONTEXTO DE LA SESIÓN ===
        TEMA CENTRAL: {self.tema_sala}
        IDIOMA: {idioma}
        
        PARTICIPANTES:
        {participantes_text}

        INSTRUCCIONES:
        1. Toda intervención debe estar alineada con el TEMA CENTRAL.
        2. Las respuestas deben ser en {idioma}.
        """

    async def stop_session(self) -> None:
        """Finalización estándar: exporta logs y cierra el hub."""
        if self.hub:
            try:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                tema_slug = (self.tema_sala or "sin_tema")[:50]
                ruta = f"./logs/conversacion_{tema_slug}_{timestamp}.json"
                os.makedirs(os.path.dirname(ruta), exist_ok=True)
                
                await self.guardar_conversacion_json(ruta)
                print(f"[✅ Log guardado]: {ruta}")
            except Exception as e:
                print(f"[❌ Error exportando]: {e}")

            await self.hub.__aexit__(None, None, None)
            self.hub = None

    async def reactiveResponse(self, usuario: str, mensaje: str, agent_name: str = "Orientador"):
        """Respuesta genérica cuando un usuario invoca a un agente específico."""
        from .utils.utilsForAgents import sanitize_name
        
        msg_usuario = Msg(name=sanitize_name(usuario), role="user", content=mensaje)
        await self._broadcast(msg_usuario)
        
        agente = next((a for a in self.agentes if a.name == agent_name), None)
        if not agente: return []

        respuesta = await self._call_agent(agente, msg_usuario)
        return [{
            "agente": agent_name,
            "respuesta": self.ensure_text(self.extract_content(respuesta))
        }]

    # --- Helpers de formato y extracción ---
    def ensure_text(self, msg):
        if hasattr(msg, "to_dict"): msg = msg.to_dict()
        if isinstance(msg, list): return "\n".join(self.ensure_text(m) for m in msg)
        if isinstance(msg, dict):
            return msg.get("text") or msg.get("content") or msg.get("value") or json.dumps(msg)
        return str(msg)

    def extract_content(self, raw):
        return raw.content if hasattr(raw, "content") else str(raw)
    
    async def show_memory(self) -> dict:
        """
        Retorna la memoria de los agentes como texto legible, estructurando los mensajes para análisis de un nuevo agente.
        """
        def serialize_msg_content(msg):
            """
            Convierte el contenido de un mensaje a texto legible.
            """
            content_texts = []
            if isinstance(msg.content, str):
                content_texts.append(msg.content)
            elif isinstance(msg.content, list):
                # lista de tool_use/tool_result
                for block in msg.content:
                    if isinstance(block, dict):
                        if block.get("type") == "tool_use":
                            response = block.get("input", {}).get("response")
                            if response:
                                content_texts.append(f"[TOOL_USE]\n{response}")
                        elif block.get("type") == "tool_result":
                            output_blocks = block.get("output", [])
                            for ob in output_blocks:
                                if ob.get("type") == "text":
                                    content_texts.append(f"[TOOL_RESULT]\n{ob.get('text')}")
            else:
                try:
                    # Intentamos serializar JSON si es BaseModel o dict
                    content_texts.append(json.dumps(msg.content, indent=2, ensure_ascii=False))
                except:
                    content_texts.append(str(msg.content))
            return "\n".join(content_texts)

        memoria_total = {}
        for agente in self.agentes:
            memoria_agente = []
            mensajes_historial = await agente.memory.get_memory()
            for idx, msg in enumerate(mensajes_historial, start=1):
                timestamp = getattr(msg, "timestamp", "")
                role = getattr(msg, "role", "unknown")
                author = getattr(msg, "author", agente.name)
                content = serialize_msg_content(msg)
                memoria_agente.append(
                    f"--- Mensaje {idx} ---\n"
                    f"Timestamp: {timestamp}\n"
                    f"Rol: {role}\n"
                    f"Autor: {author}\n"
                    f"Contenido:\n{content}\n"
                )
            memoria_total[agente.name] = memoria_agente
        return memoria_total
    
    async def exportar_conversacion_completa(self) -> dict:
        """
        Devuelve la conversación completa (mensajes humanos + agentes)
        en formato estructurado y cronológico
        """
        if not self.hub:
            raise RuntimeError("No hay sesión activa para exportar.")

        registro = {
            "tema": getattr(self, "tema_sala", ""),
            "timestamp_exportacion": datetime.now().isoformat(),
            "mensajes": []
        }

        #  Recuperar los mensajes históricos del hub (orden cronológico real)
        if hasattr(self.hub, "history"):
            for msg in self.hub.history:
                registro["mensajes"].append({
                    "timestamp": getattr(msg, "timestamp", None),
                    "autor": getattr(msg, "name", "Desconocido"),
                    "rol": getattr(msg, "role", "unknown"),
                    "contenido": str(msg.content),
                    "tipo": "hub_message"
                })

        #  Agregar la memoria interna de los agentes
        memoria = await self.show_memory()
        for agente, mensajes in memoria.items():
            for idx, msg_texto in enumerate(mensajes, start=1):
                registro["mensajes"].append({
                    "timestamp": None,
                    "autor": agente,
                    "rol": "agent_memory",
                    "contenido": msg_texto,
                    "tipo": "memoria_agente",
                    "orden_memoria": idx
                })

        #  Ordenar por timestamp si existe
        registro["mensajes"].sort(key=lambda m: m.get("timestamp") or "", reverse=False)

        return registro

    async def guardar_conversacion_json(self, ruta_archivo: str) -> str:
        """
        Guarda la conversación exportada como archivo JSON ordenado.
        """
        datos = await self.exportar_conversacion_completa()
        with open(ruta_archivo, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=2, ensure_ascii=False)
        return ruta_archivo
    
    # -----------------------------------------------------------------------
    # GESTIÓN DE TIEMPO Y HITOS (Lógica Común)
    # -----------------------------------------------------------------------

    async def avisar_tiempo(self, elapsed_time: int, remaining_time: int):
        """
        Envía un aviso de tiempo al hub para que todos los agentes (y el log) 
        estén al tanto del progreso.
        """
        if not self.hub:
            logger.warning("[Pipeline] Hub no disponible en avisar_tiempo")
            return None

        
        mensaje_tiempo = (
            f"**Actualización del tiempo**\n"
            f"- Tiempo transcurrido: {formato_tiempo(elapsed_time)}\n"
            f"- Tiempo restante: {formato_tiempo(remaining_time)}\n\n"
        )
        
        msg_tiempo = Msg(name="Timer", role="system", content=mensaje_tiempo)
        
        await self._broadcast(msg_tiempo)
        return None

    @abstractmethod
    async def mensaje_hito_temporal(self, hito: int, mensaje_base: str, elapsed_time: int, remaining_time: int):
        return

    @abstractmethod
    async def evento_timer(self):
        return