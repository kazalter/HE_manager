;(function () {
  var mode = 'dark'
  var theme = 'midnight'
  try {
    var storedMode = localStorage.getItem('he-manager-color-mode')
    if (storedMode === 'light' || storedMode === 'system') mode = storedMode
    var storedTheme = localStorage.getItem('he-manager-theme')
    if (['midnight', 'sakura', 'forest', 'amber'].indexOf(storedTheme) !== -1) theme = storedTheme
  } catch (_) { /* Keep the existing dark default. */ }
  if (mode === 'system') mode = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  document.documentElement.dataset.colorMode = mode
  document.documentElement.dataset.theme = theme
  document.querySelector('meta[name="color-scheme"]').content = mode
  if (mode === 'light') document.querySelector('meta[name="theme-color"]').content = '#f8f8f9'
})()
