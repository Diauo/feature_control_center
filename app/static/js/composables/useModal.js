const { ref, nextTick } = Vue;

export function useModal() {
    const modal = ref({ 
        show: false, 
        title: "", 
        description: "", 
        fields: [], 
        buttons: [], 
        modalParams: {}, 
        top: 0, 
        left: 0 
    });
    const modalWindow = ref(null);

    // 打开模态框
    const openModal = (title, description, fields, buttons, buttonElement) => {
        modal.value.title = title;
        modal.value.fields = fields;
        modal.value.description = description;
        modal.value.buttons = buttons;
        modal.value.show = true;
        
        // 更新动态窗口的位置，避免超出屏幕
        nextTick(() => {
            if (modalWindow.value) {
                const modalRect = modalWindow.value.getBoundingClientRect();
                const modalWidth = modalRect.width;
                const modalHeight = modalRect.height;
                const buttonRect = buttonElement.getBoundingClientRect();
                let top = buttonRect.top + window.scrollY;
                let left = (buttonRect.left + window.scrollX) * 1.25;
                
                // 检查是否超出屏幕底部
                if (top + modalHeight > window.innerHeight + window.scrollY) {
                    top = window.innerHeight + window.scrollY - modalHeight;
                }
                
                // 检查是否超出屏幕右侧
                if (left + modalWidth > window.innerWidth + window.scrollX) {
                    left = window.innerWidth + window.scrollX - modalWidth;
                }
                
                modal.value.top = top;
                modal.value.left = left;
            }
        });
    };

    // 关闭模态框
    const closeModal = () => {
        modal.value.show = false;
        modal.value.title = "";
        modal.value.fields = [];
        modal.value.description = "";
        modal.value.modalParams = {};
        modal.value.params = {};
        modal.value.hanldFunction = undefined;
    };

    return {
        modal,
        modalWindow,
        openModal,
        closeModal
    };
}