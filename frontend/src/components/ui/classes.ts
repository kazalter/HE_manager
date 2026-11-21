// Class recipes shared by the Ui* components and by pages that need the same
// look on a native element or a <router-link>. Every string is a literal so
// Tailwind can see it.
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

const BUTTON_BASE = 'inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-xl font-medium select-none transition-[background-color,border-color,color,box-shadow,scale] duration-150 ease-out focus-ring disabled:pointer-events-none disabled:opacity-45 aria-disabled:pointer-events-none aria-disabled:opacity-45 active:scale-[0.98]'

const BUTTON_SIZE: Record<ControlSize, string> = {
  sm: 'min-h-8 gap-1.5 px-3 py-1 text-meta',
  md: 'min-h-9 gap-2 px-3.5 py-1.5 text-body',
  lg: 'min-h-10 gap-2 px-4 py-2 text-body pointer-coarse:min-h-11',
}

const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  primary: 'bg-accent text-on-accent shadow-[inset_0_1px_0_rgb(255_255_255/0.22),0_4px_14px_-4px_rgb(var(--color-accent)/0.55)] hover:bg-accent/92 hover:shadow-[inset_0_1px_0_rgb(255_255_255/0.25),0_6px_18px_-4px_rgb(var(--color-accent)/0.65)] active:bg-accent/85',
  secondary: 'border border-line bg-surface-2 text-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.04)] hover:border-line-strong hover:bg-surface-3',
  ghost: 'text-muted hover:bg-surface-2/85 hover:text-ink',
  danger: 'border border-danger/30 bg-danger/12 text-danger hover:border-danger/45 hover:bg-danger/20',
}

export const buttonClass = (variant: ButtonVariant = 'secondary', size: ControlSize = 'md', block = false) =>
  [BUTTON_BASE, BUTTON_SIZE[size], BUTTON_VARIANT[variant], block ? 'w-full' : ''].join(' ')

const ICON_BUTTON_SIZE: Record<ControlSize, string> = {
  sm: 'min-h-8 min-w-8 p-1.5',
  md: 'min-h-9 min-w-9 p-2 pointer-coarse:min-h-11 pointer-coarse:min-w-11',
  lg: 'min-h-10 min-w-10 p-2 pointer-coarse:min-h-11 pointer-coarse:min-w-11',
}

export const iconButtonClass = (variant: ButtonVariant = 'ghost', size: ControlSize = 'md') =>
  [BUTTON_BASE, ICON_BUTTON_SIZE[size], BUTTON_VARIANT[variant], 'aria-pressed:border-accent/45 aria-pressed:bg-accent/15 aria-pressed:text-accent-glow'].join(' ')

const CONTROL_SIZE: Record<ControlSize, string> = {
  sm: 'min-h-8 px-2.5 py-1 text-meta',
  md: 'min-h-9 px-3 py-1.5 text-body',
  lg: 'min-h-10 px-3.5 py-2 text-body',
}

/** Text input / native select / textarea look. Add `h-auto py-2` for textarea. */
export const controlClass = (size: ControlSize = 'md', invalid = false) => [
  'w-full min-w-0 rounded-xl border bg-surface-2/90 text-ink placeholder:text-faint transition-[border-color,background-color,box-shadow] duration-150 ease-out',
  'focus:outline-none focus:ring-2 disabled:cursor-not-allowed disabled:opacity-50',
  CONTROL_SIZE[size],
  invalid
    ? 'border-danger/60 focus:border-danger focus:ring-danger/25'
    : 'border-line hover:border-line-strong focus:border-accent focus:bg-surface-2 focus:ring-accent/25',
].join(' ')

export const chipClass = (selected = false, size: 'sm' | 'md' = 'md') => [
  'inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border font-medium transition-colors duration-150 ease-out focus-ring',
  size === 'sm' ? 'min-h-7 px-2.5 py-0.5 text-caption pointer-coarse:min-h-9' : 'min-h-8 px-3 py-1 text-meta pointer-coarse:min-h-10',
  selected
    ? 'border-accent/50 bg-accent/15 text-accent-glow shadow-[inset_0_1px_0_rgb(255_255_255/0.08)]'
    : 'border-line bg-surface text-muted hover:border-line-strong hover:text-ink',
].join(' ')

const BADGE_TONE: Record<Tone, string> = {
  neutral: 'bg-surface-3 text-muted ring-1 ring-inset ring-line/80',
  accent: 'bg-accent/15 text-accent-glow ring-1 ring-inset ring-accent/25',
  success: 'bg-success/12 text-success ring-1 ring-inset ring-success/20',
  warning: 'bg-warning/12 text-warning ring-1 ring-inset ring-warning/20',
  danger: 'bg-danger/12 text-danger ring-1 ring-inset ring-danger/20',
  info: 'bg-info/12 text-info ring-1 ring-inset ring-info/20',
  overlay: 'bg-black/65 text-white backdrop-blur-md ring-1 ring-inset ring-white/15',
}

export const badgeClass = (tone: Tone = 'neutral') =>
  ['inline-flex min-h-5 shrink-0 items-center gap-1 whitespace-nowrap rounded-md px-1.5 py-0.5 text-caption font-medium tabular-nums', BADGE_TONE[tone]].join(' ')

const CARD_PADDING: Record<CardPadding, string> = {
  none: '',
  sm: 'p-3',
  md: 'p-4 sm:p-5',
  lg: 'p-5 sm:p-6',
}

export const cardClass = (padding: CardPadding = 'md', interactive = false) => [
  'rounded-2xl squircle border border-line bg-surface shadow-[inset_0_1px_0_var(--he-border-specular)]',
  CARD_PADDING[padding],
  interactive ? 'text-left transition-[background-color,border-color,box-shadow,translate] duration-150 ease-out hover:border-line-strong hover:bg-surface-2 focus-ring' : '',
].join(' ')

/** Floating menus, popovers and dropdown panels. */
export const popoverClass = 'rounded-2xl squircle border border-line-strong glass-elevated p-1.5 shadow-pop'

/** One row inside a popover/menu. Add `aria-selected:` or a selected class as needed. */
export const menuItemClass = 'flex w-full items-center gap-2.5 min-h-9 rounded-xl px-2.5 py-1.5 text-left text-body text-muted transition-colors duration-100 hover:bg-line-strong/55 hover:text-ink focus-ring-inset'

/** Row inside a list card (`divide-y divide-line`). */
export const listRowClass = 'flex min-h-14 items-center gap-3 px-4 py-3'

/** Small uppercase-free form label above a control. */
export const fieldLabelClass = 'mb-1.5 block text-meta font-medium text-muted'
export const fieldHintClass = 'mt-1.5 text-caption text-subtle'
