/**
 * 模态框初始化脚本
 * 在 DOM 加载完成后创建 modal-root 容器
 */

export function ensureModalRoot() {
    let modalRoot = document.getElementById('modal-root');
    if (!modalRoot) {
        modalRoot = document.createElement('div');
        modalRoot.id = 'modal-root';
        document.body.appendChild(modalRoot);
    }
    return modalRoot;
}

// 在脚本加载时立即初始化
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ensureModalRoot);
} else {
    ensureModalRoot();
}
