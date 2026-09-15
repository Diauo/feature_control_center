import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import ModalDialog from '@/components/ModalDialog.vue'


describe('ModalDialog', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('renders through teleport and exposes an explicit close action', async () => {
    const wrapper = mount(ModalDialog, {
      attachTo: document.body,
      props: { open: true, title: '确认操作', description: '请核对信息' },
      slots: { default: '<p>正文</p>' },
    })

    expect(document.body.textContent).toContain('确认操作')
    expect(document.body.textContent).toContain('正文')
    await document.querySelector<HTMLButtonElement>('[aria-label="关闭"]')!.click()
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })

  it('does not render a close button for a non-closeable secret', () => {
    const wrapper = mount(ModalDialog, {
      attachTo: document.body,
      props: { open: true, title: '临时密码', closeable: false },
    })
    expect(document.querySelector('[aria-label="关闭"]')).toBeNull()
    wrapper.unmount()
  })
})
