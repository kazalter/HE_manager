for (const action of ['pause', 'seek', 'fullscreen']) document.getElementById(action).onclick = () => window.heProbe.action(action);
document.getElementById('mode').onchange = (event) => window.heProbe.action('mode', event.target.value);
document.getElementById('menu-toggle').onclick = () => { document.getElementById('menu').hidden = !document.getElementById('menu').hidden; };
document.getElementById('menu-action').onclick = () => window.heProbe.action('menu-input');
document.addEventListener('keydown', (event) => {
  if (event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement) return;
  if (event.key === 'F11') { event.preventDefault(); void window.heProbe.action('fullscreen'); }
  if (event.key === 'Escape') {
    event.preventDefault();
    if (!document.getElementById('menu').hidden) document.getElementById('menu').hidden = true;
    else void window.heProbe.action('exit-fullscreen');
  }
});
setInterval(async () => {
  const state = await window.heProbe.state();
  document.getElementById('state').textContent = state.error || `${state.version} · ${state.hwdec || '等待硬解状态'} · ${state.position.toFixed(2)}s · 渲染 ${state.renderedFrames} / 显示 ${state.displayedFrames} · 在途 ${state.leases}/2`;
}, 200);
