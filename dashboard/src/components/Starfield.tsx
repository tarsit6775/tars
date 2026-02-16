import { useEffect, useRef } from 'react'

interface Star {
  x: number
  y: number
  z: number
  size: number
  brightness: number
  color: string
}

interface ShootingStar {
  x: number
  y: number
  vx: number
  vy: number
  life: number
  maxLife: number
  size: number
}

const STAR_COLORS = [
  'rgba(241,245,249,', // white
  'rgba(96,165,250,',  // blue
  'rgba(251,191,36,',  // yellow
  'rgba(251,146,60,',  // orange
  'rgba(139,92,246,',  // purple
  'rgba(6,182,212,',   // cyan
]

export default function Starfield() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const mouseRef = useRef({ x: 0, y: 0 })
  const starsRef = useRef<Star[]>([])
  const shootingStarsRef = useRef<ShootingStar[]>([])
  const frameRef = useRef(0)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let w = window.innerWidth
    let h = window.innerHeight
    canvas.width = w
    canvas.height = h

    // Generate stars
    const count = Math.min(400, Math.floor((w * h) / 4000))
    starsRef.current = Array.from({ length: count }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      z: Math.random() * 3,
      size: Math.random() * 1.8 + 0.3,
      brightness: Math.random(),
      color: STAR_COLORS[Math.floor(Math.random() * STAR_COLORS.length)],
    }))

    const handleResize = () => {
      w = window.innerWidth
      h = window.innerHeight
      canvas.width = w
      canvas.height = h
    }

    const handleMouse = (e: MouseEvent) => {
      mouseRef.current = { x: e.clientX, y: e.clientY }
    }

    window.addEventListener('resize', handleResize)
    window.addEventListener('mousemove', handleMouse)

    let animId: number
    const animate = () => {
      frameRef.current++
      ctx.clearRect(0, 0, w, h)

      // Nebula gradient background
      const grd = ctx.createRadialGradient(w * 0.7, h * 0.3, 0, w * 0.7, h * 0.3, w * 0.6)
      grd.addColorStop(0, 'rgba(109, 40, 217, 0.04)')
      grd.addColorStop(0.5, 'rgba(30, 64, 175, 0.02)')
      grd.addColorStop(1, 'transparent')
      ctx.fillStyle = grd
      ctx.fillRect(0, 0, w, h)

      const grd2 = ctx.createRadialGradient(w * 0.2, h * 0.7, 0, w * 0.2, h * 0.7, w * 0.5)
      grd2.addColorStop(0, 'rgba(14, 116, 144, 0.03)')
      grd2.addColorStop(1, 'transparent')
      ctx.fillStyle = grd2
      ctx.fillRect(0, 0, w, h)

      // Parallax offset
      const mx = (mouseRef.current.x / w - 0.5) * 2
      const my = (mouseRef.current.y / h - 0.5) * 2

      // Draw stars
      for (const star of starsRef.current) {
        const parallax = star.z * 8
        const px = star.x + mx * parallax
        const py = star.y + my * parallax

        // Twinkle
        const twinkle = 0.5 + 0.5 * Math.sin(frameRef.current * 0.02 + star.brightness * 10)
        const alpha = (0.3 + twinkle * 0.7) * (0.4 + star.z * 0.2)

        ctx.beginPath()
        ctx.arc(px, py, star.size * (0.5 + star.z * 0.3), 0, Math.PI * 2)
        ctx.fillStyle = star.color + alpha + ')'
        ctx.fill()

        // Glow for larger stars
        if (star.size > 1.2) {
          ctx.beginPath()
          ctx.arc(px, py, star.size * 2.5, 0, Math.PI * 2)
          ctx.fillStyle = star.color + (alpha * 0.15) + ')'
          ctx.fill()
        }
      }

      // Shooting stars
      if (Math.random() < 0.003) {
        shootingStarsRef.current.push({
          x: Math.random() * w,
          y: Math.random() * h * 0.4,
          vx: (Math.random() - 0.3) * 8,
          vy: Math.random() * 4 + 2,
          life: 0,
          maxLife: 40 + Math.random() * 30,
          size: Math.random() * 1.5 + 0.5,
        })
      }

      shootingStarsRef.current = shootingStarsRef.current.filter(s => {
        s.x += s.vx
        s.y += s.vy
        s.life++
        const progress = s.life / s.maxLife
        const alpha = progress < 0.3 ? progress / 0.3 : 1 - (progress - 0.3) / 0.7

        ctx.beginPath()
        ctx.moveTo(s.x, s.y)
        ctx.lineTo(s.x - s.vx * 6, s.y - s.vy * 6)
        ctx.strokeStyle = `rgba(241,245,249,${alpha * 0.8})`
        ctx.lineWidth = s.size
        ctx.stroke()

        // Glow trail
        ctx.beginPath()
        ctx.moveTo(s.x, s.y)
        ctx.lineTo(s.x - s.vx * 3, s.y - s.vy * 3)
        ctx.strokeStyle = `rgba(6,182,212,${alpha * 0.4})`
        ctx.lineWidth = s.size * 3
        ctx.stroke()

        return s.life < s.maxLife
      })

      animId = requestAnimationFrame(animate)
    }

    // Respect reduced motion
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (!prefersReducedMotion) {
      animate()
    } else {
      // Just draw static stars
      for (const star of starsRef.current) {
        ctx.beginPath()
        ctx.arc(star.x, star.y, star.size, 0, Math.PI * 2)
        ctx.fillStyle = star.color + '0.6)'
        ctx.fill()
      }
    }

    return () => {
      cancelAnimationFrame(animId)
      window.removeEventListener('resize', handleResize)
      window.removeEventListener('mousemove', handleMouse)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 z-0 pointer-events-none"
      style={{ background: 'transparent' }}
    />
  )
}
