import unittest
import json
from app import create_app, db
from app.models.base_models import Feature
from app.services.feature_service import get_feature_by_category_tags_id


class TestService(unittest.TestCase):
    def setUp(self):
        # 初始化测试应用
        self.app = create_app("app.config.Test_config")
        self.app_context = self.app.app_context()
        self.app_context.push()

    def test_get_feature_by_category_tags_id(self):
        # 调用服务方法并验证结果
        features = get_feature_by_category_tags_id(1)
        print(features)

if __name__ == "__main__":
    unittest.main()