import { describe, expect, it } from 'vitest'

import { featurePackageExtensions } from '@/lib/featurePackages'


describe('featurePackageExtensions', () => {
  it('expands the enabled formats in setting order', () => {
    expect(featurePackageExtensions(['rar', 'tar_gz', 'zip'])).toEqual([
      '.rar',
      '.tar.gz',
      '.tgz',
      '.zip',
    ])
  })

  it('ignores unknown values and removes duplicate extensions', () => {
    expect(featurePackageExtensions(['zip', 'unknown', 'zip'])).toEqual(['.zip'])
  })
})
