const { ref } = Vue;

export function useNotifications() {
    const notifications = ref([]);
    const notificationCount = ref(0);

    // 添加通知
    const addNotification = (message) => {
        const now = new Date();
        const hours = ('0' + now.getHours()).slice(-2);
        const minutes = ('0' + now.getMinutes()).slice(-2);
        const seconds = ('0' + now.getSeconds()).slice(-2);
        const id = notificationCount.value++;
        const formattedMessage = "💡 " + hours + ":" + minutes + ":" + seconds + "\<br\>" + message;
        
        notifications.value.push({
            id,
            message: formattedMessage
        });
        
        setTimeout(() => {
            removeNotification(id);
        }, 10000);
    };

    // 移除通知
    const removeNotification = (id) => {
        notifications.value = notifications.value.filter(notification => notification.id !== id);
    };

    return {
        notifications,
        notificationCount,
        addNotification,
        removeNotification
    };
}