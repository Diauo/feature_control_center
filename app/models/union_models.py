from app import db

class Union_feature_category(db.Model):
    __tablename__ = 'union_feature_category'

    id = db.Column(db.Integer, primary_key=True)
    feature_id = db.Column(db.Integer, unique=False, nullable=False)
    category_id = db.Column(db.Integer, unique=False, nullable=False)
