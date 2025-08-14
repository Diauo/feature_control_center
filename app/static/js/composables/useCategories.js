const { ref, computed } = Vue;

export function useCategories(currentUser, currentCustomer, addNotification, openModal, closeModal, modal, api) {
    const categories = ref([]);
    const selectedCategory = ref(null);
    const categorieEditMode = ref(false);
    const categoriesReferenceMap = new Map();

    // 根据选择的客户筛选分类
    const filteredCategories = computed(() => {
        if (!currentCustomer.value) {
            return categories.value;
        }
        return categories.value.filter(category =>
            category.customer_id === currentCustomer.value
        );
    });

    // 切换分类编辑模式
    const toggleCategoryEdite = () => {
        categorieEditMode.value = !categorieEditMode.value;
    };

    // 切换分类展开/收起
    const toggleCategory = async (category) => {
        // 设置选中的分类
        selectedCategory.value = category ? category.id : null;
        
        // 如果分类为空，说明点击的是"所有功能选项卡"
        if (!category || category.id === null) {
            // 如果客户ID为空，检查当前用户是否为管理员
            if (!currentCustomer.value) {
                if (currentUser.value && currentUser.value.role === 'admin') {
                    // 管理员可以查看所有功能，不传客户ID
                    return { type: 'reloadFeatures', method: 'all' };
                } else {
                    // 非管理员且没有选择有效客户，报错
                    addNotification('错误：没有选择有效的客户');
                    return { type: 'error', message: '没有选择有效的客户' };
                }
            } else {
                // 有客户ID，调用get_feature_by_customer_id查询当前客户下的所有功能
                return { type: 'reloadFeatures', method: 'customer', customerId: currentCustomer.value };
            }
        } else {
            // 有具体分类，调用get_feature_by_category_id查询分类下的功能
            // 如果客户ID为空且当前用户是管理员，则不传客户ID
            if (!currentCustomer.value && currentUser.value && currentUser.value.role === 'admin') {
                return { type: 'reloadFeatures', method: 'category', categoryId: category.id };
            } else {
                // 传入客户ID（即使是空值也会传）
                return {
                    type: 'reloadFeatures',
                    method: 'category',
                    categoryId: category.id,
                    customerId: currentCustomer.value
                };
            }
        }
    };

    // 选择分类
    const selectCategory = async (categoryCode) => {
        selectedCategory.value = categoryCode || null;
        return { type: 'reloadFeatures' };
    };

    // 添加分类
    const addCategory = async (params) => {
        const modalParams = modal.value.modalParams;
        const requestBody = {
            customer_id: params.customer_id,
            depth_level: params.depth_level + 1,
            parent_id: params.id,
            tags: modalParams.modalParams,
            name: modalParams.name,
            order_id: modalParams.order_id,
        };
        
        if (!requestBody.name) {
            alert("请输入新分类的名称！");
            return;
        }
        
        try {
            const response = await api.category.add_category(requestBody);
            console.log(response);
            
            if (response.data.status) {
                const parent = categoriesReferenceMap.get(params.id);
                if (parent) {
                    if (!parent.child) {
                        parent.child = [];
                    }
                    parent.child.push(response.data.data);
                } else {
                    const index = categories.value.push(response.data.data);
                    categoriesReferenceMap.set(response.data.data.id, categories.value[index - 1]);
                }
                closeModal();
                addNotification(response.data.message || "分类添加成功");
            } else {
                addNotification(response.data.message || "插入分类失败：" + response.data.data);
            }
        } catch (error) {
            addNotification('添加分类时发生错误: ' + error.message);
        }
    };

    // 删除分类
    const delCategory = async (params) => {
        const requestBody = { id: params.id };
        
        try {
            const response = await api.category.del_category(requestBody);
            
            if (response.data.status) {
                const parent = categoriesReferenceMap.get(params.parent_id);
                if (parent?.child) {
                    const childIndex = parent.child.findIndex(child => child.id === params.id);
                    if (childIndex !== -1) {
                        parent.child.splice(childIndex, 1);
                    }
                } else {
                    const index = categories.value.findIndex(category => category.id === params.id);
                    if (index !== -1) {
                        categories.value.splice(index, 1);
                    }
                    categoriesReferenceMap.delete(params.id);
                }
                closeModal();
                addNotification(response.data.message || "分类删除成功");
            } else {
                addNotification(response.data.message || "删除分类失败：" + response.data.data);
            }
        } catch (error) {
            addNotification('删除分类时发生错误: ' + error.message);
        }
    };

    // 打开新增分类窗口
    const openAddCategoryModal = (category, event) => {
        if (!category) {
            category = {
                "customer_id": currentCustomer.value,
                "depth_level": -1,
                "id": 0,
                "expanded": false
            };
        }
        
        const fields = [
            {
                type: "text",
                key: "name",
                label: "名称",
            }, {
                type: "text",
                key: "order_id",
                label: "排序",
            }
        ];
        
        const buttons = [
            {
                label: "新增",
                style: "btn-confirm",
                function: addCategory,
                param: category
            },
            {
                label: "修改",
                style: "btn-warnning",
                function: closeModal,
                param: category
            },
            {
                label: "删除",
                style: "btn-danger",
                function: delCategory,
                param: category
            }
        ];
        
        const buttonElement = event.currentTarget;
        openModal(
            "分类菜单", 
            "新增：根据填写的信息，在本分类下新增一个子菜单；\<br\>修改：根据填写的信息修改当前分类；\<br\>删除：删除当前分类。", 
            fields, 
            buttons, 
            buttonElement
        );
    };

    return {
        categories,
        selectedCategory,
        categorieEditMode,
        filteredCategories,
        toggleCategory,
        toggleCategoryEdite,
        selectCategory,
        addCategory,
        delCategory,
        openAddCategoryModal
    };
}