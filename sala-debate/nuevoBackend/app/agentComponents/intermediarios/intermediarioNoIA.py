from .base_intermediario import BaseIntermediario
from ..pipelines.noIaPipeline import NoIaPipeline
import logging

logger = logging.getLogger("intermediario_no_ia")

class IntermediarioNoIA(BaseIntermediario):
    """
    Intermediario que permite que los usuarios conversen sin IA.
    Los participantes conversan directamente sin ningún tipo de asistencia externa.
    Se mantiene el logging para registro completo de la sesión.
    """
    
    def __init__(self, prompts: dict = None, sio=None, sala: str = None, room_session_id: int = None, config_multiagente=None):
        super().__init__(sio, sala, room_session_id)
        
        # Pipeline sin IA - sin agentes, solo conversación de usuarios
        # Los prompts no se necesitan ya que no hay agentes
        self.pipeLine = NoIaPipeline()
        self.pipeLine.sala_name = sala

    async def agregarMensage(self, userName, message, user_message_id):
        """
        Procesa un mensaje del usuario.
        Sin IA, simplemente lo pasa al pipeline para que lo registre.
        
        Args:
            userName: Nombre del usuario
            message: Contenido del mensaje
            user_message_id: ID del mensaje en la DB
            
        Returns:
            None (sin respuestas de IA)
        """
        self.hubo_mensaje_desde_ultimo_callback = True
        
        # Pasar mensaje al pipeline para registrarlo
        # El pipeline no devuelve nada (sin IA)
        await self.pipeLine.entrar_mensaje_a_la_sala(username=userName, mensaje=message)
        
        # Sin respuestas de IA, retorna None
        return None
