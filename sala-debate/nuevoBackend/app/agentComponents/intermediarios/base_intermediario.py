import asyncio
import re
import logging
from typing import Optional, List, Dict, Any
from abc import ABC, abstractmethod
from .timer import Timer
from app.models.models import insert_message, SenderType

logger = logging.getLogger("base_intermediario")

class BaseIntermediario(ABC):
    def __init__(self, sio, sala: str, room_session_id):
        self.sio = sio
        self.sala = sala
        self.room_session_id = room_session_id
        
        # Infraestructura de mensajes
        self.message_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self.processing_task = asyncio.create_task(self._process_messages())
        
        # Gestión de tiempo
        self.timer = Timer()
        self.timer_silencio_consecutivo = 0
        self.hubo_mensaje_desde_ultimo_callback = False
        
        # Pipeline (se define en las subclases)
        self.pipeLine = None

    # --- Gestión de Cola ---
    async def _process_messages(self):
        while True:
            username, message, user_message_id = await self.message_queue.get()
            try:
                resultado = await self.agregarMensage(username, message, user_message_id)
                if resultado:
                    await self.sio.emit("evaluacion", resultado, room=self.sala)
            except Exception as e:
                logger.error(f"Error procesando mensaje en {self.sala}: {e}")
            finally:
                self.message_queue.task_done()

    async def enqueue(self, username: str, message: str, user_message_id: int):
        await self.message_queue.put((username, message, user_message_id))

    # --- Gestión de Timer ---
    async def start_timer(self, duration_seconds: int, update_interval: int):
        self.timer.callback = self.callback
        await self.sio.emit("timer_user_update", {
            "elapsed_time": 0,
            "remaining_time": duration_seconds
        }, room=self.sala)
        asyncio.create_task(self.timer.run(duration_seconds, update_interval))

    def get_timer_state(self) -> Dict[str, int]:
        state = self.timer.get_state()
        return {
            "elapsed_time": state.get("elapsed_seconds", 0),
            "remaining_time": state.get("remaining_seconds", 0),
        }

    async def stop_session(self):
        if self.pipeLine:
            await self.pipeLine.stop_session()
        self.timer.stop()

    # --- Lógica de Sesión Común ---
    async def start_session(self, topic: str, usuarios_sala: list, idioma: str):
        """Inicia la sesión y procesa todas las respuestas iniciales del pipeline."""
        respuestas = await self.pipeLine.start_session(topic, usuarios_sala, idioma)
        
        # Iteramos sobre las respuestas para persistirlas y emitirlas
        if respuestas:
            for r in respuestas:
                self._insert_in_db(agent_name=r["agente"], content=r["respuesta"])
            
            await self.sio.emit("evaluacion", respuestas, room=self.sala)

    # --- Callbacks y Eventos ---
    async def callback(self, elapsed_time: int, remaining_time: int, hito_alcanzado: Optional[int] = None):
        try:
            if hito_alcanzado:
                await self._manejar_hito_temporal(hito_alcanzado, elapsed_time, remaining_time)

            await self.pipeLine.avisar_tiempo(elapsed_time, remaining_time)
            await self.sio.emit("timer_user_update", {"elapsed_time": elapsed_time, "remaining_time": remaining_time}, room=self.sala)

            # Detección de silencio
            if self.hubo_mensaje_desde_ultimo_callback:
                self.timer_silencio_consecutivo = 0
                self.hubo_mensaje_desde_ultimo_callback = False
            else:
                self.timer_silencio_consecutivo += 1

            if self.timer_silencio_consecutivo >= 2:
                self.timer_silencio_consecutivo = 0
                resultado = await self.pipeLine.evento_timer()
                if resultado:
                    await self.sio.emit("evaluacion", resultado, room=self.sala)
        except Exception as e:
            logger.error(f"[Error callback timer {self.sala}]: {e}")

    async def _manejar_hito_temporal(self, hito: int, elapsed_time: int, remaining_time: int):
        """Procesa hitos de tiempo delegando la autoría al pipeline."""
        mensajes_base = {
            25: "Se ha cumplido un cuarto del tiempo.",
            50: "Mitad del tiempo transcurrido.",
            75: "Queda un cuarto del tiempo.",
            100: "Tiempo finalizado."
        }
        msg_base = mensajes_base.get(hito, f"Hito {hito}% alcanzado.")
        
        # El pipeline decide qué agente responde al hito
        respuestas = await self.pipeLine.mensaje_hito_temporal(hito, msg_base, elapsed_time, remaining_time)
        
        if respuestas:
            for r in respuestas:
                self._insert_in_db(agent_name=r["agente"], content=r["respuesta"])
            await self.sio.emit("evaluacion", respuestas, room=self.sala)

    # --- Helpers ---
    def _insert_in_db(self, agent_name, content, parent_id=None, used_ids=None):
        """Helper para centralizar inserciones en DB."""
        if self.room_session_id:
            try:
                insert_message(
                    room_session_id=self.room_session_id,
                    user_id=None,
                    agent_name=agent_name,
                    sender_type=SenderType.agent,
                    content=content,
                    parent_message_id=parent_id,
                    used_message_ids=used_ids
                )
            except Exception as e:
                logger.error(f"Error DB ({agent_name}): {e}")

    def contiene_mencion_orientador(self, mensaje: str) -> bool:
        return bool(re.search(r'@orientador\b', str(mensaje), re.IGNORECASE))

    @abstractmethod
    async def agregarMensage(self, userName: str, message: str, user_message_id: int):
        pass