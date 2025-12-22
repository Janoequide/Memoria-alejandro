import os 
import asyncio
import threading
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS 
from models.models import * 
from models.models import Base, engine
from controllers.auth_controller import auth_bp
from controllers.ChatSocketController import *
from agentsComponents.clases.intermediador import Intermediario
import time

load_dotenv()
app = Flask(__name__)
CORS(app)
app.register_blueprint(auth_bp)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY") 
Base.metadata.create_all(engine)
GLOBAL_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(GLOBAL_LOOP)

# Guardamos las salas activas , room_name -> Intermediario
salas_activas: dict[str, Intermediario] = {}


#Inicializar Sockets
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
# Cargar eventos de sockets
register_sockets(socketio,salas_activas)

@app.route("/api/estado-salas",methods=["GET"])
def get_estado_salas():
    """
    Devuelve el estado más reciente de cada sala.
    Ejemplo de respuesta:
    [
      {"room_name": "Sala_1", "status": "active"},
      {"room_name": "Sala_2", "status": "closed"}
    ]
    """
    try:
        statuses = get_latest_room_statuses()
        return jsonify(statuses), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route("/api/init-topic",methods=["POST"])
def init_topic():
    """
    Se extrae el nombre de la sala y el prompt inicial que en verdad es el tema que se va a discutir en la sala 
    Luego se crea la room_session o si estaba ya activa se devuelve el id. 
    Si se tuvo que crear entonces se tiene que setear la clase del sistema multiagente.
    """
    data =request.json
    room_name = data["room"]
    topic = data["prompt_inicial"]
    idioma = data.get("idioma","español")

    if room_name in salas_activas:
        print("sala ya inicializada")
        return jsonify({"status":"ya_inicializado"}),200
    print("se inicializa la sala")
    room_session = get_or_create_Active_room_session(room_name,topic)
    if(room_session["primera_inicializacion"] == True):
        print(f"id de la sala:{room_session['id']}")
        #Recuperamos los ultimos promts para cada agente
        current_prompts = get_current_prompts()
        prompt_validador = (current_prompts.get("Clasificador","Prompt por defecto del clasificador")).replace("{tema}",topic)
        #prompt_puntuador = (current_prompts.get("Puntuador","Prompt por defecto del puntuador")).replace("{tema}",topic)
        prompt_curador = (current_prompts.get("Curador", "Prompt por defecto del curador")).replace("{tema}",topic)
        prompt_orientador = (current_prompts.get("Orientador", "Prompt por defecto del orientador")).replace("{tema}",topic)
        #print(f"puntuador prompt: {prompt_puntuador}")
        #Recuperamos la configuracion del sistema multiagente 
        configuracion_multiagente = get_multiagent_config()
        tamaño_ventana_mensajes = configuracion_multiagente.ventana_mensajes
        tiempo_fase_1 = configuracion_multiagente.fase_1_segundos 
        tiempo_fase_2 = configuracion_multiagente.fase_2_segundos
        duracion_sesion = tiempo_fase_1 + tiempo_fase_2
        update_interval = configuracion_multiagente.update_interval

        intermediario = Intermediario(
            tamañoVentana=tamaño_ventana_mensajes,
            prompt_agenteValidador=prompt_validador,
            #prompt_agentePuntuador=prompt_puntuador,
            prompt_agenteCurador=prompt_curador,
            prompt_agenteOrientador=prompt_orientador,
            socketIo=socketio,
            sala=room_name,
            emit_callback=lambda evento, resultado, sala: emitir_resultado_socket(socketio,evento,resultado,sala)
            )
        
        usuarios_sala = get_user_list(room_name)
        salas_activas[room_name] = intermediario
        # 🔵 Iniciar sesión async
        asyncio.run_coroutine_threadsafe(
            intermediario.start_session(topic, usuarios_sala, idioma),
            intermediario.loop
        )

        # 🔵 Iniciar worker de mensajes
        intermediario.start_processing()

        # 🔵 Iniciar timer
        intermediario.start_timer(duracion_sesion, update_interval)

        timer_state = intermediario.get_timer_state()

        emitir_resultado_socket(
            socketio,
            "start_session",
            {
                "room": room_name,
                "users": get_user_list(room_name),
            },
            room_name,
        )

        emitir_resultado_socket(
            socketio,
            "timer_user_update",
            {
                "elapsed_time": timer_state["elapsed_time"],
                "remaining_time": timer_state["remaining_time"],
            },
            room_name,
        )
        return jsonify({"status":"initialized"}),201

    if(room_session["primera_inicializacion"] == False):
        print(f"id de la sala ya inicializada:{room_session['id']}")
        return jsonify({"status":"ya_inicializado"}),200

@app.route("/api/close-room", methods=["POST"])
def close_room():
    data = request.json
    room_name = data.get("room")

    if not room_name:
        return jsonify({"error": "Se requiere el nombre de la sala"}), 400

    try:
        result = close_active_room_session(room_name)
        if not result:
            return jsonify({"status": "no_active_session", "message": "No hay sesión activa para esta sala"}), 404

        # Limpiar la instancia en memoria
        if room_name in salas_activas:
            intermediario = salas_activas.get(room_name)
            asyncio.run(intermediario.stop_session())
            del salas_activas[room_name]


        return jsonify({"status": "closed", **result}), 200

    except SQLAlchemyError as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tema/<room>", methods=["GET"])
def obtener_tema(room):
    topic = get_active_room_topic(room)
    if topic is None:
        return jsonify({"tema": "sin tema definido"}), 404
    return jsonify({"tema":topic}), 200

@app.route("/api/temas", methods=["GET","POST","PUT"])
def manejar_temas():
    '''
    GET  -> Consultar todos los temas guardados
    POST -> Crear un nuevo tema # ejemplo {"tema_text": "Nuevo tema de debate"}
    '''
    if request.method == "GET":
        temas = get_temas()
        return jsonify(temas), 200
    
    if request.method == "POST":
        data = request.json  
        titulo = data.get("titulo")
        tema_text = data.get("tema_text")
        if not titulo or not tema_text:
            return jsonify({"error": "Los campos 'titulo' y 'tema_text' son obligatorios"}), 400
        tema_id = insert_tema(titulo, tema_text)
        return jsonify({"status": "success", "id": tema_id}), 201
    
    if request.method == "PUT":
        data = request.json
        tema_id = data.get("id")
        titulo = data.get("titulo")
        tema_text = data.get("tema_text")
        if not tema_id or not titulo or not tema_text:
            return jsonify({"error": "Se requieren los campos 'id', 'titulo' y 'tema_text'"}), 400
        actualizado = update_tema(tema_id, titulo, tema_text)
        if not actualizado:
            return jsonify({"error": "No se encontró el tema con ese ID"}), 404
        return jsonify({"status": "success", "id": tema_id}), 200

@app.route("/api/prompts",methods=["GET","POST"])
def get_prompts():
    '''
    GET  -> Consultar el último prompt de cada agente
    POST -> Actualizar prompt(s) de uno o varios agentes # ejemplo(1) {"Curador": "nuevo prompt", "Orientador": "otro prompt"}
    (2) {"Curador": "nuevo prompt"}

    '''
    if request.method == "GET":
        prompts = get_current_prompts()
        return jsonify(prompts), 200
    
    if request.method == "POST":
        data = request.json  
        created_ids = []
        for agent_name, prompt_text in data.items():
            prompt_id = create_promt(agent_name, prompt_text)
            created_ids.append({"agent": agent_name, "id": prompt_id})
        #el update devuelve la lista de agentes actualizados 
        return jsonify({
            "status": "success", 
            "updated": created_ids}), 201
    

@app.route("/api/prompt-template/<agent_name>", methods=["GET"])
def api_get_template(agent_name):
    """
    Endpoint: Retorna el template completo de un agente en formato JSON.
    Si no existe, retorna error 404.
    """
    try:
        template = get_agent_template(agent_name)
        return jsonify(template), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    
@app.route("/api/prompt-template", methods=["POST"])
def api_create_template():
    data = request.json
    agent_name = data.get("agent_name")

    if not agent_name:
        return jsonify({"error": "agent_name is required"}), 400


    try:
        template = create_agent_template(agent_name)
        return jsonify({"status": "created", "agent_name": template.agent_name}), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

@app.route("/api/prompt-template/<agent_name>", methods=["PUT"])
def api_update_template(agent_name):
    data = request.json

    if not isinstance(data, dict):
        return jsonify({"error": "Invalid payload"}), 400
    try:
        updated_prompt = update_agent_layers(agent_name, data)
        return jsonify({"status": "updated", "prompt": updated_prompt}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

@app.route("/api/prompt/<agent_name>", methods=["GET"])
def api_get_final_prompt(agent_name):

    try:
        prompts = get_current_prompts()
        return jsonify({
            "agent_name": agent_name,
            "prompt": prompts.get(agent_name)
        }), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

@app.route("/api/cuantosagentes", methods=["GET"])
def get_agents():
    """
    Endpoint: Retorna la lista de nombres únicos de agentes registrados.
    """
    agents = get_all_agents()
    return jsonify({"agents": agents}), 200

@app.route("/api/rooms",methods=["GET","POST"])
def get_salas():
    '''
    GET  -> Devuelve las salas a las cuales los usuarios pueden conectarse a chatear
    POST -> Crea una nueva sala  
    '''
    if request.method == "GET":
        rooms = get_rooms()
        return jsonify(rooms), 200
    if request.method == "POST":
        data = request.json 
        room_id = create_room_name(data["nombre_sala"])
        return jsonify({"id":room_id,"nombre":data["nombre_sala"]}),201

@app.route("/api/room-messages/<room_name>",methods=["GET"])
def get_room_messages(room_name):
    #recuperamos el id de la sesion activa
    id_session = get_active_room_session_id(room_name)
    if not id_session:
        return jsonify({"error":"No hay sesion activa"}) , 404

    messages = get_messages_by_room(id_session)
    return jsonify(messages), 200 



@app.route("/api/multiagent-config", methods=["GET", "POST"])
def multiagent_config():
    
    if request.method == "GET":
        config = get_multiagent_config()
        if not config:
            return jsonify({"error": "No configuration found"}), 404
        return jsonify({
            "ventana_mensajes": config.ventana_mensajes,
            "fase_1_segundos": config.fase_1_segundos,
            "fase_2_segundos": config.fase_2_segundos,
            "update_interval": config.update_interval,
            "created_at": config.created_at.isoformat()
        }), 200

    if request.method == "POST":
        # Validar campos obligatorios
        try:
            data = request.json 
            ventana_mensajes = data["ventana_mensajes"]
            fase_1_segundos = data["fase_1_segundos"]
            fase_2_segundos = data["fase_2_segundos"]
            update_interval = data["update_interval"]
            print(ventana_mensajes)
            print(fase_1_segundos)
            print(fase_2_segundos)
            print(update_interval)

        except (TypeError, KeyError):
            return jsonify({"error": "Missing required fields"}), 400

        config = get_multiagent_config()
        if config is None:
            # Crear configuración nueva
            result = create_multiagent_config(
                ventana_mensajes=ventana_mensajes,
                fase_1_segundos=fase_1_segundos,
                fase_2_segundos=fase_2_segundos,
                update_interval=update_interval
            )
            return jsonify({
                "ventana_mensajes": result.ventana_mensajes,
                "fase_1_segundos": result.fase_1_segundos,
                "fase_2_segundos": result.fase_2_segundos,
                "update_interval": result.update_interval,
                "created_at": result.created_at.isoformat()
            }), 201

        # Actualizar configuración existente
        result = update_multiagent_config(
            ventana_mensajes=ventana_mensajes,
            fase_1_segundos=fase_1_segundos,
            fase_2_segundos=fase_2_segundos,
            update_interval=update_interval
        )
        return jsonify({
            "ventana_mensajes": result.ventana_mensajes,
            "fase_1_segundos": result.fase_1_segundos,
            "fase_2_segundos": result.fase_2_segundos,
            "update_interval": result.update_interval,
            "created_at": result.created_at.isoformat()
        }), 200


if __name__ == "__main__":
    #app.run(debug=True)
    #socketio.run(app, debug=True, host='0.0.0.0', port=5000)
    socketio.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 5000)),
        debug=True,
        use_reloader=True
    )


