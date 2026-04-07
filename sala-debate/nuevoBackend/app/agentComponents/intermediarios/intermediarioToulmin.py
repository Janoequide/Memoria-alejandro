from .base_intermediario import BaseIntermediario
from ..pipelines.qualityPipeline import QualityPipeline
from ..factory_agents import ReActAgentFactory
import time
import logging

logger = logging.getLogger("intermediario_toulmin")

class IntermediarioToulmin(BaseIntermediario):
    def __init__(self, prompts: dict, sio, sala, room_session_id, config_multiagente=None):
        super().__init__(sio, sala, room_session_id)
        
        # Nombre del orientador (default para Toulmin)
        self.nombre_orientador = "Orientador"
        
        # Extraemos lo específico de Toulmin
        self.tamañoVentana = config_multiagente.ventana_mensajes if config_multiagente else 5
        
        self.pipeLine = QualityPipeline(
            factory=ReActAgentFactory(),
            prompt_validador=prompts.get("Validador"),
            prompt_curador=prompts.get("Curador"),
            prompt_orientador=prompts.get("Orientador")
        )
        # nombre de sala para los logs
        self.pipeLine.sala_name = sala

        # Estado del Cooldown para @orientador
        self.ultima_intervencion_ts = 0
        self.cooldown_actual = 60
        self.min_cooldown = 60
        self.max_cooldown = 600

        # Seguimiento de mensajes para ventana
        self.numeroMensajes = 0
        self.ids_mensajes_ventana = []

    def puede_intervenir(self) -> bool:
        """Devuelve True si el tiempo de enfriamiento ha pasado."""
        return (time.time() - self.ultima_intervencion_ts) >= self.cooldown_actual

    async def agregarMensage(self, userName, message, user_message_id):
        self.hubo_mensaje_desde_ultimo_callback = True

        # Reacción a mención @orientador respeta cooldown
        if self.contiene_mencion_orientador(message):
            if not self.puede_intervenir():
                # Está en cooldown, ignorar mención
                tiempo_restante = int(self.cooldown_actual - (time.time() - self.ultima_intervencion_ts))
                print(f"\n⏳ COOLDOWN ACTIVO - No se puede invocar LLM. Tiempo restante: {tiempo_restante}s\n")
                logger.info(f"[{self.sala}] @orientador mencionado pero en cooldown (resto: {tiempo_restante}s)")
                return None
            
            res = await self.pipeLine.reactiveResponse(userName, message)
            if res:
                self._insert_in_db("Orientador", res[0]["respuesta"])
                self.ultima_intervencion_ts = time.time()  # Actualizar timestamp de intervención
                return self._transformar_respuestas(res)
            return None

        # Flujo de Ventana / Calidad
        res_validador = await self.pipeLine.entrar_mensaje_a_la_sala(username=userName, mensaje=message)
        if res_validador:
            self._insert_in_db("Validador", res_validador, parent_id=user_message_id)

        self.numeroMensajes += 1
        self.ids_mensajes_ventana.append(user_message_id)

        if self.numeroMensajes >= self.tamañoVentana:
            respuesta_cascada = await self.pipeLine.evaluar_intervencion_en_cascada()
            for r in respuesta_cascada:
                nombre_agente = r.get("agente", "").capitalize()
                self._insert_in_db(nombre_agente, r.get("respuesta", ""), used_ids=self.ids_mensajes_ventana.copy())
            
            self.ids_mensajes_ventana = []
            self.numeroMensajes = 0
            return self._transformar_respuestas(respuesta_cascada)
        return None