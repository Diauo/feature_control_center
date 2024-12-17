from app import db
from .base_models import Base_model

class Union_feature_tag(Base_model):
    __tablename__ = 'union_feature_tag'

    feature_id = db.Column(db.Integer, unique=False, nullable=False)
    tag_id = db.Column(db.Integer, unique=False, nullable=False)

class Union_category_tag(Base_model):
    __tablename__ = 'union_category_tag'

    category_id = db.Column(db.Integer, unique=False, nullable=False)
    tag_id = db.Column(db.Integer, unique=False, nullable=False)