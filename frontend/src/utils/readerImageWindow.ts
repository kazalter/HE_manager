import { READER_DECODE_CACHE_BYTES } from '../composables/useReaderImageBuffer'

/** Put every visible page first, then prepare both sides in reading direction. */
export function readerImageWindow(
  total: number, first: number, last: number, direction: -1 | 1,
  dimensions: (page: number) => [number, number] | null,
) {
  first = Math.max(0, Math.min(first, total - 1))
  last = Math.max(first, Math.min(last, total - 1))
  const indices = Array.from({ length: last - first + 1 }, (_, offset) => first + offset)
  const visibleCount = indices.length
  const cost = (page: number) => { const size = dimensions(page); return size ? size[0] * size[1] * 4 : 800 * 1200 * 4 }
  let bytes = indices.reduce((sum, page) => sum + cost(page), 0)
  // Always prepare the immediate neighbor on both sides. Beyond that, avoid
  // filling a phone's memory with many full-resolution scans at once.
  for (let distance = 1; distance <= 6; distance++) {
    const neighbors = direction === 1 ? [last + distance, first - distance] : [first - distance, last + distance]
    for (const page of neighbors) {
      if (page < 0 || page >= total) continue
      const nextBytes = cost(page)
      if (distance > 1 && bytes + nextBytes > READER_DECODE_CACHE_BYTES) continue
      indices.push(page); bytes += nextBytes
    }
  }
  return { indices, visibleCount }
}
