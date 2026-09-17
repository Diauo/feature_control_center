import { apiRequest } from '@/lib/api'

export const FEATURE_PACKAGE_FORMAT_EXTENSIONS: Readonly<Record<string, readonly string[]>> = {
  zip: ['.zip'],
  '7z': ['.7z'],
  rar: ['.rar'],
  tar: ['.tar'],
  tar_gz: ['.tar.gz', '.tgz'],
  tar_bz2: ['.tar.bz2', '.tbz2'],
  tar_xz: ['.tar.xz', '.txz'],
}

export function featurePackageExtensions(formats: readonly string[]): string[] {
  return [...new Set(formats.flatMap((format) => FEATURE_PACKAGE_FORMAT_EXTENSIONS[format] ?? []))]
}

export interface FeatureUploadResult {
  restored?: boolean
  activatedForCustomer?: boolean
}

export async function uploadFeaturePackage(customerId: string, file: File): Promise<FeatureUploadResult> {
  const body = new FormData()
  body.append('customerId', customerId)
  body.append('package', file)
  return await apiRequest<FeatureUploadResult>('/api/admin/features/versions', { method: 'POST', body })
}
