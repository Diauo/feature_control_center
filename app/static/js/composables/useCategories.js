const { ref, computed } = Vue;

export function useCategories(currentCustomer, addNotification, openModal, closeModal, modal, api) {
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

    // 构建分类引用映射，用于通过映射直接修改节点
    const buildCategoryReferenceMap = (nodes) => {
        if (!nodes || !Array.isArray(nodes)) return;
        categoriesReferenceMap.clear();
        
        const buildMap = (nodeList) => {
            nodeList.forEach((node) => {
                categoriesReferenceMap.set(node.id, node);
                if (node.child && node.child.length > 0) {
                    buildMap(node.child);
                }
            });
        };
        
        buildMap(nodes);
    };

    // 切换分类编辑模式
    const toggleCategoryEdite = () => {
        categorieEditMode.value = !categorieEditMode.value;
    };

    // 切换分类展开/收起
    const toggleCategory = async (category) => {
        if (categorieEditMode.value) {
            const collapseChildren = (cat) => {
                if (cat.child && cat.child.length > 0) {
                    cat.child.forEach(child => {
                        child.expanded = false;
                        collapseChildren(child);
                    });
                }
            };

            category.expanded = !category.expanded;
            if (!category.expanded) {
                collapseChildren(category);
            }
            selectCategory();
            return;
        }
        
        selectedCategory.value = category.id;
        
        if (category.id === null || category.id === undefined) {
            // 加载所有功能的逻辑需要在调用处处理
            return { type: 'loadAllFeatures' };
        } else {
            try {
                const response = await api.feature.get_feature_by_category_id(category.id, currentCustomer.value);
                if (response.data.status) {
                    return { type: 'loadCategoryFeatures', data: response.data.data };
                } else {
                    addNotification(response.data.message || '加载功能列表失败');
                    return { type: 'error' };
                }
            } catch (error) {
                addNotification('加载功能时发生错误: ' + error.message);
                return { type: 'error' };
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
        buildCategoryReferenceMap,
        toggleCategory,
        toggleCategoryEdite,
        selectCategory,
        addCategory,
        delCategory,
        openAddCategoryModal
    };
}