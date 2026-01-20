import logging
from .base_pipeline import BasePipeline
from ..utils.utilsForAgents import *
from agentscope.message import Msg
from agentscope.pipeline import MsgHub

logger = logging.getLogger("abogado_pipeline")

class AbogadoPipeline(BasePipeline):
    """
    Pipeline del sistema "Abogado-del-Diablo".
    Estructura idéntica al StandardPipeline (2 agentes: Validador + Orientador),
    pero orientado a cuestionar y desafiar argumentos.
    
    La diferencia principal está en los prompts que recibe de la BD,
    que deben estar diseñados para fomentar el pensamiento crítico y la contraargumentación.
    """
    def __init__(self, factory, prompt_validador, prompt_orientador):
        super().__init__(timeout=15)
        # Agentes específicos de este pipeline
        self.agenteValidador = factory.create_agent("Validador", prompt_validador)
        self.agenteOrientador = factory.create_agent("Orientador", prompt_orientador)
        self.agentes = [self.agenteValidador, self.agenteOrientador]

    async def start_session(self, tema_sala: str, usuarios_sala: list, idioma: str):
        await self.set_hub(tema_sala, usuarios_sala, idioma)
        
        # Lógica de bienvenida
        mensaje = Msg(name="Host", role="system", content="Sesión iniciada. Orientador, explica el objetivo.")
        await self._broadcast(mensaje)
        res = await self._call_agent(self.agenteOrientador)
        
        return [{"agente": "Orientador", "respuesta": self.ensure_text(self.extract_content(res))}]

    async def entrar_mensaje_a_la_sala(self, username: str, mensaje: str):
        msg = Msg(name=sanitize_name(username), role='user', content=mensaje)
        return await self.evaluar_intervencion_en_cascada(msg)

    async def evaluar_intervencion_en_cascada(self, mensaje: Msg):
        await self._broadcast(mensaje)
        res_val = await self._call_agent(self.agenteValidador, mensaje)
        texto_val = self.ensure_text(self.extract_content(res_val))
        
        respuestas = [{"agente": "Validador", "respuesta": texto_val}]
        
        if filter_agents(texto_val, self.agentes):
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