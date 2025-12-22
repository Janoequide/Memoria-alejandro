
import uuid
import os
import enum
from pathlib import Path
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, func, select, JSON
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import declarative_base, relationship, scoped_session, sessionmaker
from sqlalchemy import create_engine, Enum
from dotenv import load_dotenv
from datetime import datetime

# Cargar variables de entorno
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)
DATABASE_URL = os.getenv("DATABASE_URL")

# Configuración de base de datos
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = scoped_session(sessionmaker(bind=engine))
Base = declarative_base()

class SenderType(enum.Enum):
    user = "user"
    agent = "agent"

class UserRole(enum.Enum):
    alumno = "alumno"
    monitor = "monitor"

class SessionStatus(enum.Enum):
    active="active"
    closed="closed"

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# Tabla: room_names (catálogo de nombres)
class RoomName(Base):
    __tablename__ = 'room_names'

    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)

# Tabla: room_sessions
class RoomSession(Base):
    __tablename__ = 'room_sessions'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_name = Column(Text, nullable=False)
    topic = Column(Text, nullable=True)
    status = Column(Enum(SessionStatus), nullable=False, default=SessionStatus.active)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Tema(Base):
    __tablename__ = 'temas'
    id = Column(Integer, primary_key=True)
    titulo = Column(String(255), nullable=False)
    tema_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# Tabla: messages
class Message(Base):
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True)
    room_session_id = Column(UUID(as_uuid=True), ForeignKey('room_sessions.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(Text, nullable=True)
    agent_name = Column(String(50), nullable=True)
    sender_type = Column(Enum(SenderType),nullable=False)
    content = Column(Text, nullable=False)
    parent_message_id = Column(
        Integer,
        ForeignKey('messages.id', ondelete='SET NULL'),
        nullable=True
    )
    used_message_ids = Column(ARRAY(Integer), nullable=True)    
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AgentPrompt(Base):
    __tablename__ = 'agent_prompts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String, nullable=False)
    prompt = Column(Text, nullable=False)
    system_type = Column(String, nullable=True, default= "standard")
    created_at = Column(DateTime, default=datetime.now())


class MultiAgentConfig(Base):
    __tablename__ = 'multiagent_config'
    id = Column(Integer, primary_key=True, autoincrement=True)
    ventana_mensajes = Column(Integer, nullable=False)
    fase_segundos = Column(Integer, nullable=False)
    update_interval = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

#----------------------------- Funciones para los temas -------------------------------------

def insert_tema(titulo:str,tema_text: str) -> int:
    """
    Inserta un nuevo tema en la tabla 'temas'.
    Retorna el ID del tema creado.
    """
    session = Session()
    try:
        nuevo_tema = Tema(titulo=titulo,tema_text=tema_text)
        session.add(nuevo_tema)
        session.commit()
        session.refresh(nuevo_tema)
        return nuevo_tema.id
    except SQLAlchemyError as e:
        session.rollback()
        raise e
    finally:
        session.close()

def get_temas() -> list[dict]:
    """
    Recupera todos los temas de la tabla 'temas', ordenados por fecha de creación.
    """
    session = Session()
    try:
        temas = session.query(Tema).order_by(Tema.created_at.desc()).all()
        return [
            {"id": t.id,"titulo":t.titulo, "tema_text": t.tema_text, "created_at": t.created_at.isoformat()}
            for t in temas
        ]
    finally:
        session.close()
        
def update_tema(tema_id:int, titulo:str=None, tema_text:str=None) -> bool:
    session = Session()
    try:
        tema = session.query(Tema).filter_by(id=tema_id).first()
        if not tema:
            return False
        if titulo:
            tema.titulo = titulo
        if tema_text:
            tema.tema_text = tema_text
        session.commit()
        return True
    finally:
        session.close()

#----------------------------- Funciones para la sala ---------------------------------------
def get_rooms() -> list[dict]:
    'Devuelve todas las salas a las cuales se pueden entrar'
    session = Session()
    try:
        rooms = session.query(RoomName).all()
        rooms_data = [{"id":r.id,"name":r.name} for r in rooms]
        return rooms_data
    finally:
        session.close()
def get_active_room_topic(room_name:str) -> str:
    '''
    Devuelve el tema de la sesion activa de la sala indicada
    Si no existe la sesion activa devuelve none
    '''
    session = Session()
    try:
        active_Session = session.query(RoomSession).filter_by(
            room_name=room_name,
            status=SessionStatus.active
        ).first()
        if active_Session:
            return active_Session.topic
        return None
    finally: 
        session.close()

def get_or_create_Active_room_session(room_name:str, topic:str) -> dict:
    '''
    Devuelve el id de la sesión activa para la sala indicada.
    Si no existe, crea una nueva sesión activa.
    '''
    session = Session()
    try:
        # Buscar sesión activa
        active_session = session.query(RoomSession).filter_by(
            room_name=room_name,
            status=SessionStatus.active
        ).first()

        if active_session:
            print("ya habia sesion activa")
            return {"id":str(active_session.id),"primera_inicializacion":False}  # ya hay una sesión activa
        # No hay sesión activa -> crear una nueva
        nueva_sesion = RoomSession(
            room_name=room_name,
            topic=topic,
            status=SessionStatus.active
        )
        session.add(nueva_sesion)
        session.commit()
        session.refresh(nueva_sesion)
        return {"id":str(nueva_sesion.id),"primera_inicializacion":True}
    
    except SQLAlchemyError as e:
        session.rollback()
        raise e
    finally:
        session.close()

def close_active_room_session(room_name: str) -> dict:
    """
    Busca la sesión activa para una sala y la marca como cerrada.
    Devuelve un dict con información de la sesión cerrada o None si no existe.
    """
    session = Session()
    try:
        active_session = session.query(RoomSession).filter_by(
            room_name=room_name,
            status=SessionStatus.active
        ).first()

        if not active_session:
            return None

        active_session.status = SessionStatus.closed
        session.commit()
        session.refresh(active_session)

        return {
            "id": str(active_session.id),
            "room_name": active_session.room_name,
            "status": active_session.status.value
        }

    except SQLAlchemyError as e:
        session.rollback()
        raise e
    finally:
        session.close()

def get_active_room_session_id(room_name:str) -> str | None:
    """
    Retorna el ID de la sesión activa para una sala dada.
    Si no existe sesión activa, devuelve None.
    """
    session = Session()
    try: 
        active_session = session.query(RoomSession).filter_by(
            room_name=room_name,
            status=SessionStatus.active
        ).first()
        return str(active_session.id) if active_session else None
    finally:
        session.close()

def get_latest_room_statuses() -> list[dict]:
    """
    Devuelve el estado más reciente de cada sala (última sesión creada).
    Retorna una lista de diccionarios con room_name y status.
    """
    session = Session()
    try: 
        subquery = (
            session.query(
                RoomSession.room_name,
                func.max(RoomSession.created_at).label("latest_created")
            )
            .group_by(RoomSession.room_name)
            .subquery()
        )
        # Query principal: unir para recuperar la fila completa
        query = (
            session.query(RoomSession.room_name, RoomSession.status)
            .join(
                subquery,
                (RoomSession.room_name == subquery.c.room_name) &
                (RoomSession.created_at == subquery.c.latest_created)
            )
        )
        results = query.all()
        # Convertir a lista de diccionarios
        return [{"room_name": r.room_name, "status": r.status.value} for r in results]
    finally:
        session.close()
        
def create_room_name(name: str) -> int:
    '''
    Se crea una nueva sala. En la tabla RoomName
    '''
    session = Session()
    try:
        nuevo_nombre = RoomName(name=name)
        session.add(nuevo_nombre)
        session.commit()
        session.refresh(nuevo_nombre)
        return nuevo_nombre.id
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

#----------------------------- Funciones para mensajes --------------------------------------
        
def insert_message(
        room_session_id: str, 
        user_id: str | None, 
        agent_name: str | None, 
        content: str, 
        sender_type:SenderType, 
        parent_message_id: int | None = None,
        used_message_ids: list[int] | None = None ) -> int:
    """
    Inserta un mensaje en la BD.
    - Si sender_type = user => guarda user_id
    - Si sender_type = agent => guarda agent_name
    """
    session = Session()
    try:
        
        nuevo_mensaje = Message(
            room_session_id=room_session_id,
            user_id=user_id if sender_type == SenderType.user else None,
            agent_name=agent_name if sender_type == SenderType.agent else None,
            sender_type=sender_type,
            content=content,
            parent_message_id=parent_message_id,
            used_message_ids=used_message_ids
        )
        session.add(nuevo_mensaje)
        session.commit()
        session.refresh(nuevo_mensaje)
        return nuevo_mensaje.id
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def get_messages_by_room(id_session:str) -> list[dict]:
    '''
    Recupera todos los mensajes de una sala la cual tiene una session activa
    Se pide que la id se recupere desde get_active_room_session_id()
    '''
    session = Session()
    try:
        messages = (
            session.query(Message)
            .filter(Message.room_session_id == id_session)
            .order_by(Message.created_at)
            .all()
        )
        return [
            {
                "username": m.user_id if m.sender_type == SenderType.user else None,
                "agente": m.agent_name if m.sender_type == SenderType.agent else None,
                "content": m.content,
                "timestamp": m.created_at.isoformat()
            }
            for m in messages
        ]
    finally:
        session.close()

#----------------------------- Funciones para IA --------------------------------------
def get_current_prompts():
    """
    Retorna los prompts más recientes para cada agente.
    extrae el prompts de cada agente mas reciente creado
    """
    session = Session()
    try:
        subquery = (
            select(
                AgentPrompt.agent_name,
                func.max(AgentPrompt.created_at).label("latest")
            )
            .group_by(AgentPrompt.agent_name)
            .subquery()
        )

        query = (
            select(AgentPrompt)
            .join(
                subquery,
                (AgentPrompt.agent_name == subquery.c.agent_name) &
                (AgentPrompt.created_at == subquery.c.latest)
            )
        )

        results = session.execute(query).scalars().all()

        # Convertir a dict
        return {p.agent_name: p.prompt for p in results}
    finally:
        session.close()


def create_promt(agent_name:str, prompt_text: str) -> int:
    """
    Crea un nuevo prompt para un agente.
    Retorna el ID del nuevo registro.
    """
    session = Session()
    try:
        new_prompt = AgentPrompt(
            agent_name=agent_name,
            prompt=prompt_text,
            created_at=datetime.now()
        )
        session.add(new_prompt)
        session.commit()
        session.refresh(new_prompt)
        return new_prompt.id
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def get_all_agents_by_pipeline(system_type: str) -> list[str]:
    """
    Retorna lista de agentes que tienen prompts asociados a un pipeline específico.
    """
    session = Session()
    try:
        query = (
            select(AgentPrompt.agent_name)
            .where(AgentPrompt.system_type == system_type)
            .distinct()
        )
        results = session.execute(query).scalars().all()
        return results
    finally:
        session.close()


def get_prompts_by_system(system_type: str):
    """
    Retorna los prompts más recientes por agente según system_type.
    """
    session = Session()
    try:
        subquery = (
            select(
                AgentPrompt.agent_name,
                func.max(AgentPrompt.created_at).label("latest")
            )
            .where(AgentPrompt.system_type == system_type)
            .group_by(AgentPrompt.agent_name)
            .subquery()
        )

        query = (
            select(AgentPrompt)
            .join(
                subquery,
                (AgentPrompt.agent_name == subquery.c.agent_name) &
                (AgentPrompt.created_at == subquery.c.latest)
            )
        )

        results = session.execute(query).scalars().all()
        return {p.agent_name: p.prompt for p in results}
    finally:
        session.close()
def create_prompt_for_system(agent_name: str, prompt_text: str, system_type: str = "standard") -> int:
    """
    Inserta un nuevo prompt en la tabla, asociado a un system_type.
    Retorna el id del nuevo registro.
    """
    session = Session()
    try:
        new_prompt = AgentPrompt(
            agent_name=agent_name,
            prompt=prompt_text,
            system_type=system_type,
            created_at=datetime.now()
        )
        session.add(new_prompt)
        session.commit()
        session.refresh(new_prompt)
        return new_prompt.id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def get_multiagent_config() -> MultiAgentConfig | None:
    """
    Devuelve la fila de configuración actual. 
    Si no existe, devuelve None.
    """
    session = Session()
    try:
        config = session.query(MultiAgentConfig).first()
        return config
    finally:
        session.close()

def update_multiagent_config(
    ventana_mensajes: int,
    fase_segundos: int,
    update_interval: int
) -> MultiAgentConfig:
    """
    Actualiza los valores de la configuración existente.
    Lanza excepción si no existe ninguna fila de configuración.
    Todos los parámetros son obligatorios.
    """
    if None in (ventana_mensajes, fase_segundos, update_interval):
        raise ValueError("Todos los parámetros son obligatorios y no pueden ser None.")

    session = Session()
    try:
        config = session.query(MultiAgentConfig).first()
        if not config:
            raise ValueError("No existe ninguna configuración para actualizar. Usa create_multiagent_config primero.")

        config.ventana_mensajes = ventana_mensajes
        config.fase_segundos = fase_segundos
        config.update_interval = update_interval
        session.commit()
        session.refresh(config)
        return config
    finally:
        session.close()


## Funciones para consulta historia cde sessiones 


# 1) Obtener todos los días donde hubo sesiones
def get_all_session_days_from_db():
    session = Session()
    try:
        query = select(func.date(RoomSession.created_at)).distinct()
        rows = session.execute(query).all()
        return [str(r[0]) for r in rows]
    finally:
        session.close()


# 2) Obtener sesiones de un día
def get_sessions_by_day_from_db(day_str: str):
    session = Session()
    try:
        query = (
            select(RoomSession)
            .where(func.date(RoomSession.created_at) == day_str)
            .order_by(RoomSession.created_at)
        )
        rows = session.execute(query).scalars().all()

        return [
            {
                "id": str(r.id),
                "room_name": r.room_name,
                "topic": r.topic,
                "created_at": r.created_at
            }
            for r in rows
        ]
    finally:
        session.close()


# 3) Obtener mensajes por session_id
def get_messages_by_session_from_db(session_id: UUID):
    session = Session()
    try:
        query = (
            select(Message)
            .where(Message.room_session_id == session_id)
            .order_by(Message.created_at)
        )
        rows = session.execute(query).scalars().all()

        return [
            {
                "content": m.content,
                "user_id": m.user_id,
                "agent_name": m.agent_name,
                "sender_type": m.sender_type.value,
                "created_at": m.created_at
            }
            for m in rows
        ]
    finally:
        session.close()