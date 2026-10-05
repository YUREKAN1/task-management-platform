from app.models.user import User
from app.models.tag import Tag
from app.models.enums import GlobalRole

def test_user_email_normalization():
    u = User(name="Test", email="  UPPER@eXample.com  ", password_hash="123")
    assert u.email == "upper@example.com"

def test_tag_name_normalization():
    t = Tag(name="  Some Tag  ")
    assert t.name == "some tag"
