-- 1. Crear el usuario
CREATE USER chat_user WITH PASSWORD 'chat_user_password';

-- 2. Crear la base de datos
CREATE DATABASE chatdb OWNER chat_user;

-- ==========================================
-- 1. CREACIÓN DE TABLAS
-- ==========================================
-- Borrar tablas en orden de dependencia
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS room_sessions CASCADE;
DROP TABLE IF EXISTS agent_prompts CASCADE;
DROP TABLE IF EXISTS multiagent_config CASCADE;
DROP TABLE IF EXISTS room_names CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS temas CASCADE;

-- Borrar el tipo ENUM si existe
DROP TYPE IF EXISTS sendertype;

-- Asegurar que existe la extensión para generar UUIDs (necesaria para la config de tu compañero)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 1. Crear el tipo de dato personalizado para sender_type
CREATE TYPE sendertype AS ENUM ('user', 'agent');

-- 2. Tabla Users (Mantenemos esta igual, ya que no vi la de tu compañero pero es estándar)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('alumno', 'monitor')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabla RoomNames
CREATE TABLE room_names (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL
);

-- 4. Tabla RoomSessions (OJO: Aquí está el cambio del UUID automático)
CREATE TABLE room_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- La BD genera el ID, no Python
    room_name TEXT NOT NULL,
    topic TEXT,
    status VARCHAR(20) DEFAULT 'active', -- Tu compañero no tenía NOT NULL explícito en el dump
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. Tabla Temas (La agregamos porque tu código Python la pide)
CREATE TABLE temas (
    id SERIAL PRIMARY KEY,
    titulo VARCHAR(255) NOT NULL,
    tema_text TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6. Tabla Messages (OJO: Usa el tipo ENUM 'sendertype')
CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    room_session_id UUID REFERENCES room_sessions(id) ON DELETE CASCADE, -- Tu compañero lo tenía nullable
    user_id TEXT,
    agent_name VARCHAR(50),
    sender_type sendertype NOT NULL DEFAULT 'user', -- Uso del ENUM
    content TEXT NOT NULL,
    parent_message_id INTEGER REFERENCES messages(id) ON DELETE SET NULL,
    used_message_ids INTEGER[] DEFAULT '{}', -- Default array vacío
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 7. Tabla AgentPrompts
CREATE TABLE agent_prompts (
    id SERIAL PRIMARY KEY,
    agent_name VARCHAR NOT NULL,
    prompt TEXT NOT NULL,
    system_type VARCHAR(50) NOT NULL DEFAULT 'default', -- Cambio: default 'default'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. Tabla MultiAgentConfig
CREATE TABLE multiagent_config (
    id SERIAL PRIMARY KEY,
    ventana_mensajes INTEGER NOT NULL,
    fase_segundos INTEGER NOT NULL DEFAULT 600, -- Cambio: Default 600
    update_interval INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- 2. POBLADO DE DATOS (SEEDING)
-- ==========================================

-- Poblar room_names
INSERT INTO room_names (name) VALUES 
('Sala-General'),
('Sala-Debate-1'),
('Sala-Debate-2'),
('Sala-de-Pruebas');

-- Poblar agent_prompts
INSERT INTO agent_prompts (agent_name, prompt, system_type) VALUES 
('Validador', 
'placeholder', 
'standard'),

('Orientador', 
'placeholder', 
'standard');

-- Poblar multiagent_config (Solo 1 configuración inicial)
INSERT INTO multiagent_config (ventana_mensajes, fase_segundos, update_interval) VALUES 
(5, 60, 10);

-- ==========================================
-- 3. PERMISOS
-- ==========================================
-- Nota: Si ejecutaste este script logueado como 'chat_user', ya eres dueño de las tablas.
-- Si lo ejecutaste como 'postgres', necesitas correr lo siguiente para que la app funcione:

GRANT CONNECT ON DATABASE chatdb TO chat_user;
GRANT USAGE ON SCHEMA public TO chat_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO chat_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO chat_user;