import logging
from .base_pipeline import BasePipeline
from ..utils.utilsForAgents import *
from agentscope.message import Msg
from agentscope.pipeline import MsgHub

logger = logging.getLogger("standard_pipeline")

class QualityPipeline(BasePipeline):
    def __init__(self, factory, prompt_validador, prompt_curador, prompt_orientador):
        super().__init__(timeout=15)
        self.agenteValidador = factory.create_agent("Validador", prompt_validador)
        self.agenteOrientador = factory.create_agent("Orientador", prompt_orientador)
        self.agenteCurador = factory.create_agent("Curador", prompt_curador)
        
        self.agentes = [self.agenteCurador, self.agenteOrientador]

    async def start_session(self, tema_sala: str, usuarios_sala: list, idioma: str):
        await self.set_hub(tema_sala, usuarios_sala, idioma)
        
        # Lógica específica de inicio
        inicio_msg = Msg(name="Host", role="system", content="La sesión ha comenzado. Orientador, da la bienvenida.")
        await self._broadcast(inicio_msg)
        
        res = await self._call_agent(self.agenteOrientador, inicio_msg)
        return [{"agente": "Orientador", "respuesta": self.ensure_text(self.extract_content(res))}]

    async def entrar_mensaje_a_la_sala(self, username: str, mensaje: str):
        msg = Msg(name=sanitize_name(username), role='user', content=mensaje)
        # Toulmin envía el mensaje al Validador directamente
        res = await self._call_agent(self.agenteValidador, msg)
        return self.ensure_text(self.extract_content(res))

    async def evaluar_intervencion_en_cascada(self):
        # Lógica de Curador -> Orientador
        msg_curador = Msg(name="Host", role="system", content="Evalúa si se necesita intervención.")
        res_curador = await self._call_agent(self.agenteCurador, msg_curador)
        texto_curador = self.ensure_text(self.extract_content(res_curador))
        
        respuestas = [{"agente": "Curador", "respuesta": texto_curador}]
        
        if filter_agents(texto_curador, self.agentes): # Si decide que sigue el Orientador
            res_ori = await self._call_agent(self.agenteOrientador)
            respuestas.append({"agente": "Orientador", "respuesta": self.ensure_text(self.extract_content(res_ori))})
        
        return respuestas
    
    async def mensaje_hito_temporal(self, hito: int, mensaje_base: str, elapsed_time: int, remaining_time: int):
        """
        Genera una instrucción para que el Orientador reaccione a un hito (25%, 50%, etc.).
        """
        instruccion = f"""
        **HITO TEMPORAL ALCANZADO: {hito}% del tiempo completado**
        Tiempo transcurrido: {self.formato_tiempo(elapsed_time)}
        Tiempo restante: {self.formato_tiempo(remaining_time)}
        {mensaje_base}
        
        Por favor, como Orientador:
        1. Haz una breve reflexión sobre el progreso del debate hasta ahora
        2. Motiva a los participantes según el momento de la sesión
        3. Da recomendaciones específicas para aprovechar el tiempo {"restante" if hito < 100 else "que tuvieron"}
        4. Debes ser crítico con el avance. Si no han avanzado lo suficiente, indícaselo a los participantes.
        5. Debes indicarle en que momento de la sesión se encuentran (inicio, mitad, casi finalizado, finalización).
        Tu mensaje debe ser conciso (máximo 3-4 oraciones) y estar en el idioma de la conversación.
        """

        msg_hito = Msg(name="Host", role="system", content=instruccion)

        try:
            # Informamos a la sala sobre el hito
            await self._broadcast(msg_hito)
            
            # Solicitamos la respuesta específica del Orientador
            agente_orientador = next((a for a in self.agentes if a.name == "Orientador"), None)
            if not agente_orientador:
                return [{"agente": "Orientador", "respuesta": mensaje_base}]

            respuesta = await self._call_agent(agente_orientador, msg_hito)
            texto = self.ensure_text(self.extract_content(respuesta))
            
            return [{"agente": "Orientador", "respuesta": texto or mensaje_base}]
            
        except Exception as e:
            logger.error(f"[Error hito temporal]: {e}")
            return [{"agente": "Orientador", "respuesta": mensaje_base}]

    async def evento_timer(self):
        """
        Intervención por inactividad: el Orientador motiva la participación.
        """
        msg = Msg(
            name="Host",
            role="system",
            content=(
                "Se ha detectado inactividad. Orientador: motiva la participación con una "
                "pregunta breve o pide profundizar un punto pendiente. No tomes postura."
            )
        )
        
        await self._broadcast(msg)
        
        agente_orientador = next((a for a in self.agentes if a.name == "Orientador"), None)
        if agente_orientador:
            respuesta = await self._call_agent(agente_orientador, msg)
            return [{
                "agente": "Orientador", 
                "respuesta": self.ensure_text(self.extract_content(respuesta))
            }]
        return []