'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

interface RoomInfo {
  room_name: string
  session_id: string
  participants_count: number
}

export default function JoinRoomPage() {
  const router = useRouter()
  const backend = process.env.NEXT_PUBLIC_BACKEND_URL
  
  const [username, setUsername] = useState('')
  const [openRooms, setOpenRooms] = useState<RoomInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [joining, setJoining] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Obtener lista de salas abiertas al cargar
  useEffect(() => {
    const fetchRooms = async () => {
      try {
        setLoading(true)
        const res = await fetch(`${backend}/api/rooms/participants/count`)
        
        if (!res.ok) {
          setOpenRooms([])
          setLoading(false)
          return
        }

        const data = await res.json()
        setOpenRooms(data.rooms || [])
      } catch (err) {
        console.error('Error fetching rooms:', err)
        setOpenRooms([])
      } finally {
        setLoading(false)
      }
    }

    fetchRooms()
  }, [backend])

  const handleAutoJoin = async () => {
    if (!username.trim()) {
      setError('Por favor, ingresa tu nombre')
      return
    }

    try {
      setJoining(true)
      setError(null)

      // Llamar endpoint auto-join
      const res = await fetch(`${backend}/api/rooms/auto-join`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: username.trim(),
          user_id: null,
        }),
      })

      if (!res.ok) {
        try {
          const errData = await res.json()
          const errorMsg = typeof errData === 'string' 
            ? errData 
            : errData?.detail || errData?.message || 'Error desconocido'
          setError(String(errorMsg))
        } catch {
          setError(`Error ${res.status}: No se pudo conectar al servidor`)
        }
        setJoining(false)
        return
      }

      const data = await res.json()
      
      // Guardar información de la sala en sessionStorage
      sessionStorage.setItem(
        'chatUser',
        JSON.stringify({
          room: data.room_name,
          username: username.trim(),
        })
      )

      // Redirigir directamente al chat (no al lobby)
      router.push(`/chat/${data.room_name}`)
    } catch (err) {
      console.error('Error joining room:', err)
      setError('Error al unirse a la sala')
      setJoining(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-blue-100 p-4">
      <div className="bg-white rounded-lg shadow-lg p-8 max-w-md w-full">
        <h1 className="text-3xl font-bold text-center mb-2 text-blue-600">
          Entrar a una Sala
        </h1>
        <p className="text-center text-gray-600 mb-6">
          Únete automáticamente a la sala con menos participantes
        </p>

        {loading ? (
          <div className="text-center py-8">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <p className="text-gray-600 mt-4">Cargando salas disponibles...</p>
          </div>
        ) : openRooms.length === 0 ? (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6 text-center">
            <p className="text-red-700 font-semibold">No hay salas disponibles</p>
            <p className="text-red-600 text-sm mt-2">
              Por favor, intenta más tarde o crea una nueva sala.
            </p>
            <button
              onClick={() => router.push('/')}
              className="mt-4 px-4 py-2 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition"
            >
              Volver
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Información de salas abiertas */}
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
              <p className="text-sm font-semibold text-blue-900 mb-2">
                Salas Disponibles:
              </p>
              <ul className="space-y-1">
                {openRooms.map((room) => (
                  <li key={room.room_name} className="text-sm text-blue-800">
                    <span className="font-medium">{room.room_name}</span>
                    {' '}
                    <span className="text-blue-600">
                      ({room.participants_count} participantes)
                    </span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Campo de nombre */}
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-gray-700 mb-2">
                Tu nombre:
              </label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleAutoJoin()}
                placeholder="Ingresa tu nombre"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                disabled={joining}
              />
            </div>

            {/* Mensaje de error */}
            {error && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                <p className="text-red-700 text-sm">{error}</p>
              </div>
            )}

            {/* Botón de entrar */}
            <button
              onClick={handleAutoJoin}
              disabled={joining || !username.trim()}
              className={`w-full py-2 rounded-lg font-semibold transition ${
                joining || !username.trim()
                  ? 'bg-gray-300 text-gray-600 cursor-not-allowed'
                  : 'bg-green-600 text-white hover:bg-green-700'
              }`}
            >
              {joining ? 'Uniéndose...' : 'Entrar a Sala'}
            </button>

            {/* Botón volver */}
            <button
              onClick={() => router.push('/')}
              disabled={joining}
              className="w-full py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition disabled:opacity-50"
            >
              Volver
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
