const { ref, nextTick } = Vue;

export function useModal() {
    const modal = ref({ 
        show: false, 
        title: "", 
        description: "", 
        fields: [], 
        buttons: [], 
        modalParams: {} 
    });
    const modalWindow = ref(null);

    // 打开模态框
    const openModal = (title, description, fields, buttons, buttonElement) => {
        modal.value.title = title;
        modal.value.fields = fields;
        modal.value.description = description;
        modal.value.buttons = buttons;
        modal.value.show = true;
        
        // 禁止背景页面滚动
        document.body.classList.add('modal-open');
        document.body.style.overflow = 'hidden';
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
        
        // 恢复背景页面滚动
        document.body.classList.remove('modal-open');
        document.body.style.overflow = '';
    };

    return {
        modal,
        modalWindow,
        openModal,
        closeModal
    };
}