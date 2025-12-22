# Titulo-Trabajo
Titulo-Trabajo

# Instrucciones de uso
- Front: 
    - `cd sala-debate\frontend\sala-de-conversacion2`
    - `npm i; npm run dev`
- NuevoBack: 
    - Crear .env usando el .env.example
    - `cd sala-debate\nuevoBackend`
    - crear entorno .venv con python3
        - `python3 -m venv .venv`
        - `.venv\Scripts\activate`
        - `pip install -r .\requirements.txt`
    - crear la bd
        - `psql -U postgres -f .\db.sql`
    - `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`