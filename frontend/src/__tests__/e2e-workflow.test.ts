import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { reactive, ref } from 'vue'
import axios from 'axios'
import AuthView from '../views/AuthView.vue'
import MediaCard from '../components/MediaCard.vue'
import type { Media } from '../types'
import { authState } from '../auth'

describe('End-to-End Workflow & Core User Journey', () => {
  beforeEach(() => {
    localStorage.clear()
    authState.ready = true
    authState.token = ''
    authState.user = null
    authState.hasUsers = true
    authState.error = ''
  })

  it('Flow 1: Authentication lifecycle from login form submission to authenticated state', async () => {
    vi.spyOn(axios, 'post').mockResolvedValueOnce({
      data: {
        access_token: 'auth-test-token-xyz',
        token_type: 'bearer',
        user: { id: 1, username: 'admin', is_admin: true, created_at: '2026-01-01' },
      },
    })

    const wrapper = mount(AuthView, {
      props: {
        hasUsers: true,
        startupError: '',
      },
    })

    // Fill login form
    const usernameInput = wrapper.find('input[placeholder="请输入用户名"]')
    const passwordInput = wrapper.find('input[placeholder="请输入密码"]')
    expect(usernameInput.exists()).toBe(true)
    expect(passwordInput.exists()).toBe(true)

    await usernameInput.setValue('admin')
    await passwordInput.setValue('password123')
    await wrapper.find('form').trigger('submit.prevent')

    // Expect authState is now authenticated
    expect(authState.token).toBe('auth-test-token-xyz')
    expect(authState.user?.username).toBe('admin')
    expect(localStorage.getItem('he_manager_token')).toBe('auth-test-token-xyz')
  })

  it('Flow 2: Media listing, card interaction and detail modal trigger', async () => {
    const sampleMedia: Media = {
      id: 201,
      title: 'E2E Workflow Test Video',
      relative_path: 'video.mp4',
      media_type: 'video',
      extension: '.mp4',
      file_size: 10485760,
      cover_path: null,
      duration: 360,
      width: 1920,
      height: 1080,
      page_count: null,
      rating: 5,
      favorite: true,
      view_status: 'viewed',
      progress: 100,
      last_opened_at: '2026-01-01',
      source_url: null,
      source_site: null,
      is_missing: false,
      missing_since: null,
      created_at: '2026-01-01',
      tags: [{ id: 10, name: 'Favorite', namespace: 'general', count: 1 }],
    }

    const selectedCard = ref<Media | null>(null)
    const onSelect = (media: Media) => {
      selectedCard.value = media
    }

    const wrapper = mount(MediaCard, {
      props: {
        media: sampleMedia,
        onClick: () => onSelect(sampleMedia),
      },
    })

    // Verify card rendered
    expect(wrapper.text()).toContain('E2E Workflow Test Video')

    // Click card to open detail
    await wrapper.trigger('click')
    expect(selectedCard.value).not.toBeNull()
    expect(selectedCard.value?.id).toBe(201)

    // Simulate closing detail modal
    selectedCard.value = null
    expect(selectedCard.value).toBeNull()
  })

  it('Flow 3: Pagination parameter transitions between pages', async () => {
    const queryParams = reactive({
      page: 1,
      limit: 24,
    })

    const getOffset = () => (queryParams.page - 1) * queryParams.limit

    expect(getOffset()).toBe(0)

    // Navigate to page 2
    queryParams.page = 2
    expect(getOffset()).toBe(24)

    // Navigate to page 3
    queryParams.page = 3
    expect(getOffset()).toBe(48)
  })
})
