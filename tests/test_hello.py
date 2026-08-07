def test_hello_world(capsys):
    print("Hello, World!")
    captured = capsys.readouterr()
    assert captured.out.strip() == "Hello, World!"
