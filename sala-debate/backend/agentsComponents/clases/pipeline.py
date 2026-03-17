import os
import time
import json, re
from datetime import datetime
from pydantic import BaseModel, Field, conint
from typing import Literal
from .factory_agents import ReActAgentFactory
from agentscope.message import Msg
from agentscope.pipeline import MsgHub, fanout_pipeline
from .BaseModels.baseModel import *
from utils.groupchat_utils import *
from.utils.utilsForAgents import *

class PuntuacionModel(BaseModel):
    score_dinamico: int = Field(..., ge=0, le=100, description="Un número entero entre 0 y 100")
    diagnostico_dinamico: str = Field(..., description="Breve explicación (15 palabras maximo) del score")

class Pipeline:
    def __init__(self,factory: ReActAgentFactory,
                 prompt_agenteValidador:str,
                 #prompt_agentePuntuador:str,
                 prompt_agenteCurador:str,
                 promt_agenteOrientador:str
                 ):
        self.agenteValidador = factory.create_agent(
            name="Validador",
            sys_prompt=prompt_agenteValidador
        )
        #self.agentePuntuador = factory.create_agent(
        #    name="Puntuador",
        #    sys_prompt=prompt_agentePuntuador
        #)
        self.agenteCurador = factory.create_agent(
            name="Curador",
            sys_prompt=prompt_agenteCurador
        )
        self.agenteOrientador = factory.create_agent(
            name="Orientador",
            sys_prompt=promt_agenteOrientador
        )
#TODO: revisar esto de la lista
        self.agentes = list([self.agenteCurador,self.agenteOrientador])
        self.hub = None
        self.msg_id = 0
        self.avisos_timer = 0
        self.baseModelValidador = None


    async def start_session(self, tema_sala:str,usuarios_sala:list,idioma:str) -> None:
        """
        Inicializa el msghub con el cual se va a trabajar en una sesion de discusion
        @Hint: mensaje con el cual se inicializan los agentes.
        """
        if(len(usuarios_sala) > 0):
            participantes_text = ""
            participantes_text = "\n".join(f"- {u}" for u in usuarios_sala)
        participantes = f"""
        En esta sesion hay ({len(usuarios_sala)}) usuarios.
        Los participantes en la discusión son los siguientes:
        {participantes_text}
        """
        idioma_prompt = f"""
        El idioma principal de esta conversación es **{idioma}**.
        Por lo tanto:
        1. Todos los análisis lingüísticos y semánticos (incluido el reconocimiento de argumentos según el modelo de Toulmin) deben realizarse en este idioma.
        2. Las respuestas, mensajes y retroalimentaciones generadas por el agente Orientador deben estar redactadas completamente en {idioma}.
        3. No traduzcas ni interpretes al inglés u otros idiomas a menos que el sistema o los participantes lo soliciten explícitamente.
        """


        self.baseModelValidador = BaseModelValidador.crear_modelo_inicial(usuarios_sala)

        self.tema_sala = tema_sala
        hint = Msg(
            name="Host",
            role="system",
            content= participantes + idioma_prompt
        )

        self.hub = await MsgHub(participants=self.agentes,announcement=hint).__aenter__()
        await self.agenteValidador.observe(hint)

        mensaje = Msg(
            name="Host",
            role="system",
            content="La sesión de debate ha comenzado. Orientador por favor da un mensaje de bienvenida y explica el objetivo de la actividad."
        )
        participantesMsg = Msg(
            name="Host",
            role="system",
            content=participantes
        )
        respuesta_validador = await self.agenteValidador(participantesMsg)
        try:
            #validacion_inicial = self.baseModelValidador.model_validate_json(respuesta_validador.content)
            validacion_inicial = safe_parse_json(respuesta_validador.content, self.baseModelValidador)
            print(validacion_inicial)
        except Exception as e:
            print(f"[Error de validación en start_session]: {e}")

        # garantizar que sea Msg antes de enviar
        if not isinstance(respuesta_validador, Msg):
            respuesta_validador = Msg(name=self.agenteValidador.name, role="assistant", content=self.ensure_text(respuesta_validador))
        await self._broadcast(respuesta_validador)
        respuesta_orientador = await self.agenteOrientador(mensaje)
        if not isinstance(respuesta_orientador, Msg):
            respuesta_orientador = Msg(name=self.agenteOrientador.name, role="assistant", content=self.ensure_text(respuesta_orientador))
        await self._broadcast(respuesta_orientador)
        return [{
            "agente":"Orientador",
            "respuesta":respuesta_orientador.content
        }]


    async def stop_session(self) -> None:
        """
        Cierra el MsgHub cuando termina la sesión de chat.
        """
        #tokens_totales = await self.contar_tokens_memoria()
        #print(tokens_totales)
        if self.hub:
            try:
                ruta = f"./logs/conversacion_{self.tema_sala[:100]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                os.makedirs(os.path.dirname(ruta), exist_ok=True)
                await self.guardar_conversacion_json(ruta)
                print(f"[✅ Conversación exportada antes de cerrar hub]: {ruta}")
            except Exception as e:
                print(f"[❌ Error exportando conversación antes del cierre]: {e}")

            await self.hub.__aexit__(None, None, None)
            self.hub = None
        memoria = await self.show_memory()
        print(memoria)

    async def anunciar_entrada_participante(self,userName:str) -> None:
        """
        Funcion que avisa al Hub cuando entra un participante a la sala.
        Así el sistema tiene conciencia de cuantos participantes hay conversando acerca del tema en cuestión.
        """
        prompt = "Ha entrado a la sala el participante llamado: " + userName
        msgSystem = Msg(name="host",
                        role="system",
                        content=prompt)
        await self.hub.broadcast(msgSystem)

    async def anunciar_salida_participante(self,userName:str) -> None:
        """
        Funcion que avisa al Hub cuando sale un participante a la sala.
        """
        prompt = "Ha salido de la sala el participante llamado: " + userName
        msgSystem = Msg(name="host",
                        role="system",
                        content=prompt)
        await self.hub.broadcast(msgSystem)

    async def entrar_mensaje_a_la_sala(self,username:str,mensaje:str):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # registrar en historial propio
        ts = datetime.now().isoformat()
        self._user_history.append({"timestamp": ts, "autor": username, "contenido": mensaje})
        username_sanitized = sanitize_name(username)
        msg = Msg(name=username_sanitized,
                  role='user',
                  content=mensaje)
        
        await self._broadcast(msg)
        respuesta_validador = await self.agenteValidador(msg)
        if not isinstance(respuesta_validador, Msg):
            respuesta_validador = Msg(
                name=self.agenteValidador.name,
                role="assistant",
                content=self.ensure_text(respuesta_validador)
            )
        await self._broadcast(respuesta_validador)
        return respuesta_validador.content

    
    async def avisar_tiempo(self, elapsed_time, remaining_time):
        """
        Envía un aviso de tiempo legible para los agentes, informando cuánto ha transcurrido y cuánto queda
        tanto en la fase actual como en la sesión total. En el primer aviso solo informa; en los siguientes,
        también solicita al Puntuador una evaluación.
        """
        if not self.hub:
            print("[Pipeline] Hub no disponible en avisar_tiempo")
            return None
        def formato_tiempo(segundos: int) -> str:
            minutos = segundos // 60
            segs = segundos % 60
            partes = []
            if minutos > 0:
                partes.append(f"{minutos} minuto{'s' if minutos != 1 else ''}")
            if segs > 0:
                partes.append(f"{segs} segundo{'s' if segs != 1 else ''}")
            return " y ".join(partes) if partes else "0 segundos"

        mensaje_tiempo = (
            f"**Actualización del tiempo**\n"
            f"- Tiempo transcurrido: {formato_tiempo(elapsed_time)}\n"
            f"- Tiempo restante: {formato_tiempo(remaining_time)}\n\n"
            f"Por favor, tengan en cuenta este avance temporal para sus decisiones y evaluaciones."
        )

        print("ACTUALIZACION DEL TIMER")

        msg_tiempo = Msg(
            name="Timer",
            role="system",
            content=mensaje_tiempo
        )
        print("AVISO TIMER ENVIADO AL HUB")
        try:
            await self._broadcast(msg_tiempo)
        except Exception as e:
            print(f"[Pipeline] Error broadcast msg_tiempo: {e}")
        return None


    
    async def evaluar_intervencion_en_cascada(self,mensaje:Msg):
        await self._broadcast(mensaje)
        print("se llama al curador PIPELINE")
        curador_msg = await self.agenteCurador(mensaje)
        print("respuesta del curador obtenida")
        respuestas = [{
            "agente":"Curador",
            "respuesta":curador_msg.content
        }]
        next_agent = filter_agents(curador_msg.content, self.agentes)
        if next_agent and next_agent[0].name == "Orientador":
            orientador_msg = await self.agenteOrientador()
            await self.agenteValidador.observe(orientador_msg)            
            respuestas.append({
                "agente":"Orientador",
                "respuesta":orientador_msg.content
            })
        return respuestas
    
    async def reactiveResponse(self,usuario:str,mensaje:str):
        """
        Funcion que se ejecuta cuando un participante de la sala llama al agente Orientador.
        """
        mensaje = str({
            "contenido":mensaje,
            "timeStamp":datetime.now()
        })
        nombre_limpio = sanitize_name(usuario)
        msgUsuario = Msg(name=nombre_limpio,
                         role="user",
                         content=mensaje)
        await self._broadcast(msgUsuario)
        respuesta = await self.agenteOrientador()
        await self.agenteValidador.observe(respuesta)
        return [{
            "agente":"Orientador",
            "respuesta":respuesta.content
        }]
    
    async def evento_ventana(self):
        """
        Funcion que se ejecuta para pedirle la opinión al Curador si es pertinente o no 
        intervenir en la conversación.
        """
        if not self.hub or self.hub == False: 
            raise RuntimeError("La sesión de chat no ha sido iniciada. Llama a start_session primero.")
        
        mensaje = """
                    Se a cumplido el tamaño de la ventana, por tanto el agente Curador debe decidir si hay que intervenir o no.
                  """
    
        msg = Msg(name="host",
                  role="system",
                  content=mensaje)
        
        respuestas = await self.evaluar_intervencion_en_cascada(msg)
        return respuestas
        

    async def evento_timer(self):
        """
        Evento que se usa cuando se detecta inactividad en la sala de debate. Se devuelve un mensaje del Orientador. 
        """
        msgSystem = f"""
        Se a detectado inactividad en la sala por parte de los estudiantes, por tanto agente Orientador debes intervenir para motivar la participación.
        """

        msg = Msg(name="host",
                  role="system",
                  content=msgSystem)
        respuesta_orientador = await self.agenteOrientador(msg)
        respuesta = [{
            "agente":"Orientador",
            "respuesta":respuesta_orientador.content
        }]
        return respuesta
    
    async def evento_lowScoreMessage(self, puntuacion:int):
        msgSystem = f"""
        El agente Puntuador ha asignado una puntuación muy baja ({puntuacion} puntos) al mensaje más reciente que ha entrado a la sala. 
        El Agente Curador debe decidir si es pertinente o no intervenir.
        """
        msg = Msg(name="host",
                  role="system",
                  content=msgSystem)
        respuestas = await self.evaluar_intervencion_en_cascada(msg)
        return respuestas
    
    async def mensaje_hito_temporal(self, hito: int, mensaje_base: str, elapsed_time: int, remaining_time: int):
        """
        Genera un mensaje del Orientador contextualizado para un hito temporal específico.
        
        Args:
            hito: Porcentaje del tiempo completado (25, 50, 75, 100)
            mensaje_base: Mensaje predefinido para este hito
            elapsed_time: Tiempo transcurrido en segundos
            remaining_time: Tiempo restante en segundos
        """
        def formato_tiempo(segundos: int) -> str:
            minutos = segundos // 60
            segs = segundos % 60
            partes = []
            if minutos > 0:
                partes.append(f"{minutos} minuto{'s' if minutos != 1 else ''}")
            if segs > 0:
                partes.append(f"{segs} segundo{'s' if segs != 1 else ''}")
            return " y ".join(partes) if partes else "0 segundos"

        instruccion = f"""
        **HITO TEMPORAL ALCANZADO: {hito}% del tiempo completado**
        
        Tiempo transcurrido: {formato_tiempo(elapsed_time)}
        Tiempo restante: {formato_tiempo(remaining_time)}
        
        {mensaje_base}
        
        Por favor, como Orientador:
        1. Haz una breve reflexión sobre el progreso del debate hasta ahora
        2. Motiva a los participantes según el momento de la sesión
        3. Da recomendaciones específicas para aprovechar el tiempo {"restante" if hito < 100 else "que tuvieron"}
        4. Mantén un tono {'alentador y energizante' if hito < 100 else 'de cierre y reflexión final'}
        5. Debes indicarle en que momento de la sesión se encuentran (inicio, mitad, casi finalizado, finalización).
        Tu mensaje debe ser conciso (máximo 3-4 oraciones) y estar en el idioma de la conversación.
        """

        msg_hito = Msg(
            name="Host",
            role="system",
            content=instruccion
        )

        try:
            # Broadcast del contexto temporal
            await self._broadcast(msg_hito)
            
            # Solicitar respuesta del Orientador
            respuesta_orientador = await self.agenteOrientador(msg_hito)
            
            if not respuesta_orientador or not respuesta_orientador.content:
                return [{
                    "agente": "Orientador",
                    "respuesta": mensaje_base  # Fallback al mensaje base
                }]
            
            return [{
                "agente": "Orientador",
                "respuesta": respuesta_orientador.content
            }]
            
        except Exception as e:
            print(f"[Error generando mensaje de hito temporal]: {e}")
            return [{
                "agente": "Orientador",
                "respuesta": mensaje_base
            }]
    
        
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

        #  Añadir mensajes de usuario guardados manualmente
        if self._user_history:
            registro["mensajes"].extend(self._user_history)
        #  Recuperar los mensajes históricos del hub (orden cronológico real).
        if hasattr(self.hub, "history"):
            for msg in self.hub.history:
                ts = getattr(msg, "timestamp", None) or datetime.now().isoformat()
                autor = getattr(msg, "name", "Desconocido")
                registro["mensajes"].append({
                    "timestamp": ts,
                    "autor": autor,
                    "contenido": str(msg.content),
                })

        #  No se incluyen entradas de memoria interna en el log general.

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
        

    
