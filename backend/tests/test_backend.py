import unittest
from fastapi.testclient import TestClient
from backend.main import app
from backend.engine_adapter import engine_adapter, compute_crc16, text_to_binary, binary_to_text
from backend.models import EngineState, CRCStatus


class TestNetWhisperBackend(unittest.TestCase):
    def setUp(self):
        engine_adapter.reset_stats()
        engine_adapter.state = EngineState.AWAITING_ENGINE
        engine_adapter.acoustic_engine = None
        self.client = TestClient(app)

    def tearDown(self):
        engine_adapter.reset_stats()
        engine_adapter.state = EngineState.AWAITING_ENGINE
        engine_adapter.acoustic_engine = None

    def test_crc16_and_binary_helpers(self):
        text = "NET"
        binary = text_to_binary(text)
        self.assertEqual(len(binary), 24)
        self.assertEqual(binary_to_text(binary), "NET")

        crc1 = compute_crc16(b"NETWHISPER")
        crc2 = compute_crc16(b"NETWHISPER")
        crc_corrupted = compute_crc16(b"NETWHISPER_CORRUPT")
        self.assertEqual(crc1, crc2)
        self.assertNotEqual(crc1, crc_corrupted)

    def test_initial_status_awaiting_engine(self):
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["project_name"], "NetWhisper — Reliable Data Communication over an Acoustic Channel")
        self.assertEqual(data["state"], "AWAITING_ENGINE")
        self.assertFalse(data["engine_connected"])
        self.assertEqual(data["metrics"]["packets_sent"], 0)
        self.assertIn("No acoustic transmission claims", data["notice"])

    def test_transmission_blocked_without_engine_or_test_mode(self):
        response = self.client.post("/api/transmit", json={"message": "Hello World"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("not yet connected", response.json()["detail"])

    def test_toggle_test_mode_and_successful_loopback(self):
        mode_resp = self.client.post("/api/mode", json={"test_mode": True})
        self.assertEqual(mode_resp.status_code, 200)
        self.assertEqual(mode_resp.json()["state"], "TEST_MODE")

        tx_resp = self.client.post("/api/transmit", json={"message": "Network Packet 1", "simulate_noise": False})
        self.assertEqual(tx_resp.status_code, 200)
        tx_data = tx_resp.json()
        self.assertTrue(tx_data["success"])
        self.assertTrue(tx_data["crc_valid"])
        self.assertIn("TEST_LOOPBACK", tx_data["source"])

        status_resp = self.client.get("/api/status")
        status_data = status_resp.json()
        self.assertEqual(status_data["metrics"]["packets_sent"], 1)
        self.assertEqual(status_data["metrics"]["packets_received"], 1)
        self.assertEqual(status_data["metrics"]["crc_valid_count"], 1)
        self.assertEqual(status_data["metrics"]["crc_error_count"], 0)
        self.assertEqual(status_data["recent_crc_status"], "VALID")
        self.assertEqual(status_data["last_transmitted"], "Network Packet 1")
        self.assertEqual(status_data["last_received"], "Network Packet 1")

    def test_noise_corruption_detection(self):
        self.client.post("/api/mode", json={"test_mode": True})
        tx_resp = self.client.post("/api/transmit", json={"message": "CorruptThisData", "simulate_noise": True})
        self.assertEqual(tx_resp.status_code, 200)
        tx_data = tx_resp.json()
        self.assertFalse(tx_data["crc_valid"])

        status_resp = self.client.get("/api/status")
        status = status_resp.json()
        self.assertEqual(status["metrics"]["crc_error_count"], 1)
        self.assertEqual(status["metrics"]["retransmissions"], 1)
        self.assertEqual(status["recent_crc_status"], "CORRUPTED")

    def test_reset_metrics(self):
        self.client.post("/api/mode", json={"test_mode": True})
        self.client.post("/api/transmit", json={"message": "Test Message"})

        reset_resp = self.client.post("/api/reset")
        self.assertEqual(reset_resp.status_code, 200)

        status = self.client.get("/api/status").json()
        self.assertEqual(status["metrics"]["packets_sent"], 0)
        self.assertEqual(status["metrics"]["packets_received"], 0)
        self.assertIsNone(status["last_transmitted"])

    def test_integration_info_endpoint(self):
        resp = self.client.get("/api/integration-info")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("Marnia", data["teammate_engine_role"])
        self.assertIn("Keerthana", data["dashboard_backend_role"])
        self.assertIn("hook_function", data["contract"])

    def test_mock_acoustic_engine_registration(self):
        class MockMarniaEngine:
            def transmit(self, text: str):
                return {"transmitted": text, "freq_mark": 1800, "freq_space": 1200}

        mock_engine = MockMarniaEngine()
        registered = engine_adapter.register_acoustic_engine(mock_engine)
        self.assertTrue(registered)

        status = self.client.get("/api/status").json()
        self.assertTrue(status["engine_connected"])
        self.assertEqual(status["state"], "ACOUSTIC_LIVE")

        tx_resp = self.client.post("/api/transmit", json={"message": "Acoustic Ping"})
        self.assertEqual(tx_resp.status_code, 200)
        self.assertEqual(tx_resp.json()["source"], "ACOUSTIC_ENGINE")

    def test_websocket_connection(self):
        with self.client.websocket_connect("/ws") as ws:
            init_data = ws.receive_json()
            self.assertEqual(init_data["type"], "INITIAL_STATE")
            self.assertEqual(init_data["status"]["state"], "AWAITING_ENGINE")
            self.assertIn("waveform", init_data)

            ws.send_json({"action": "ping"})
            pong_data = ws.receive_json()
            self.assertEqual(pong_data["type"], "pong")


if __name__ == "__main__":
    unittest.main()
