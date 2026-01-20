from .base_intermediario import BaseIntermediario
from .qualityPipeline import QualityPipeline
from .factory_agents import ReActAgentFactory

class IntermediarioToulmin(BaseIntermediario):
    def __init__(self, prompts: dict, sio, sala, room_session_id, config_multiagente=None):
        super().__init__(sio, sala, room_session_id)
        
        # Extraemos lo específico de Toulmin
        self.tamañoVentana = config_multiagente.ventana_mensajes if config_multiagente else 5
        
        self.pipeLine = QualityPipeline(
            factory=ReActAgentFactory(),
            prompt_validador=prompts.get("Validador"),
            prompt_curador=prompts.get("Curador"),
            prompt_orientador=prompts.get("Orientador")
        )

    async def agregarMensage(self, userName, message, user_message_id):
        self.hubo_mensaje_desde_ultimo_callback = True

        # Reacción a mención @orientador
        if self.contiene_mencion_orientador(message):
            res = await self.pipeLine.reactiveResponse(userName, message)
            if res:
                self._insert_in_db("Orientador", res[0]["respuesta"])
            return res

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
            return respuesta_cascada
        return None