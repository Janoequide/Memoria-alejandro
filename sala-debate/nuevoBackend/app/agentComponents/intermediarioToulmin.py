import asyncio
import re
from typing import Optional, List, Dict, Any
from .timer import Timer  
from .factory_agents import ReActAgentFactory  
from .qualityPipeline import QualityPipeline
from app.models.models import (
    insert_message,
    SenderType
)
class IntermediarioToulmin:
    def __init__(
        self,
        tamañoVentana: int,
        prompt_agenteValidador: str,
        prompt_agenteCurador: str,
        prompt_agenteOrientador: str,
        sio,
        sala: str,
        room_session_id
    ):
        self.room_session_id = room_session_id
        self.pipeLine = QualityPipeline(
            factory=ReActAgentFactory(),
            prompt_agenteValidador=prompt_agenteValidador,
            promtp_agenteCurador=prompt_agenteCurador,
            promt_agenteOrientador=prompt_agenteOrientador
        )

        self.tamañoVentana = tamañoVentana
        self.numeroMensajes = 0
        self.ids_mensajes_ventana = []

        self.sio = sio
        self.sala = sala

        # Cola async para serializar mensajes por sala
        self.message_queue: asyncio.Queue = asyncio.Queue(maxsize=500)

        # Worker que procesa la cola (se crea en el loop actual)
        self.processing_task: Optional[asyncio.Task] = asyncio.create_task(self._process_messages())

        # Timer async
        self.timer = Timer()
        # Controles de silencio / hits
        self.timer_silencio_consecutivo = 0
        self.hubo_mensaje_desde_ultimo_callback = False


    # ---- cola / worker ----
    async def _process_messages(self):
        while True:
            username, message, user_message_id = await self.message_queue.get()
            try:
                resultado = await self.agregarMensage(username, message, user_message_id)
                if resultado:
                    # Emitir resultado al room
                    await self.sio.emit("evaluacion", resultado, room=self.sala)
            except Exception as e:
                print(f"Error procesando mensaje en {self.sala}: {e}")
            finally:
                self.message_queue.task_done()

    async def enqueue(self, username: str, message: str, user_message_id: int):
        """
        Se llama desde los handlers socket: await intermediario.enqueue(...)
        """
        await self.message_queue.put((username, message, user_message_id))

    # ---- timer & estado ----
    async def start_timer(self, duration_seconds: int, update_interval: int):
        """
        Inicia el timer; `Timer.run` es una coroutine no bloqueante.
        Lanza una tarea y retorna inmediatamente.
        """
        # el Timer llamará a self.callback_periodic
        self.timer.callback = self.callback

        await self.sio.emit("timer_user_update", {
            "elapsed_time": 0,
            "remaining_time": duration_seconds
        }, room=self.sala)
        # lanzar como tarea separada en el event loop
        asyncio.create_task(self.timer.run(duration_seconds, update_interval))

    def get_timer_state(self) -> Dict[str, int]:
        state = self.timer.get_state()
        return {
            "elapsed_time": state.get("elapsed_seconds", 0),
            "remaining_time": state.get("remaining_seconds", 0),
        }

    # ---- lógica del pipeline ----
    async def agregarMensage(self, userName: str, message: str, user_message_id: int) -> Optional[List[Dict[str, Any]]]:

        self.hubo_mensaje_desde_ultimo_callback = True

        # Verificar mención al orientador
        if self.contiene_mencion_orientador(message):
            respuesta = await self.pipeLine.reactiveResponse(userName, message)
            if respuesta:
                contenido = respuesta[0]["respuesta"]
                insert_message(
                    room_session_id=self.room_session_id,
                    user_id=None,
                    agent_name="Orientador",
                    sender_type=SenderType.agent,
                    content=contenido
                )
            return respuesta

        # pipiline normal
        respuesta_validador = await self.pipeLine.entrar_mensaje_a_la_sala(username=userName, mensaje=message)
        if respuesta_validador:
            insert_message(
                room_session_id=self.room_session_id,
                user_id=None,
                agent_name="Validador",
                sender_type=SenderType.agent,
                content=respuesta_validador,
                parent_message_id=user_message_id
            )

        self.numeroMensajes += 1
        self.ids_mensajes_ventana.append(user_message_id)
        print(f"[{self.sala}] Mensajes en ventana actual: {self.ids_mensajes_ventana}")
        if(self.numeroMensajes >= self.tamañoVentana):
            respuesta_cascada = await self.pipeLine.evaluar_intervencion_en_cascada()
            for r in respuesta_cascada: 
                agente = r.get("agente","").lower()
                contenido = r.get("respuesta","")
                if agente == "curador":
                    insert_message(
                        room_session_id=self.room_session_id,
                        user_id=None,
                        agent_name="Curador",
                        sender_type=SenderType.agent,
                        content=contenido,
                        used_message_ids=self.ids_mensajes_ventana.copy()
                    )
                else: 
                    insert_message(
                        room_session_id=self.room_session_id,
                        user_id=None,
                        agent_name=agente.capitalize(),
                        sender_type=SenderType.agent,
                        content=contenido,
                        used_message_ids=self.ids_mensajes_ventana.copy()
                    )
            self.ids_mensajes_ventana = []
            self.numeroMensajes = 0
            return respuesta_cascada

    async def start_session(self, topic: str, usuarios_sala: list, idioma: str):
        respuesta = await self.pipeLine.start_session(topic, usuarios_sala, idioma)
        contenido = ""
        if isinstance(respuesta, list) and len(respuesta) > 0:
            contenido = respuesta[0].get("respuesta", "")
        else:
            contenido = str(respuesta)
        if self.room_session_id:
            insert_message(
                room_session_id=self.room_session_id,
                user_id=None,
                agent_name="Orientador",
                sender_type=SenderType.agent,
                content=contenido
            )
        # Emitir resultado al room
        await self.sio.emit("evaluacion", respuesta, room=self.sala)

    async def stop_session(self):
        await self.pipeLine.stop_session()
        self.timer.stop()


    # ---- callback invocado por Timer ----
    async def callback(self, elapsed_time: int, remaining_time: int, hito_alcanzado: Optional[int] = None):
        try:
            if hito_alcanzado:
                await self._manejar_hito_temporal(hito_alcanzado, elapsed_time, remaining_time)

            await self.pipeLine.avisar_tiempo(elapsed_time, remaining_time)

            # emitir estado de timer
            await self.sio.emit("timer_user_update", {
                "elapsed_time": elapsed_time,
                "remaining_time": remaining_time
            }, room=self.sala)

            # DETECCIÓN DE SILENCIO
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
            print(f"[Error crítico en callback timer de {self.sala}]: {e}")
            try:
                await self.sio.emit("timer_user_update", {
                    "elapsed_time": elapsed_time,
                    "remaining_time": remaining_time
                }, room=self.sala)
            except:
                pass

    async def _manejar_hito_temporal(self, hito: int, elapsed_time: int, remaining_time: int):
        try:
            mensajes_hito = {
                25: "Se ha cumplido un cuarto del tiempo de la sesión. Es un buen momento para verificar que todos estén participando y que las ideas fluyan con claridad.",
                50: "Hemos llegado a la mitad del tiempo disponible. Asegúrense de que los argumentos principales ya hayan sido presentados y que el debate esté bien encaminado para llegar a un consenso, sobre todo si los participantes discrepan ayudalos converger a un consenso comun.",
                75: "Se han completado tres cuartos de la sesión. Este es el momento clave para consolidar sus posiciones y preparar conclusiones.",
                100: "El tiempo de la sesión ha finalizado. Es momento de hacer un cierre y resumir los puntos principales del debate."
            }
            mensaje_orientador = mensajes_hito.get(hito, f"Hito temporal alcanzado: {hito}%")
            respuesta = await self.pipeLine.mensaje_hito_temporal(hito, mensaje_orientador, elapsed_time, remaining_time)

            if respuesta:
                if isinstance(respuesta, list) and len(respuesta) > 0:
                    contenido = respuesta[0].get("respuesta", "")
                else:
                    contenido = str(respuesta)


                try:
                    insert_message(
                        room_session_id=self.room_session_id,
                        user_id=None,
                        agent_name="Orientador",
                        sender_type=SenderType.agent,
                        content=contenido
                    )
                except Exception as db_error:
                    print(f"[Error DB guardando mensaje de hito]: {db_error}")

                await self.sio.emit("evaluacion", respuesta, room=self.sala)
        except Exception as e:
            print(f"[Error manejando hito temporal {hito}% en {self.sala}]: {e}")

    def contiene_mencion_orientador(self, mensaje: str) -> bool:
        if not isinstance(mensaje, str):
            return False
        patron = r'@orientador\b'
        return re.search(patron, mensaje, re.IGNORECASE) is not None
