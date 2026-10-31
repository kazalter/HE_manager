/** Real Home -> MediaDetail -> reader geometry regression. Serve frontend/dist first.
 * HE_READER_BASE_URL=http://127.0.0.1:5180 HE_PLAYWRIGHT_MODULE=/path/to/playwright node scripts/check-mobile-webtoon.cjs
 * BROWSER_EXECUTABLE optionally selects installed Chrome. APIs are fulfilled locally; no account is used.
 */
const { chromium } = require(process.env.HE_PLAYWRIGHT_MODULE || 'playwright')
const assert = require('node:assert/strict')
const base = process.env.HE_READER_BASE_URL || 'http://127.0.0.1:5180'
const count = 60
const image = Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1200"><rect width="800" height="1200" fill="#c7d2df"/><text x="100" y="400" font-size="90">Reader QA</text></svg>')

async function run() {
  const browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_EXECUTABLE ? { executablePath: process.env.BROWSER_EXECUTABLE } : {}) })
  const results = []
  try {
    for (const type of ['image', 'manga']) for (const standalone of [false, true]) {
      const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true })
      const page = await context.newPage()
      const errors = []
      page.on('pageerror', error => errors.push(error.message))
      const items = Array.from({ length: count }, (_, i) => ({ id: i + 1, title: `Reader QA ${i + 1}`, relative_path: `qa-${i}.jpg`,
        media_type: type, extension: type === 'manga' ? '.zip' : '.jpg', file_size: 1000, cover_path: null, duration: null,
        width: 800, height: 1200, page_count: type === 'manga' ? count : null, rating: 0, favorite: false,
        view_status: 'unviewed', progress: 0, last_opened_at: null, source_url: null, source_site: null,
        is_missing: false, missing_since: null, created_at: '2026-10-31', tags: [] }))
      await page.addInitScript(standalone => {
        localStorage.setItem('he_manager_token', 'reader-qa-local-only')
        if (standalone) Object.defineProperty(navigator, 'standalone', { value: true })
      }, standalone)
      await page.route('**/*', async route => {
        const url = new URL(route.request().url()), path = url.pathname
        if (path === '/' || path.startsWith('/assets/') || path === '/theme-init.js' || path === '/version.json') return route.continue()
        if (path === '/auth/status') return route.fulfill({ json: { has_users: true } })
        if (path === '/auth/me') return route.fulfill({ json: { id: 1, username: 'qa', is_active: true, is_admin: false, created_at: '' } })
        if (path === '/media') return route.fulfill({ json: url.searchParams.get('sort') === 'opened' ? [] : items, headers: { 'x-total-count': String(count) } })
        if (/^\/media\/\d+$/.test(path)) return route.fulfill({ json: items[Number(path.split('/').at(-1)) - 1] })
        if (/^\/manga\/\d+\/pages$/.test(path)) return route.fulfill({ json: { total_pages: count, page_dimensions: Array.from({ length: count }, () => [800, 1200]) } })
        if (path.startsWith('/stream/') || /\/manga\/\d+\/page\/\d+/.test(path)) return route.fulfill({ body: image, contentType: 'image/svg+xml' })
        return route.fulfill({ json: [] })
      })
      await page.goto(`${base}/#/type/${type}?media=1`)
      await page.waitForSelector('.he-reader-page img')
      await page.waitForTimeout(300)
      const before = await page.evaluate(() => {
        const content = document.querySelector('.he-webtoon-content')
        window.qaReaderRoot = document.querySelector('.he-manga-reader')
        return { top: content.getBoundingClientRect().top + scrollY, height: content.offsetHeight,
          documentHeight: document.scrollingElement.scrollHeight, library: getComputedStyle(document.querySelector('#app')).display,
          first: document.querySelector('.he-reader-page').getBoundingClientRect().top, scrollY }
      })
      assert(Math.abs(before.top) <= 1, `first page is outside normal flow: ${JSON.stringify({ type, standalone, before })}`)
      assert(Math.abs(before.documentHeight - before.height) <= 1, 'document omits part of the strip')
      assert.equal(before.library, 'none', 'library still participates in reader layout')
      assert.equal(before.scrollY, 0, 'opening the first page scrolled to another page')
      await page.evaluate(() => window.scrollTo(0, 30 * 585))
      await page.waitForTimeout(300)
      const navigated = await page.evaluate(() => ({ same: window.qaReaderRoot === document.querySelector('.he-manga-reader'), hash: location.hash }))
      assert(navigated.same, 'reading progress remounted the reader')
      if (type === 'image') assert(navigated.hash.includes('media=31'), 'document scroll did not update the selected image')
      const cdp = await context.newCDPSession(page)
      const touch = async (type, points) => { await cdp.send('Input.dispatchTouchEvent', { type, touchPoints: points.map(([x, y], i) => ({ x, y, id: i + 1 })) }); await page.waitForTimeout(25) }
      await touch('touchStart', [[145, 400], [245, 400]])
      for (let i = 1; i <= 6; i++) await touch('touchMove', [[145 - i * 7, 400], [245 + i * 7, 400]])
      await touch('touchEnd', [])
      const zoomed = await page.evaluate(() => ({ scale: visualViewport.scale, transform: document.querySelector('.he-webtoon-content').style.transform,
        top: document.querySelector('.he-webtoon-content').getBoundingClientRect().top + scrollY }))
      assert(zoomed.scale > 1.2, 'native pinch did not zoom')
      assert.equal(zoomed.transform, '', 'pinch transformed the whole strip')
      assert(Math.abs(zoomed.top) <= 1, 'pinch/release changed the strip origin')
      await page.getByRole('button', { name: '返回媒体列表', exact: true }).evaluate(button => button.click())
      await page.waitForTimeout(250)
      const closed = await page.evaluate(() => ({ active: document.documentElement.classList.contains('he-webtoon-document'), scale: visualViewport.scale,
        library: getComputedStyle(document.querySelector('#app')).display }))
      assert(!closed.active && Math.abs(closed.scale - 1) < 0.01 && closed.library !== 'none', 'close did not restore the library')
      assert.deepEqual(errors, [])
      results.push({ type, standalone, before, zoomed, closed })
      await context.close()
    }
    console.log(JSON.stringify(results, null, 2))
  } finally { await browser.close() }
}
run().catch(error => { console.error(error); process.exitCode = 1 })
