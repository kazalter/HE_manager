export const pawchiveCreatorKey = (creator: { service: string; creator_id: string }) => `${creator.service}:${creator.creator_id}`

export function parsePawchiveCreator(value: string): { service: string; creatorId: string } | null {
  const text = value.trim()
  const url = text.match(/^https?:\/\/(?:www\.)?pawchive\.pw\/([A-Za-z0-9_-]{1,100})\/user\/([A-Za-z0-9_-]{1,100})(?:[/?#]|$)/i)
  const id = text.match(/^([A-Za-z0-9_-]{1,100})\s*\/\s*([A-Za-z0-9_-]{1,100})$/)
  const match = url || id
  return match ? { service: match[1], creatorId: match[2] } : null
}
