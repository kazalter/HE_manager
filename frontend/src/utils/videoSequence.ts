import type { Media } from '../types'

export function nextVideo(
  media: Media[], currentId: number, mode: 'order' | 'shuffle', random = Math.random,
): Media | undefined {
  const videos = media.filter(item => item.media_type === 'video' && !item.is_missing)
  if (mode === 'order') {
    return videos[videos.findIndex(item => item.id === currentId) + 1]
  }
  const candidates = videos.filter(item => item.id !== currentId)
  return candidates.length ? candidates[Math.floor(random() * candidates.length)] : undefined
}
