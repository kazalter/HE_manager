/**
 * Full-roster two-layer L2D audit:
 *   Layer 1 (static): model3/HitAreas/fades/defaults/interaction/l2d schema, trigger types, relation types, motion refs.
 *   Layer 2 (engine): Real Cubism Core + InteractionRuntime + DragOrchestrator traversal of HitAreas, zones, drags, gyro, and reset.
 *
 * Usage:
 *   node tests/audit_roster.mjs [--root /mnt/hdd/azurlane-l2dviewer/models] [--skin <id>] [--workers 4] [--strict]
 */
import fs from 'node:fs'
import path from 'node:path'
import { spawn } from 'node:child_process'
import { createTestClock } from './helpers/clock.mjs'
import { cubismCoreAvailable, loadCubismCore } from './helpers/cubism.mjs'
import { stubLocalStorage } from './helpers/fakes.mjs'

stubLocalStorage()

const KNOWN_TRIGGERS = new Set([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16])
const KNOWN_RELATIONS = new Set([101, 102, 103, 104])

function parseArgs(argv) {
  const args = { root: '/mnt/hdd/azurlane-l2dviewer/models', skin: null, strict: false, workers: 4, shard: null, json: false }
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--root' && argv[i + 1]) args.root = argv[++i]
    else if (argv[i] === '--skin' && argv[i + 1]) args.skin = argv[++i]
    else if (argv[i] === '--strict') args.strict = true
    else if (argv[i] === '--workers' && argv[i + 1]) args.workers = Math.max(1, Number(argv[++i]) || 1)
    else if (argv[i] === '--shard' && argv[i + 1]) args.shard = argv[++i]
    else if (argv[i] === '--json') args.json = true
  }
  return args
}

function discoverSkins(root) {
  const skins = []
  const unreadable = []
  function walk(dir) {
    let entries
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true })
    } catch (err) {
      if (err?.code === 'EACCES' || err?.code === 'EPERM') {
        unreadable.push(path.relative(root, dir))
        return
      }
      throw err
    }
    const modelFile = entries.find((e) => e.isFile() && e.name.endsWith('.model3.json'))
    if (modelFile) {
      skins.push({ skin: modelFile.name.slice(0, -'.model3.json'.length), dir, modelFile: modelFile.name })
      return
    }
    for (const e of entries) {
      if (e.isDirectory()) walk(path.join(dir, e.name))
    }
  }
  walk(root)
  skins.sort((a, b) => a.skin.localeCompare(b.skin))
  return { skins, unreadable }
}

function normalizeZone(name) {
  return String(name || '').toLowerCase().replace(/[^a-z0-9]/g, '')
}

function collectMotionClips(model3Json) {
  const clipToFiles = new Map()
  const motions = model3Json?.FileReferences?.Motions ?? {}
  for (const defs of Object.values(motions)) {
    for (const d of defs ?? []) {
      const f = d?.File
      if (!f) continue
      const clip = path.posix.basename(f).replace(/\.motion3\.json$/, '')
      clipToFiles.set(clip, f)
    }
  }
  return clipToFiles
}

function auditLayer1(item) {
  const { skin, dir, modelFile } = item
  const errors = []
  const warnings = []
  const modelPath = path.join(dir, modelFile)
  let m3
  try {
    m3 = JSON.parse(fs.readFileSync(modelPath, 'utf8'))
  } catch (err) {
    errors.push(`invalid model3.json: ${err.message}`)
    return { errors, warnings, m3: null, l2d: null, interaction: null, fades: null }
  }
  const refs = m3.FileReferences ?? {}
  if (!refs.Moc || !fs.existsSync(path.join(dir, refs.Moc))) errors.push(`missing moc3: ${refs.Moc}`)
  if (refs.Physics && !fs.existsSync(path.join(dir, refs.Physics))) errors.push(`missing physics3: ${refs.Physics}`)
  for (const tex of refs.Textures ?? []) {
    if (!fs.existsSync(path.join(dir, tex))) errors.push(`missing texture: ${tex}`)
  }
  const clipFiles = collectMotionClips(m3)
  for (const [clip, rel] of clipFiles) {
    if (!fs.existsSync(path.join(dir, rel))) errors.push(`missing motion file ${clip}: ${rel}`)
  }

  let fades = null
  const fadesPath = path.join(dir, `${skin}.fades.json`)
  if (fs.existsSync(fadesPath)) {
    try { fades = JSON.parse(fs.readFileSync(fadesPath, 'utf8')) } catch (err) { errors.push(`invalid fades.json: ${err.message}`) }
  }

  const defaultsPath = path.join(dir, `${skin}.defaults.json`)
  if (fs.existsSync(defaultsPath)) {
    try { JSON.parse(fs.readFileSync(defaultsPath, 'utf8')) } catch (err) { errors.push(`invalid defaults.json: ${err.message}`) }
  }

  let interaction = null
  const interPath = path.join(dir, `${skin}.interaction.json`)
  if (fs.existsSync(interPath)) {
    try {
      interaction = JSON.parse(fs.readFileSync(interPath, 'utf8'))
      for (const clip of Object.keys(interaction.clips ?? {})) {
        if (!clipFiles.has(clip)) warnings.push(`interaction clip not in motions: ${clip}`)
      }
    } catch (err) {
      errors.push(`invalid interaction.json: ${err.message}`)
    }
  }

  let l2d = null
  const l2dPath = path.join(dir, `${skin}.l2d.json`)
  if (fs.existsSync(l2dPath)) {
    try {
      l2d = JSON.parse(fs.readFileSync(l2dPath, 'utf8'))
    } catch (err) {
      errors.push(`invalid l2d.json: ${err.message}`)
      return { errors, warnings, m3, l2d: null, interaction, fades }
    }
    const idleGroupClips = new Set(
      (refs.Motions?.idle ?? []).map((d) => path.posix.basename(d.File ?? '').replace(/\.motion3\.json$/, '')),
    )
    for (const [idx, clip] of Object.entries(l2d.idle_index ?? {})) {
      if (clip && !idleGroupClips.has(clip)) {
        warnings.push(`idle_index[${idx}]='${clip}' missing from idle group`)
      }
    }
    const hitAreaZones = new Set((m3.HitAreas ?? []).map((h) => normalizeZone(h.Name)))
    for (const e of l2d.entries ?? []) {
      const at = e.action_trigger
      if (at && typeof at === 'object' && 'type' in at) {
        if (!KNOWN_TRIGGERS.has(at.type)) errors.push(`entry ${e.id}: unsupported trigger type ${at.type}`)
        const checkAction = (act) => {
          if (!act || act === 'idle') return
          const list = Array.isArray(act) ? act : [act]
          for (const a of list) {
            if (a && a !== 'idle' && !clipFiles.has(a)) {
              warnings.push(`entry ${e.id}: action '${a}' not in model motions`)
            }
          }
        }
        checkAction(at.action)
        for (const al of at.action_list ?? []) checkAction(al?.action)
      }
      for (const r of e.relation_parameter?.list ?? []) {
        if (!KNOWN_RELATIONS.has(r.type)) errors.push(`entry ${e.id}: unsupported relation type ${r.type}`)
      }
      if (e.draw_able_name && !hitAreaZones.has(normalizeZone(e.draw_able_name))) {
        warnings.push(`zone_missing_hitarea:${e.draw_able_name}:${e.id}`)
      }
    }
  }

  return { errors, warnings, m3, l2d, interaction, fades }
}

const hasCore = cubismCoreAvailable()
let InteractionRuntime
let createActions
let installMotionPatches
let CubismFramework
let CubismMoc
let Cubism4ModelSettings
let Cubism4InternalModel
let frameworkReady = false
if (hasCore) {
  await loadCubismCore()
  ;({ CubismFramework, CubismMoc, Cubism4ModelSettings, Cubism4InternalModel } = await import('pixi-live2d-display/cubism4'))
  ;({ InteractionRuntime } = await import('../src/utils/interaction/runtime.js'))
  ;({ createActions } = await import('../src/l2d/actions.js'))
  ;({ installMotionPatches } = await import('../src/l2d/motionPatches.js'))
  installMotionPatches({ fades: { default: 0.3 } })
}
const { DragOrchestrator } = await import('../src/utils/dragmachine/orchestrator.js')

function ensureFramework() {
  if (!frameworkReady) {
    CubismFramework.startUp()
    CubismFramework.initialize()
    frameworkReady = true
  }
}

const origWarn = console.warn
const origLog = console.log
let activeWarnList = null

function buildClipMetaMap(dir, m3) {
  const metaMap = new Map()
  const motions = m3?.FileReferences?.Motions ?? {}
  for (const defs of Object.values(motions)) {
    for (const d of defs ?? []) {
      if (!d?.File) continue
      const clip = path.posix.basename(d.File).replace(/\.motion3\.json$/, '')
      if (metaMap.has(clip)) continue
      try {
        const j = JSON.parse(fs.readFileSync(path.join(dir, d.File), 'utf8'))
        metaMap.set(clip, { duration: j?.Meta?.Duration ?? 2, loop: Boolean(j?.Meta?.Loop) })
      } catch {
        metaMap.set(clip, { duration: 2, loop: false })
      }
    }
  }
  return metaMap
}

async function auditLayer2(item, { m3, l2d, interaction, fades }) {
  const { skin, dir, modelFile } = item
  const errors = []
  const notes = []
  const clock = createTestClock(1).install()
  let internal = null
  let moc = null
  const flush = async () => {
    await Promise.resolve()
    await Promise.resolve()
  }

  const checkNoNaN = (phase, coreModel) => {
    const count = coreModel.getParameterCount()
    for (let i = 0; i < count; i++) {
      const v = coreModel.getParameterValueByIndex(i)
      if (!Number.isFinite(v)) {
        errors.push(`${phase}: non-finite parameter idx=${i} (${v})`)
        return false
      }
    }
    return true
  }

  try {
    ensureFramework()
    const settingsJson = JSON.parse(fs.readFileSync(path.join(dir, modelFile), 'utf8'))
    settingsJson.url = dir + '/'
    const settings = new Cubism4ModelSettings(settingsJson)
    const mocBuf = fs.readFileSync(path.join(dir, settings.moc ?? settings.FileReferences.Moc))
    const ab = mocBuf.buffer.slice(mocBuf.byteOffset, mocBuf.byteOffset + mocBuf.byteLength)
    moc = CubismMoc.create(ab)
    const coreModel = moc.createModel()
    internal = new Cubism4InternalModel(coreModel, settings)
    internal.motionManager._loadMotion = (group, index) => {
      const def = internal.motionManager.definitions[group]?.[index]
      const data = JSON.parse(fs.readFileSync(path.join(dir, def.File), 'utf8'))
      return internal.motionManager.createMotion(data, group, def)
    }
    internal.motionManager.groups.idle = 'idle'
    const clipMeta = buildClipMetaMap(dir, m3)

    const model = {
      elapsedTime: 0,
      internalModel: internal,
      toGlobal: (p) => p,
      motion: (g, i, p) => internal.motionManager.startMotion(g, i, p),
    }
    const ctx = { model, currentMotion: { value: '' }, fades: fades ?? { default: 0.3 }, _mounting: false }
    installMotionPatches(ctx)
    const runtime = new InteractionRuntime(model, interaction)
    ctx.runtime = runtime
    const actions = createActions(ctx)
    ctx.actions = actions

    let orch = null
    if (l2d) {
      orch = new DragOrchestrator(model, l2d, actions.playLuaAction)
      ctx.orch = orch
      orch.clipDurationOf = (clip) => interaction?.clips?.[clip]?.duration ?? clipMeta.get(clip)?.duration ?? 2
      orch.resetAll()
      runtime.checkEnable = (clip) => orch.checkEnablePlay(clip)
      internal.motionManager.on('motionStart', (g, i) => orch.noteMotionStart(runtime.clipOf(g, i), g === 'idle'))
      internal.motionManager.on('motionFinish', () => orch.noteMotionFinish())
      internal.on('beforeMotionUpdate', () => orch.restoreLayer(coreModel))
      internal.on('afterMotionUpdate', () => orch.applyLayer(coreModel))
    }

    internal.on('beforeMotionUpdate', () => runtime.applySmoothReset())
    runtime.resetParameters()
    runtime.setFixedParam('Paramring', 0)
    runtime.setFixedParam('l2d_hx', /_hx$/i.test(skin) ? 1 : 0)

    const advance = async (sec, hz = 30) => {
      const dt = 1 / hz
      const frames = Math.max(1, Math.round(sec * hz))
      for (let f = 0; f < frames; f++) {
        const nowMs = clock.advance(dt) * 1000
        model.elapsedTime = nowMs
        runtime.syncPlayingState?.()
        orch?.step(dt)
        internal.update(dt * 1000, nowMs)
        await flush()
      }
    }

    const drainPlaying = async (phase) => {
      if (!orch) return
      let waited = 0
      while (orch.isPlaying) {
        const meta = clipMeta.get(orch.playActionName)
        const cap = Math.max(4, (meta?.duration ?? 5) + 2)
        if (meta?.loop) {
          errors.push(`${phase}: non-idle looping reaction '${orch.playActionName}' loop locks isPlaying`)
          break
        }
        if (waited >= cap) {
          errors.push(`${phase}: isPlaying stuck on '${orch.playActionName}' after ${waited.toFixed(1)}s (dur=${meta?.duration ?? '?'})`)
          break
        }
        await advance(0.25, 12)
        waited += 0.25
      }
    }

    // Boot idle
    if (orch) {
      await actions.playLuaAction(orch.idleClipFor(0))
    } else if (m3?.FileReferences?.Motions?.idle?.length) {
      await model.motion('idle', 0, 3)
    }
    await advance(0.4, 30)
    checkNoNaN('boot_idle', coreModel)
    if (orch) {
      if (orch.machineAble) errors.push('boot_idle: machineAble leaked true')
      if (orch.isPlaying) errors.push(`boot_idle: isPlaying stuck on ${orch.playActionName}`)
      const rawModel = coreModel.getModel()
      const drawableIds = new Set(Array.from({ length: rawModel.drawables.count }, (_, idx) => normalizeZone(rawModel.drawables.ids[idx])))
      const hitAreaSet = new Set((m3?.HitAreas ?? []).map((h) => normalizeZone(h.Name)))
      for (const m of orch.machines) {
        const nz = normalizeZone(m.drawAbleName)
        if (nz && !hitAreaSet.has(nz) && drawableIds.has(nz)) {
          errors.push(`entry ${m.id}: drawable '${m.drawAbleName}' exists in moc3 but missing from HitAreas`)
        }
      }
    }

    // Probe standard HitAreas (touch_head / touch_body / touch_special) if non-machine
    for (const hitName of ['touch_head', 'touch_body', 'touch_special']) {
      if (internal.hitAreas?.[hitName] && (!orch || orch.zoneOrder(hitName) < 0)) {
        actions.handleHitAreas([hitName])
        await advance(0.2, 30)
        await drainPlaying(`hit(${hitName})`)
        checkNoNaN(`hit(${hitName})`, coreModel)
      }
    }

    if (orch) {
      for (const pid of Object.keys(orch.paraRange ?? {})) {
        if (orch.paramIndex(pid) < 0) notes.push(`l2d_para_range missing param: ${pid}`)
      }

      const zones = []
      const seen = new Set()
      for (const m of orch.machines) {
        const k = normalizeZone(m.drawAbleName)
        if (k && !seen.has(k)) {
          seen.add(k)
          zones.push(m.drawAbleName)
        }
      }

      for (const zone of zones) {
        orch.onDown(zone, { x: 0, y: 0 }, { x: 500, y: 500 })
        await advance(0.06, 30)
        orch.onUp(zone, { x: 0, y: 0 })
        await advance(0.2, 30)
        await drainPlaying(`tap(${zone})`)
        if (!checkNoNaN(`tap(${zone})`, coreModel)) break
        if (orch.machineAble) {
          errors.push(`tap(${zone}): machineAble leaked true`)
          break
        }

        orch.onDown(zone, { x: 0, y: 0 }, { x: 500, y: 500 })
        orch.onMove({ x: 180, y: -180 }, { x: 600, y: 400 })
        await advance(0.25, 30)
        orch.onMove({ x: -180, y: 180 }, { x: 420, y: 550 })
        await advance(0.25, 30)
        orch.onUp(zone, { x: -180, y: 180 })
        await advance(0.2, 30)
        await drainPlaying(`drag(${zone})`)
        if (!checkNoNaN(`drag(${zone})`, coreModel)) break
        if (orch.machineAble) {
          errors.push(`drag(${zone}): machineAble leaked true`)
          break
        }
      }

      if (orch.hasGyro) {
        orch.setGyro(true, { x: 0.1, y: -0.1, z: 0.05 })
        await advance(0.2, 20)
        checkNoNaN('gyro_on', coreModel)
        orch.setGyro(false)
        await advance(0.2, 20)
        checkNoNaN('gyro_off', coreModel)
      }

      actions.resetInteraction()
      await advance(0.5, 20)
      checkNoNaN('resetInteraction', coreModel)
      if (orch.idleIndex !== 0) errors.push(`resetInteraction: idleIndex=${orch.idleIndex} != 0`)
      if (orch.machineAble) errors.push('resetInteraction: machineAble leaked true')
      if (orch.isPlaying) errors.push(`resetInteraction: isPlaying leaked on ${orch.playActionName}`)
      if (orch.enablePlayActions.length) errors.push(`resetInteraction: whitelist not cleared (${orch.enablePlayActions.length})`)
    }
  } catch (err) {
    errors.push(`exception: ${err?.stack || err}`)
  } finally {
    clock.restore()
    internal?.destroy?.()
    moc?._moc?.release?.()
  }
  return { errors, notes }
}

async function runParentWorkers(opts) {
  const { skins, unreadable } = discoverSkins(opts.root)
  const wCount = Math.min(opts.workers, Math.max(1, skins.length))
  console.log(`Discovered ${skins.length} readable skins across ${wCount} workers (unreadable dirs skipped: ${unreadable.length}: ${unreadable.join(', ') || 'none'})`)
  const promises = []
  for (let w = 0; w < wCount; w++) {
    promises.push(new Promise((resolve, reject) => {
      const childArgs = [process.argv[1], '--root', opts.root, '--shard', `${w}/${wCount}`, '--json']
      const p = spawn(process.execPath, childArgs, { stdio: ['ignore', 'pipe', 'pipe'] })
      let out = ''
      let err = ''
      p.stdout.on('data', (c) => { out += c })
      p.stderr.on('data', (c) => { err += c })
      p.on('close', (code) => {
        const marker = '__AUDIT_JSON__'
        const idx = out.lastIndexOf(marker)
        if (idx >= 0) {
          resolve(JSON.parse(out.slice(idx + marker.length).trim()))
        } else {
          reject(new Error(`Worker ${w} exited ${code}: ${err || out}`))
        }
      })
    }))
  }
  const results = await Promise.all(promises)
  const failSkins = results.flatMap((r) => r.failSkins)
  const warnSummary = results.flatMap((r) => r.warnSummary)
  const noteSummary = results.flatMap((r) => r.noteSummary)
  const l2dCount = results.reduce((s, r) => s + r.l2dCount, 0)
  const audited = results.reduce((s, r) => s + r.audited, 0)
  console.log(`\n=== Audit Summary ===`)
  console.log(`Skins audited: ${audited} (L2D configs: ${l2dCount}, skipped unreadable: ${unreadable.length})`)
  console.log(`Failures: ${failSkins.length}`)
  for (const f of failSkins) console.log(`  [FAIL] ${f.skin}: ${f.errors.join(' | ')}`)
  console.log(`Skins with L1/runtime warnings: ${warnSummary.length}`)
  for (const w of warnSummary.slice(0, 30)) {
    console.log(`  [WARN] ${w.skin}: ${w.warnings.slice(0, 4).join(' ; ')}${w.warnings.length > 4 ? ` (+${w.warnings.length - 4})` : ''}`)
  }
  console.log(`Skins with L2 notes: ${noteSummary.length}`)
  for (const n of noteSummary.slice(0, 20)) {
    console.log(`  [NOTE] ${n.skin}: ${n.notes.slice(0, 3).join(' ; ')}`)
  }
  if (failSkins.length || (opts.strict && warnSummary.length)) process.exit(1)
}

const opts = parseArgs(process.argv.slice(2))
if (!fs.existsSync(opts.root)) {
  console.error(`Models root not found: ${opts.root}`)
  process.exit(2)
}

if (!opts.skin && !opts.shard && opts.workers > 1) {
  await runParentWorkers(opts)
} else {
  const { skins, unreadable } = discoverSkins(opts.root)
  let filtered = opts.skin ? skins.filter((s) => s.skin === opts.skin) : skins
  if (opts.shard) {
    const [idx, total] = opts.shard.split('/').map(Number)
    filtered = filtered.filter((_, i) => i % total === idx)
  }
  if (!opts.json) {
    console.log(`Discovered ${filtered.length} readable skins (unreadable dirs skipped: ${unreadable.length}: ${unreadable.join(', ') || 'none'})`)
    if (!hasCore) console.warn('Cubism Core unavailable: running Layer 1 only')
  }

  const failSkins = []
  const warnSummary = []
  const noteSummary = []
  let l2dCount = 0

  console.log = () => {}
  console.warn = (...args) => {
    const s = args.join(' ')
    if (activeWarnList && (s.includes('未实现') || s.includes('异常') || s.includes('失败'))) {
      activeWarnList.push(s)
    }
  }

  try {
    for (let i = 0; i < filtered.length; i++) {
      const item = filtered[i]
      activeWarnList = []
      const l1 = auditLayer1(item)
      if (l1.l2d) l2dCount++
      let l2 = { errors: [], notes: [] }
      if (hasCore && l1.m3) {
        l2 = await auditLayer2(item, l1)
      }
      const allErrs = [...l1.errors, ...l2.errors]
      const filteredWarns = l1.warnings.filter((w) => !hasCore || !w.startsWith('zone_missing_hitarea:'))
      const allWarns = [...filteredWarns, ...activeWarnList]
      if (allErrs.length) {
        failSkins.push({ skin: item.skin, errors: allErrs })
        if (!opts.json) origLog(`[FAIL] ${item.skin}: ${allErrs.join(' | ')}`)
      }
      if (allWarns.length) warnSummary.push({ skin: item.skin, warnings: allWarns })
      if (l2.notes.length) noteSummary.push({ skin: item.skin, notes: l2.notes })
    }
  } finally {
    activeWarnList = null
    console.log = origLog
    console.warn = origWarn
  }

  if (opts.json) {
    console.log('__AUDIT_JSON__' + JSON.stringify({ audited: filtered.length, l2dCount, failSkins, warnSummary, noteSummary }))
  } else {
    console.log(`\n=== Audit Summary ===`)
    console.log(`Skins audited: ${filtered.length} (L2D configs: ${l2dCount}, skipped unreadable: ${unreadable.length})`)
    console.log(`Failures: ${failSkins.length}`)
    console.log(`Skins with L1/runtime warnings: ${warnSummary.length}`)
    for (const w of warnSummary.slice(0, 20)) {
      console.log(`  [WARN] ${w.skin}: ${w.warnings.slice(0, 4).join(' ; ')}${w.warnings.length > 4 ? ` (+${w.warnings.length - 4})` : ''}`)
    }
    console.log(`Skins with L2 notes: ${noteSummary.length}`)
    for (const n of noteSummary.slice(0, 15)) {
      console.log(`  [NOTE] ${n.skin}: ${n.notes.slice(0, 3).join(' ; ')}`)
    }
    if (failSkins.length || (opts.strict && warnSummary.length)) process.exit(1)
  }
}
