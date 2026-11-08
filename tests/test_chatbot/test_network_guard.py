import socket

import pytest


def test_outbound_network_is_blocked_in_chatbot_tests():
    with pytest.raises(OSError, match="network blocked"):
        socket.create_connection(("8.8.8.8", 53), timeout=1)
    with pytest.raises(OSError, match="network blocked"), socket.socket() as sock:
        sock.connect(("93.184.216.34", 80))
