const revision = import.meta.env.HE_SOURCE_REVISION as string | null | undefined
const dirty = import.meta.env.HE_SOURCE_DIRTY as boolean | null | undefined
export const sourceVersion = revision ? `${revision.slice(0, 12)}${dirty ? '（含未提交改动）' : ''}` : '未知'
