import multiprocessing
import socket
from concurrent.futures import ProcessPoolExecutor

import pytest
import requests

pytestmark = pytest.mark.usefixtures("no_network")


def test_a_unix_socket_pair_works():
    left, right = socket.socketpair(socket.AF_UNIX)
    with left, right:
        left.sendall(b"ping")
        assert right.recv(4) == b"ping"


def test_a_unix_socket_connect_works(tmp_path):
    path = str(tmp_path / "local.sock")
    with socket.socket(socket.AF_UNIX) as server, socket.socket(socket.AF_UNIX) as client:
        server.bind(path)
        server.listen(1)
        client.connect(path)
        accepted, _ = server.accept()
        with accepted:
            client.sendall(b"ping")
            assert accepted.recv(4) == b"ping"


def test_a_forkserver_process_pool_works():
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("forkserver")) as pool:
        assert list(pool.map(abs, [-1, -2])) == [1, 2]


@pytest.mark.parametrize(("family", "address"), [(socket.AF_INET, ("127.0.0.1", 9)), (socket.AF_INET6, ("::1", 9))])
def test_internet_connects_fail(family, address):
    try:
        sock = socket.socket(family)
    except OSError:
        pytest.skip("address family not available")
    with sock:
        with pytest.raises(AssertionError, match="network access attempted"):
            sock.connect(address)
        with pytest.raises(AssertionError, match="network access attempted"):
            sock.connect_ex(address)


def test_create_connection_and_requests_stay_blocked():
    with pytest.raises(AssertionError, match="network access attempted"):
        socket.create_connection(("127.0.0.1", 9))
    with pytest.raises(AssertionError, match="network access attempted"):
        requests.get("http://127.0.0.1:9", timeout=1)
