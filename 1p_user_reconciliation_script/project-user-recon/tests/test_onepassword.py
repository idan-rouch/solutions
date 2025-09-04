from recon.onepassword import list_1password_users

def test_normalization():
    users = list_1password_users(mock=True, mock_path="tests/fixtures/op_user_list.json")
    assert len(users) == 3
    assert users[0]["email"] == "alice@example.com"
    assert users[0]["state"] == "ACTIVE"
    assert "id" in users[0]
