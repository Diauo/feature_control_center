const { createApp, defineComponent, ref } = Vue;

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
      const toggleCategory = (category) => {
        // 如果有子菜单，递归地折叠所有子菜单
        const collapseChildren = (cat) => {
          if (cat.child && cat.child.length > 0) {
            cat.child.forEach(child => {
              child.expanded = false;  // 折叠子菜单
              collapseChildren(child); // 递归折叠
            });
          }
        };

        // 切换当前类别的折叠状态
        category.expanded = !category.expanded;

        // 如果折叠了当前菜单，折叠它的所有子菜单
        if (!category.expanded) {
          collapseChildren(category);
        }
      };

      return {
        toggleCategory,
      };
    },
    template: `
      <div>
        <div v-for="category in categories" :key="category.order_id" class="category">
          <!-- 顶层菜单 -->
          <div class="category-title" @click="toggleCategory(category)">
            {{ category.name }}
            <!-- 只有有子菜单的项才显示 '▶' 或 '▼' -->
            <span v-if="category.child && category.child.length > 0">
              {{ category.expanded ? '▼' : '▶' }}
            </span>
          </div>

          <!-- 递归渲染子菜单 -->
          <div v-if="category.expanded && category.child && category.child.length" class="child-categories">
            <sidebar-menu :categories="category.child"></sidebar-menu>
          </div>
        </div>
      </div>
    `
  });

export default SidebarMenu