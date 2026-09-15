import { toast, type ExternalToast } from 'vue-sonner'

export interface NotifyOptions {
  description?: string
  duration?: number
  id?: string | number
  action?: {
    label: string
    onClick: () => void
  }
}

function options(value?: NotifyOptions): ExternalToast | undefined {
  if (!value) return undefined
  return {
    description: value.description,
    duration: value.duration,
    id: value.id,
    action: value.action,
    closeButton: true,
  }
}

export const notify = {
  success(title: string, value?: NotifyOptions): string | number {
    return toast.success(title, options({ duration: 3600, ...value }))
  },
  error(title: string, value?: NotifyOptions): string | number {
    return toast.error(title, options({ duration: 8000, ...value }))
  },
  warning(title: string, value?: NotifyOptions): string | number {
    return toast.warning(title, options({ duration: 6000, ...value }))
  },
  info(title: string, value?: NotifyOptions): string | number {
    return toast.info(title, options({ duration: 4500, ...value }))
  },
  loading(title: string, value?: NotifyOptions): string | number {
    return toast.loading(title, options({ duration: Infinity, ...value }))
  },
  dismiss(id?: string | number): void {
    toast.dismiss(id)
  },
}
