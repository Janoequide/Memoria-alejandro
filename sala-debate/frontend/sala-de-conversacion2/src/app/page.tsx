'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'


export default function HomePage() {
  const router = useRouter()

  const entrarACrearSala = () => {
    router.push('/elegirChat')
  }

  const entrarAUnirSala = () => {
    router.push('/join-room')
  }

  return (
    <>
      <div className="container" id="container">
        <div className="form-container sign-in-container">
          <form>
            <h1>Sala de Debate</h1>
            <p>¿Qué deseas hacer?</p>
            <button
              type="button"
              onClick={entrarACrearSala}
              className="w-full px-4 py-2 mb-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Crear Sala
            </button>
            <button
              type="button"
              onClick={entrarAUnirSala}
              className="w-full px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
            >
              Entrar a Sala
            </button>
          </form>
        </div>

        <div className="overlay-container">
          <div className="overlay">
            <div className="overlay-panel overlay-left">
              <button className="ghost" id="signIn">Sign In</button>
            </div>
            <div className="overlay-panel overlay-right">
              <h1>¡Hola, explorador ético!</h1>
              <p>
                Forma parte de conversaciones en salas de chat en las 
                que tus argumentos son examinados por un sistema multiagente 
                orientado al análisis y la evaluación de discusiones éticas.
              </p>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
