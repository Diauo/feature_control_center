const { defineComponent, inject } = Vue;

// 定义 SidebarMenu 组件
const SidebarMenu = defineComponent({
    name: "SidebarMenu",
    props: {
      categories: {
        type: Array,
        required: true,
      },
    },
    setup(props) {
      const openAddCategoryModal = inject('openAddCategoryModal');
      const toggleCategory = inject('toggleCategory');
      const categorieEditMode = inject('categorieEditMode');
      return {
        openAddCategoryModal,
        toggleCategory,
        categorieEditMode,
      };
    },
    template: `
      <div>
        <div v-for="category in categories" :key="category.order_id" class="category">
          <!-- 顶层菜单 -->
          <div class="category-title">
            {{ category.name }}
            <div v-if="categorieEditMode" class="category-active-zone --category-active-zone-edit" @click="toggleCategory(category)" ></div>
            <div v-if="!categorieEditMode" class="category-active-zone --category-active-zone-normal" @click="toggleCategory(category)" ></div>
            <span v-if="categorieEditMode" class="button button--add-category" @click="openAddCategoryModal(category, $event)">📝</span>
          </div>
        </div>
      </div>
    `
  });

export default SidebarMenu