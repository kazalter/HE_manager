/**
 * Critically damped springs advanced on animation frames. Each value keeps its
 * velocity, so an animation can be retargeted or interrupted without a jump.
 */
export interface SpringValue { value: number; velocity: number; target: number }

/** Advances one value by `elapsed` ms with natural frequency `omega` (rad/s). */
export function stepSpring(spring: SpringValue, elapsed: number, omega: number) {
  const time = elapsed / 1000
  const offset = spring.value - spring.target
  const coefficient = spring.velocity + omega * offset
  const decay = Math.exp(-omega * time)
  spring.value = spring.target + (offset + coefficient * time) * decay
  spring.velocity = (spring.velocity - omega * coefficient * time) * decay
}

export const springAtRest = (spring: SpringValue, tolerance: number) =>
  Math.abs(spring.value - spring.target) < tolerance && Math.abs(spring.velocity) < tolerance * 10

/** Runs `step` once per frame with the elapsed milliseconds until it returns false. */
export function animateFrames(step: (elapsed: number) => boolean) {
  let previous: number | null = null
  let frame: number | null = requestAnimationFrame(function tick(now) {
    // The first frame only establishes the clock, so a slow first frame cannot jump.
    const elapsed = previous === null ? 0 : Math.min(48, Math.max(0, now - previous))
    previous = now
    frame = step(elapsed) ? requestAnimationFrame(tick) : null
  })
  return () => { if (frame !== null) cancelAnimationFrame(frame); frame = null }
}
