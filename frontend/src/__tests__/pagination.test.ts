import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import axios from 'axios'
import { useExternalFavoritesPage } from '../composables/useExternalFavoritesPage'

describe('useExternalFavoritesPage composable', () => {
  it('computes totalPages, pageStart and pageEnd correctly', async () => {
    const activeSourceId = ref<number | null>(1)
    const searchQuery = ref('')

    vi.spyOn(axios, 'get').mockResolvedValueOnce({
      data: Array(15).fill({ id: 1, title: 'Item' }),
      headers: { 'x-total-count': '42' },
    })

    const page = useExternalFavoritesPage({
      sourceType: 'wnacg',
      activeSourceId,
      searchQuery,
      pageSize: 15,
    })

    await page.fetchItems(true)

    expect(page.totalItems.value).toBe(42)
    expect(page.totalPages.value).toBe(3)
    expect(page.pageStart.value).toBe(1)
    expect(page.pageEnd.value).toBe(15)

    page.currentPage.value = 3
    expect(page.pageStart.value).toBe(31)
    expect(page.pageEnd.value).toBe(42)
  })

  it('handles empty results safely', async () => {
    const activeSourceId = ref<number | null>(null)
    const searchQuery = ref('no match')

    vi.spyOn(axios, 'get').mockResolvedValueOnce({
      data: [],
      headers: { 'x-total-count': '0' },
    })

    const page = useExternalFavoritesPage({
      sourceType: 'wnacg',
      activeSourceId,
      searchQuery,
      pageSize: 15,
    })

    await page.fetchItems(true)

    expect(page.totalItems.value).toBe(0)
    expect(page.totalPages.value).toBe(1)
    expect(page.pageStart.value).toBe(0)
    expect(page.pageEnd.value).toBe(0)
  })
})
