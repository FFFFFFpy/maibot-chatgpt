import ipaddress
import socket
import pytest


@pytest.fixture(autouse=True)
def offline_only(monkeypatch, request):
    if request.node.get_closest_marker("offline") is None:
        return
    original = socket.socket.connect

    def connect(sock, addr):
        if isinstance(addr, tuple) and not ipaddress.ip_address(addr[0]).is_loopback:
            raise AssertionError("external socket forbidden")
        return original(sock, addr)

    monkeypatch.setattr(socket.socket, "connect", connect)
