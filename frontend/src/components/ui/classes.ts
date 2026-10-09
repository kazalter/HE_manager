// Class recipes shared by the Ui* components and by pages that need the same
// look on a native element or a <router-link>. Every string is a literal so
// Tailwind can see it. DESIGN_SPEC.md documents each recipe.
import type { Component } from 'vue'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ControlSize = 'sm' | 'md' | 'lg'
export type Tone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'info' | 'overlay'
export type CardPadding = 'none' | 'sm' | 'md' | 'lg'

export interface SegmentedOption<V> {
  value: V
  label: string
  icon?: Component
  /** Hide the label visually (icon-only segment); it stays the accessible name. */
  iconOnly?: boolean
}

const BUTTON_BASE = 'inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-lg font-medium select-none transition-colors duration-150 ease-out focus-ring disabled:pointer-events-none disabled:opacity-45 aria-disabled:pointer-events-none aria-disabled:opacity-45'

const BUTTON_SIZE: Record<ControlSize, string> = {
  sm: 'h-8 gap-1.5 px-3 text-meta',
  md: 'h-9 gap-2 px-3.5 text-body',
  lg: 'h-10 gap-2 px-4 text-body pointer-coarse:h-11',
}

const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  primary: 'bg-accent text-on-accent hover:bg-accent/90 active:bg-accent/80',
  secondary: 'border border-line bg-surface-2 text-ink hover:border-line-strong hover:bg-surface-3',
  ghost: 'text-muted hover:bg-surface-2 hover:text-ink',
  danger: 'border border-danger/25 bg-danger/12 text-danger hover:bg-danger/20',
}

export const buttonClass = (variant: ButtonVariant = 'secondary', size: ControlSize = 'md', block = false) =>
  [BUTTON_BASE, BUTTON_SIZE[size], BUTTON_VARIANT[variant], block ? 'w-full' : ''].join(' ')

const ICON_BUTTON_SIZE: Record<ControlSize, string> = {
  sm: 'size-8',
  md: 'size-9 pointer-coarse:size-11',
  lg: 'size-10 pointer-coarse:size-11',
}

export const iconButtonClass = (variant: ButtonVariant = 'ghost', size: ControlSize = 'md') =>
  [BUTTON_BASE, ICON_BUTTON_SIZE[size], BUTTON_VARIANT[variant], 'aria-pressed:bg-accent/15 aria-pressed:text-accent-glow'].join(' ')

const CONTROL_SIZE: Record<ControlSize, string> = {
  sm: 'h-8 px-2.5 text-meta',
  md: 'h-9 px-3 text-body',
  lg: 'h-10 px-3.5 text-body',
}

/** Text input / native select / textarea look. Add `h-auto py-2` for textarea. */
export const controlClass = (size: ControlSize = 'md', invalid = false) => [
  'w-full min-w-0 rounded-lg border bg-surface-2 text-ink placeholder:text-faint transition-colors duration-150 ease-out',
  'focus:outline-none focus:ring-2 disabled:cursor-not-allowed disabled:opacity-50',
  CONTROL_SIZE[size],
  invalid
    ? 'border-danger/60 focus:border-danger focus:ring-danger/25'
    : 'border-line hover:border-line-strong focus:border-accent focus:ring-accent/25',
].join(' ')

export const chipClass = (selected = false, size: 'sm' | 'md' = 'md') => [
  'inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border font-medium transition-colors duration-150 ease-out focus-ring',
  size === 'sm' ? 'h-7 px-2.5 text-caption pointer-coarse:h-9' : 'h-8 px-3 text-meta pointer-coarse:h-10',
  selected
    ? 'border-accent/50 bg-accent/15 text-accent-glow'
    : 'border-line bg-surface text-muted hover:border-line-strong hover:text-ink',
].join(' ')

const BADGE_TONE: Record<Tone, string> = {
  neutral: 'bg-surface-3 text-muted',
  accent: 'bg-accent/15 text-accent-glow',
  success: 'bg-success/12 text-success',
  warning: 'bg-warning/12 text-warning',
  danger: 'bg-danger/12 text-danger',
  info: 'bg-info/12 text-info',
  overlay: 'bg-black/65 text-white',
}

export const badgeClass = (tone: Tone = 'neutral') =>
  ['inline-flex h-5 shrink-0 items-center gap-1 whitespace-nowrap rounded-md px-1.5 text-caption font-medium tabular-nums', BADGE_TONE[tone]].join(' ')

const CARD_PADDING: Record<CardPadding, string> = {
  none: '',
  sm: 'p-3',
  md: 'p-4 sm:p-5',
  lg: 'p-5 sm:p-6',
}

export const cardClass = (padding: CardPadding = 'md', interactive = false) => [
  'rounded-2xl border border-line bg-surface',
  CARD_PADDING[padding],
  interactive ? 'text-left transition-colors duration-150 ease-out hover:border-line-strong hover:bg-surface-2 focus-ring' : '',
].join(' ')

/** Floating menus, popovers and dropdown panels. */
export const popoverClass = 'rounded-2xl border border-line-strong bg-surface-3 p-1.5 shadow-pop'

/** One row inside a popover/menu. Add `aria-selected:` or a selected class as needed. */
export const menuItemClass = 'flex w-full items-center gap-2.5 h-9 rounded-lg px-2.5 text-left text-body text-muted transition-colors duration-100 hover:bg-line-strong/60 hover:text-ink focus-ring-inset'

/** Row inside a list card (`divide-y divide-line`). */
export const listRowClass = 'flex min-h-14 items-center gap-3 px-4 py-3'

/** Small uppercase-free form label above a control. */
export const fieldLabelClass = 'mb-1.5 block text-meta font-medium text-muted'
export const fieldHintClass = 'mt-1.5 text-caption text-subtle'
