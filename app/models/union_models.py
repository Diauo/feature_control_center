from app import db


class Union_feature_tag(db.Model):
    __tablename__ = 'union_feature_tag'

    id = db.Column(db.Integer, primary_key=True)
    feature_id = db.Column(db.Integer, unique=False, nullable=False)
    tag_id = db.Column(db.Integer, unique=False, nullable=False)


class Union_category_tag(db.Model):
    __tablename__ = 'union_category_tag'

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, unique=False, nullable=False)
    tag_id = db.Column(db.Integer, unique=False, nullable=False)