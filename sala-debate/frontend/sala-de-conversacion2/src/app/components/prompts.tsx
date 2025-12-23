'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthGuard } from '../hooks/useAuthGuard'

export default function PromptsPage() {
  const backend = process.env.NEXT_PUBLIC_BACKEND_URL
  const router = useRouter()

  const [agents, setAgents] = useState<string[]>([]) // lista de agentes
  const [currentIndex, setCurrentIndex] = useState(0) // índice del agente actual
  const [prompts, setPrompts] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [pipelineType, setPipelineType] = useState("standard")



  // Obtener lista de agentes disponibles
  const fetchAgents = async () => {
    try {
      const res = await fetch(`${backend}/api/agents?system_type=${pipelineType}`)


      if (!res.ok) throw new Error('Error al obtener agentes')
      const data = await res.json()
      setAgents(data.agents || []) 
    } catch (error) {
      console.error('Error al cargar agentes:', error)
    }
  }
  const fetchPrompts = async () => {
    try {
      setLoading(true)
      const res = await fetch(`${backend}/api/prompts?pipeline=${pipelineType}`)
      if (!res.ok) throw new Error('Error al obtener prompts')
      const data = await res.json()
      setPrompts(data)
    } catch (error) {
      console.error('Error al cargar prompts:', error)
    } finally {
      setLoading(false)
    }
  }
  

  const handleSavePrompt = async () => {
    if (agents.length === 0) return
    const currentAgent = agents[currentIndex]
    try {
      setSaving(true)
      await fetch(`${backend}/api/prompts`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Pipeline': pipelineType,
        },
        body: JSON.stringify({
          agent_name: currentAgent,
          prompt: prompts[currentAgent],
        }),
      })
      
      await fetchPrompts()
    } catch (error) {
      console.error('Error al guardar prompt:', error)
    } finally {
      setSaving(false)
    }
  }
  useEffect(() => {
    fetchPrompts()
  }, [pipelineType])
  
  useEffect(() => {
    fetchAgents()
    setCurrentIndex(0) 
  }, [pipelineType])
  const currentAgent = agents[currentIndex] || null

  return (
    <div className="p-8 w-full max-w-6xl mx-auto">
      <div className="border rounded-2xl p-6 shadow-lg bg-white min-h-[60vh] flex flex-col">
        <h2 className="text-xl font-semibold mb-4">
          {currentAgent ? `Prompt del agente: ${currentAgent}` : 'Cargando agente...'}
        </h2>
        {loading ? (
          <p>Cargando prompt...</p>
        ) : (
          <textarea
            className="w-full border p-4 rounded-lg min-h-[500px] h-[60vh] text-sm sm:text-base resize-vertical"
            rows={12}
            value={currentAgent ? prompts[currentAgent] || '' : ''}
            onChange={(e) =>
              currentAgent &&
              setPrompts((prev) => ({ ...prev, [currentAgent]: e.target.value }))
            }
          />
        )}
      </div>

      {/* Paginación */}
      <div className="mt-6 flex justify-center gap-2">
        {agents.map((agent, index) => (
          <button
            key={agent}
            onClick={() => setCurrentIndex(index)}
            className={`px-4 py-2 rounded ${
              index === currentIndex
                ? 'bg-blue-600 text-white'
                : 'bg-gray-200 hover:bg-gray-300'
            }`}
          >
            {index + 1}
          </button>
        ))}
      </div>

      {/* Botones inferiores */}
      <div className="mt-6 flex justify-between">
        <button
          onClick={() => router.back()}
          className="bg-gray-300 text-gray-800 px-4 py-2 rounded hover:bg-gray-400 transition"
        >
          ← Volver
        </button>

        <button
          onClick={handleSavePrompt}
          className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 transition"
          disabled={saving}
        >
          {saving ? 'Guardando...' : 'Guardar cambios'}
        </button>
        <div className="flex gap-3 mb-6">
        <button
          onClick={() => setPipelineType("standard")}
          className={`px-4 py-2 rounded-lg border ${
            pipelineType === "standard"
              ? "bg-blue-600 text-white"
              : "bg-gray-200 hover:bg-gray-300"
          }`}
        >
          Standard
        </button>

        <button
          onClick={() => setPipelineType("toulmin")}
          className={`px-4 py-2 rounded-lg border ${
            pipelineType === "toulmin"
              ? "bg-blue-600 text-white"
              : "bg-gray-200 hover:bg-gray-300"
          }`}
        >
          Toulmin
        </button>
      </div>

      </div>
    </div>
  )
}
