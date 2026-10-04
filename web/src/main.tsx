import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import 'maplibre-gl/dist/maplibre-gl.css'
import './styles.css'
import './game.css'
import './views.css'

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>)
