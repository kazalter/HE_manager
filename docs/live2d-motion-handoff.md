# Live2D motion handoff investigation (2026-11-08)

The current user-visible stutter has no identified skin or interaction yet. The
following defects were reproduced independently; they do not establish that every
perceived pause has the same cause.

## Reproduced and fixed

- A natural reaction completion emptied the Cubism queue during evaluation, but
  the library only processed completion on the following update. That following
  rendered frame had no motion evaluation while asynchronous idle startup waited.
  `dafeng_6` and `lafeiii_3` touch_head both reproduced one empty frame at 60 Hz.
  Completion now drains after the last evaluated frame, before the next render;
  the same regression measures zero empty rendered motion frames.
- FinishAction reserves explicit idle while the engine also requests automatic
  idle. The second request was rejected. Automatic fallback now yields to an
  existing explicit reservation, including a chained reaction.
- Parameter reset used wall time while animation used model elapsed time. Reset
  now freezes with animation when wallpaper tickers pause.
- Default idle preload ran before fades.json loaded, so cached idle motions could
  use the fallback fade instead of the skin's authored transition. Load the table
  first. Also await driven-parameter/boundary preparation before revealing the
  interactive model, preventing a first interaction from resetting driven curves
  while their exemption cache is still loading. Transition durations are unchanged.

## Verification

- Real Cubism engine: both skins, zero empty motion ticks; parameter reset remains
  unchanged while wall time advances during an animation pause.
- lafeiii_3: all three card selections reach idle4/5/6, continue moving, close to
  base idle and allow the opening interaction again.
- Interaction: 41 checks; drag machine: 128; ladder loop: 11; engine curves: 6.
- Desktop: 73 tests, including foreground/input/pause policies.
- Electron 44.8.0 production viewer, offscreen WebGL with physics: touch_head to
  idle for both skins, no reported renderer errors. Finish-to-start wall times
  approximately 2.4 ms and 3.3 ms, with identical animation elapsed times.
  Wallpaper activity messages stop frame production and resume a moving idle.
  These messages exercise the renderer pause path; they do not independently
  verify Windows foreground detection by switching real desktop applications.
- Runtime traces and rendered screenshots are in the workspace sibling folder
  `.motion-diagnostics/` (renderer-report.json, dafeng_6.png, lafeiii_3.png).

## Capturing another case

In the viewer's renderer DevTools console, run
`window.__l2dDiagnostics.start()`, reproduce the interaction, then export
`JSON.stringify(window.__l2dDiagnostics.read())`.
`stop()` disables per-frame sampling. Sampling is disabled by default; the buffer
holds at most 600 frames and 128 events.

The trace includes wall and animation clocks, motion start/finish, selected idle
variant, queue time/weight, reset activity and both ticker states. `motionDelta`
is the largest parameter change after motion evaluation relative to the previous
frame, normalized by parameter range. `postMotionDelta` measures the difference
after subsequent layers including physics; it is not a physics-only measurement.
`wallpaper-activity` records requested pause/resume and the ticker states before
applying it. Use these fields to distinguish an empty queue, a long frame, a
parameter discontinuity and an intentional wallpaper pause.

## Build and update

The desktop build uses `integrations/l2dviewer`, not the older sibling viewer's
`build:manager` destination. Shared source changes were copied from L2Dviewer
into that integration while retaining its desktop/CSP/wallpaper adaptations.
Run `npm run build:manager` there, then `npm run build:ui` in `desktop`.
The output flows through `frontend/public/l2d` to `desktop/ui/l2d`.
The daily application's `resources/app/ui/l2d` was updated and its entry script
SHA-256 checked against the build. The application was restarted. The initial
investigation did not deploy the server or publish a Release. The subsequent
authorized release includes these changes in desktop version 1.0.3.
