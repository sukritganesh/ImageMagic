import io
import runpy
import socket
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


@unittest.skipUnless(sys.platform == "win32", "The launcher uses the Windows portable runtime")
class LauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.launcher = runpy.run_path(str(Path(__file__).resolve().parents[1] / "launch_studio.py"))

    def test_only_reopens_a_studio_owned_by_this_installation(self):
        discover = self.launcher["running_port"]
        psutil = self.launcher["psutil"]
        connections = [
            SimpleNamespace(status=psutil.CONN_LISTEN, laddr=SimpleNamespace(ip="127.0.0.1", port=p), pid=i)
            for i, p in enumerate((8188, 8190), start=1)
        ]
        paths = {1: r"C:\another-install\python.exe", 2: str(self.launcher["PYTHON"])}
        with patch.object(psutil, "net_connections", return_value=connections), \
             patch.object(psutil, "Process", side_effect=lambda pid: SimpleNamespace(exe=lambda: paths[pid])), \
             patch.dict(discover.__globals__, ready=lambda port: True):
            self.assertEqual(discover(), 8190)
            paths[2] = paths[1]
            self.assertIsNone(discover())

    def test_occupied_port_becomes_available_after_release(self):
        available = self.launcher["port_available"]
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            self.assertFalse(available(port))
        self.assertTrue(available(port))

    def test_maintenance_stops_only_the_idle_server_for_this_installation(self):
        stop = self.launcher["stop_studio"]
        process = Mock()
        with patch.dict(stop.__globals__, running_studio=lambda: (8189, process)), \
             patch("urllib.request.urlopen") as get_queue:
            for queue in (b'{"queue_running":[1],"queue_pending":[]}', b'{"queue_running":[],"queue_pending":[1]}'):
                get_queue.return_value = io.BytesIO(queue)
                with self.assertRaises(SystemExit):
                    stop()
                process.terminate.assert_not_called()
            get_queue.return_value = io.BytesIO(b'{"queue_running":[],"queue_pending":[]}')
            stop()
            get_queue.assert_called_with("http://127.0.0.1:8189/queue", timeout=5)
            process.terminate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
