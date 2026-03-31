import logging
import json
import os
from datetime import datetime
from .base_pipeline import BasePipeline
from agentscope.message import Msg
from agentscope.pipeline import MsgHub

logger = logging.getLogger("no_ia_pipeline")

class NoIaPipeline(BasePipeline):
    """
    Pipeline sin agentes de IA.
    Los usuarios conversan directamente sin intervención de IA.
    Solo registra los mensajes de los usuarios en el historial.
    """

    def __init__(self):
        super().__init__(timeout=15)
        # Sin agentes - directa entre usuarios
        self.agentes = []
        self.usuarios_sala = []

    async def start_session(self, tema_sala: str, usuarios_sala: list, idioma: str):
        """Inicia la sesión sin agentes. Solo registra el inicio."""
        await self.set_hub(tema_sala, usuarios_sala, idioma)
        
        # Inicializar lista de usuarios
        self.usuarios_sala = usuarios_sala or []
        
        # Mensaje de bienvenida informativo
        mensaje_inicio = Msg(
            name="Host", 
            role="system", 
            content=f"Sesión iniciada. Tema: {tema_sala}. Los participantes conversan directamente sin asistencia de IA."
        )
        await self._broadcast(mensaje_inicio)
        
        return [{"agente": "Host", "respuesta": "Sesión sin IA iniciada. Adelante con la conversación."}]

    async def entrar_mensaje_a_la_sala(self, username: str, mensaje: str):
        """
        Recibe un mensaje de usuario y simplemente lo registra sin procesamiento de IA.
        
        Args:
            username: Nombre del usuario
            mensaje: Contenido del mensaje
            
        Returns:
            None (no hay respuestas de IA)
        """
        from ..utils.utilsForAgents import sanitize_name
        
        nombre_limpio = sanitize_name(username)
        msg = Msg(name=nombre_limpio, role='user', content=mensaje)
        
        # Solo registrar el mensaje en el historial
        await self._broadcast(msg)
        
        # No hay procesamiento de IA, así que retornamos None
        return None

    async def evento_timer(self):
        """
        Evento de timer. Sin IA, solo registra un recordatorio.
        """
        recordatorio = Msg(
            name="Host",
            role="system",
            content="Recordatorio: Continúen con la conversación según lo planeado."
        )
        await self._broadcast(recordatorio)
        return [{"agente": "Host", "respuesta": "Recordatorio enviado."}]

    async def avisar_tiempo(self, elapsed_time: int, remaining_time: int):
        """
        Aviso de tiempo transcurrido. Sin IA, solo lo registra.
        """
        if not self.hub:
            logger.warning("[NoIA Pipeline] Hub no disponible")
            return None

        mensaje_tiempo = Msg(
            name="Host",
            role="system",
            content=f"Tiempo transcurrido: {self.formato_tiempo(elapsed_time)}. Tiempo restante: {self.formato_tiempo(remaining_time)}."
        )
        await self._broadcast(mensaje_tiempo)

    async def mensaje_hito_temporal(self, hito: int, msg_base: str, elapsed_time: int, remaining_time: int):
        """
        Procesa hitos temporales (25%, 50%, 75%, 100%). Sin IA, solo registra.
        """
        if not self.hub:
            return None

        mensaje_hito = Msg(
            name="Host",
            role="system",
            content=f"[{hito}%] {msg_base} Tiempo restante: {self.formato_tiempo(remaining_time)}."
        )
        await self._broadcast(mensaje_hito)
        return [{"agente": "Host", "respuesta": msg_base}]

    async def stop_session(self) -> None:
        """
        Finalización: exporta logs y cierra la sesión.
        """
        if self.hub:
            try:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                tema_slug = (self.tema_sala or "sin_tema")[:50]
                ruta = f"./logs/conversacion_{tema_slug}_{timestamp}.json"
                os.makedirs(os.path.dirname(ruta), exist_ok=True)
                
                await self.guardar_conversacion_json(ruta)
                logger.info(f"[✅ Log savedado]: {ruta}")
            except Exception as e:
                logger.error(f"[❌ Error exportando]: {e}")

            await self.hub.__aexit__(None, None, None)
            self.hub = None
