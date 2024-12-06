from app import db

class Base_model(db.Model):
    __tablename__ = "base"
    __abstract__ = True  # 标记为抽象类，不会映射到具体的表

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    def save(self):
        db.session.add(self)
        db.session.commit()

    def delete(self):
        db.session.delete(self)
        db.session.commit()

    def __repr__(self):
        name = getattr(self, 'name', '无名model')
        return f"<{name}>"

class Feature(Base_model):
    __tablename__ = 'base_feature'

    name = db.Column(db.String(64), unique=False, nullable=False)
    description = db.Column(db.String(256), unique=False, nullable=True)
    customer_id = db.Column(db.Integer, unique=False, nullable=False)
    category_tags = ""
    customer_name = ""

class Category(Base_model):
    __tablename__ = 'base_category'

    name = db.Column(db.String(64), unique=True, nullable=False)
    code = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.String(256), unique=False, nullable=True)

class Tag(Base_model):
    __tablename__ = 'base_tag'

    name = db.Column(db.String(64), unique=True, nullable=False)
    code = db.Column(db.String(64), unique=True, nullable=False)

class Customer(Base_model):
    __tablename__ = 'base_customer'

    name = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.String(256), unique=False, nullable=True)

