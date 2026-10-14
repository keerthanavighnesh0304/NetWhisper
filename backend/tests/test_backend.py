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
        self.assertIn("fsk_engine.transmit_text", data["contract"]["expected_engine_interface"][0])

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

    def test_fsk_engine_transmit_text_success_mapping(self):
        class MockFSKEngine:
            AUDIO_HARDWARE_AVAILABLE = True

            def transmit_text(self, message: str, seq_num: int = None):
                return {
                    "success": True,
                    "message": message,
                    "seq_num": 15,
                    "crc_16": 0x29B1,
                    "crc_hex": "0x29B1",
                    "duration_sec": 0.85,
                    "bytes_sent": len(message.encode("utf-8")),
                    "error": None
                }

        engine_adapter.register_acoustic_engine(MockFSKEngine())
        tx_resp = self.client.post("/api/transmit", json={"message": "Acoustic Data Frame"})
        self.assertEqual(tx_resp.status_code, 200)
        data = tx_resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["seq_num"], 15)
        self.assertEqual(data["crc_hex"], "0x29B1")
        self.assertEqual(data["source"], "ACOUSTIC_ENGINE")
        self.assertEqual(data["latency_ms"], 850.0)

        # Check status reflects metrics
        status = self.client.get("/api/status").json()
        self.assertEqual(status["metrics"]["packets_sent"], 1)
        self.assertEqual(status["recent_packets"][-1]["seq_num"], 15)
        self.assertEqual(status["recent_packets"][-1]["source"], "ACOUSTIC_ENGINE")

    def test_fsk_engine_transmit_failure_handling(self):
        class MockFailedFSKEngine:
            AUDIO_HARDWARE_AVAILABLE = False

            def transmit_text(self, message: str, seq_num: int = None):
                return {
                    "success": False,
                    "error": "sounddevice package not available or audio output unavailable."
                }

        engine_adapter.register_acoustic_engine(MockFailedFSKEngine())
        tx_resp = self.client.post("/api/transmit", json={"message": "Fail Message"})
        self.assertEqual(tx_resp.status_code, 400)
        self.assertIn("sounddevice package not available", tx_resp.json()["detail"])

        # Packets sent should remain 0 on failed transmission
        status = self.client.get("/api/status").json()
        self.assertEqual(status["metrics"]["packets_sent"], 0)

    def test_fsk_engine_receive_success_mapping(self):
        class MockReceiveFSKEngine:
            AUDIO_HARDWARE_AVAILABLE = True

            def receive_text(self, timeout_seconds: float = 10.0):
                return "Decoded Acoustic Frame", {
                    "success": True,
                    "message": "Decoded Acoustic Frame",
                    "seq_num": 22,
                    "crc_valid": True,
                    "received_crc": 0xABCD,
                    "correlation_ratio": 12.5,
                    "error": None
                }

        engine_adapter.register_acoustic_engine(MockReceiveFSKEngine())
        rx_resp = self.client.post("/api/receive", json={"timeout_seconds": 5.0})
        self.assertEqual(rx_resp.status_code, 200)
        data = rx_resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["message"], "Decoded Acoustic Frame")
        self.assertEqual(data["seq_num"], 22)
        self.assertTrue(data["crc_valid"])
        self.assertEqual(data["crc_hex"], "0xABCD")
        self.assertEqual(data["correlation_ratio"], 12.5)

        # Verify metrics updated
        status = self.client.get("/api/status").json()
        self.assertEqual(status["metrics"]["packets_received"], 1)
        self.assertEqual(status["metrics"]["crc_valid_count"], 1)
        self.assertEqual(status["recent_crc_status"], "VALID")
        self.assertEqual(status["last_received"], "Decoded Acoustic Frame")

    def test_fsk_engine_receive_crc_error_handling(self):
        class MockCorruptedReceiveFSKEngine:
            AUDIO_HARDWARE_AVAILABLE = True

            def receive_text(self, timeout_seconds: float = 10.0):
                return None, {
                    "success": False,
                    "detected": True,
                    "crc_valid": False,
                    "seq_num": 23,
                    "received_crc": 0x9999,
                    "raw_text": "BadNoiseBytes",
                    "error": "CRC-16 mismatch: received 0x9999, computed 0x1234 (corrupted frame rejected)",
                    "correlation_ratio": 9.2
                }

        engine_adapter.register_acoustic_engine(MockCorruptedReceiveFSKEngine())
        rx_resp = self.client.post("/api/receive", json={"timeout_seconds": 5.0})
        self.assertEqual(rx_resp.status_code, 200)
        data = rx_resp.json()
        self.assertFalse(data["success"])
        self.assertFalse(data["crc_valid"])
        self.assertIn("CRC-16 mismatch", data["error"])

        status = self.client.get("/api/status").json()
        self.assertEqual(status["metrics"]["packets_received"], 1)
        self.assertEqual(status["metrics"]["crc_error_count"], 1)
        self.assertEqual(status["metrics"]["retransmissions"], 1)
        self.assertEqual(status["recent_crc_status"], "CORRUPTED")

    def test_real_fsk_engine_module_integration(self):
        import fsk_engine
        engine_adapter.register_acoustic_engine(fsk_engine)
        status = self.client.get("/api/status").json()
        self.assertTrue(status["engine_connected"])
        self.assertEqual(status["state"], "ACOUSTIC_LIVE")

        # In current environment without sounddevice, transmit safely returns 400 error
        tx_resp = self.client.post("/api/transmit", json={"message": "Real Engine Test"})
        if not getattr(fsk_engine, "AUDIO_HARDWARE_AVAILABLE", False):
            self.assertEqual(tx_resp.status_code, 400)
            self.assertIn("sounddevice", tx_resp.json()["detail"])

    def test_websocket_connection(self):
        with self.client.websocket_connect("/ws") as ws:
            init_data = ws.receive_json()
            self.assertEqual(init_data["type"], "INITIAL_STATE")
            self.assertEqual(init_data["status"]["state"], "AWAITING_ENGINE")
            self.assertIn("waveform", init_data)

            ws.send_json({"action": "ping"})
            pong_data = ws.receive_json()
            self.assertEqual(pong_data["type"], "pong")


    def test_tx_completion_does_not_update_receiver_or_crc(self):
        class MockTxOnlyEngine:
            AUDIO_HARDWARE_AVAILABLE = True

            def transmit_text(self, message: str, seq_num: int = None):
                return {
                    "success": True,
                    "message": message,
                    "seq_num": 101,
                    "crc_16": 0x1234,
                    "crc_hex": "0x1234",
                    "duration_sec": 0.5,
                    "bytes_sent": len(message.encode("utf-8")),
                    "error": None
                }

        engine_adapter.register_acoustic_engine(MockTxOnlyEngine())

        with self.client.websocket_connect("/ws") as ws:
            ws.receive_json()  # INITIAL_STATE

            # Transmit message
            tx_resp = self.client.post("/api/transmit", json={"message": "TX Only Test Frame"})
            self.assertEqual(tx_resp.status_code, 200)

            # Receive WS events
            ws_tx_start = ws.receive_json()
            self.assertEqual(ws_tx_start["type"], "TX_START")

            ws_tx_complete = ws.receive_json()
            self.assertEqual(ws_tx_complete["type"], "TX_COMPLETE")
            self.assertEqual(ws_tx_complete["packet"]["payload_text"], "TX Only Test Frame")

        # Verify backend status: transmitter is updated, but receiver and CRC remain untouched!
        status = self.client.get("/api/status").json()
        self.assertEqual(status["last_transmitted"], "TX Only Test Frame")
        self.assertIsNone(status["last_received"])
        self.assertEqual(status["recent_crc_status"], "IDLE")
        self.assertEqual(status["metrics"]["packets_sent"], 1)
        self.assertEqual(status["metrics"]["packets_received"], 0)

    def test_rx_failure_does_not_falsely_display_received_message(self):
        class MockSilentEngine:
            AUDIO_HARDWARE_AVAILABLE = True

            def receive_text(self, timeout_seconds: float = 10.0):
                return None, {
                    "success": False,
                    "error": "No acoustic signal detected within timeout.",
                    "detected": False
                }

        engine_adapter.register_acoustic_engine(MockSilentEngine())
        rx_resp = self.client.post("/api/receive", json={"timeout_seconds": 3.0})
        self.assertEqual(rx_resp.status_code, 200)
        data = rx_resp.json()
        self.assertFalse(data["success"])
        self.assertIn("No acoustic signal detected", data["error"])

        status = self.client.get("/api/status").json()
        self.assertIsNone(status["last_received"])
        self.assertEqual(status["recent_crc_status"], "IDLE")
        self.assertEqual(status["metrics"]["packets_received"], 0)

    def test_tx_and_rx_packet_history_ordering(self):
        class MockFullDuplexEngine:
            AUDIO_HARDWARE_AVAILABLE = True

            def transmit_text(self, message: str, seq_num: int = None):
                return {
                    "success": True,
                    "message": message,
                    "seq_num": 1,
                    "crc_16": 0x1111,
                    "crc_hex": "0x1111",
                    "duration_sec": 0.4,
                    "bytes_sent": len(message),
                    "error": None
                }

            def receive_text(self, timeout_seconds: float = 10.0):
                return "Decoded Inbound Frame", {
                    "success": True,
                    "message": "Decoded Inbound Frame",
                    "seq_num": 2,
                    "crc_valid": True,
                    "received_crc": 0x2222,
                    "correlation_ratio": 15.0,
                    "error": None
                }

        engine_adapter.register_acoustic_engine(MockFullDuplexEngine())

        # 1. Transmit
        self.client.post("/api/transmit", json={"message": "Outbound Packet"})
        # 2. Receive
        self.client.post("/api/receive", json={"timeout_seconds": 2.0})

        status = self.client.get("/api/status").json()
        self.assertEqual(status["metrics"]["packets_sent"], 1)
        self.assertEqual(status["metrics"]["packets_received"], 1)
        self.assertEqual(status["last_transmitted"], "Outbound Packet")
        self.assertEqual(status["last_received"], "Decoded Inbound Frame")
        self.assertEqual(status["recent_crc_status"], "VALID")

        # Check packet history ordering & direction
        packets = status["recent_packets"]
        self.assertEqual(len(packets), 2)
        self.assertEqual(packets[0]["payload_text"], "Outbound Packet")
        self.assertEqual(packets[0]["seq_num"], 1)
        self.assertEqual(packets[0]["direction"], "TX")
        self.assertEqual(packets[1]["payload_text"], "Decoded Inbound Frame")
        self.assertEqual(packets[1]["seq_num"], 2)
        self.assertEqual(packets[1]["direction"], "RX")

    def test_network_performance_analytics_computations(self):
        """Verifies accurate calculation of CRC error rate, retransmission rate, latency and throughput averages."""
        class MockAnalyticsEngine:
            AUDIO_HARDWARE_AVAILABLE = True
            def transmit_text(self, message, seq_num=None):
                return {
                    "success": True,
                    "seq_num": 10,
                    "crc_hex": "0xAAAA",
                    "bytes_sent": len(message.encode("utf-8")),
                    "duration_sec": 0.5,
                    "error": None
                }
            def receive_text(self, timeout_seconds=10.0):
                # Will be overridden in test
                pass

        mock = MockAnalyticsEngine()
        engine_adapter.register_acoustic_engine(mock)

        # 1. Successful transmit
        tx_resp = self.client.post("/api/transmit", json={"message": "Analytics Payload 1"})
        self.assertEqual(tx_resp.status_code, 200)

        # 2. Successful receive
        mock.receive_text = lambda timeout_seconds=10.0: ("Analytics RX 1", {
            "success": True,
            "seq_num": 11,
            "crc_valid": True,
            "received_crc": 0xBBBB,
            "correlation_ratio": 12.0,
            "length_bytes": 14,
            "error": None
        })
        rx_resp1 = self.client.post("/api/receive", json={"timeout_seconds": 2.0})
        self.assertEqual(rx_resp1.status_code, 200)

        # 3. Corrupted receive
        mock.receive_text = lambda timeout_seconds=10.0: (None, {
            "success": False,
            "detected": True,
            "crc_valid": False,
            "seq_num": 12,
            "received_crc": 0xCCCC,
            "correlation_ratio": 9.5,
            "length_bytes": 14,
            "raw_text": "CorruptedData",
            "error": "CRC-16 mismatch"
        })
        rx_resp2 = self.client.post("/api/receive", json={"timeout_seconds": 2.0})
        self.assertEqual(rx_resp2.status_code, 200)

        status = self.client.get("/api/status").json()
        metrics = status["metrics"]

        self.assertEqual(metrics["packets_sent"], 1)
        self.assertEqual(metrics["packets_received"], 2)
        self.assertEqual(metrics["crc_valid_count"], 1)
        self.assertEqual(metrics["crc_error_count"], 1)
        # CRC Error Rate = 1 error / (1 valid + 1 error) * 100% = 50.0%
        self.assertEqual(metrics["crc_error_rate"], 50.0)
        # Retransmission Rate = 1 retransmission / 1 sent * 100% = 100.0%
        self.assertEqual(metrics["retransmission_rate"], 100.0)
        # Latency and throughput metrics
        self.assertGreater(metrics["average_latency_ms"], 0)
        self.assertGreater(metrics["average_data_rate_bps"], 0)
        self.assertGreaterEqual(metrics["peak_data_rate_bps"], metrics["average_data_rate_bps"])

        # Check packet records direction and metrics
        packets = status["recent_packets"]
        self.assertEqual(len(packets), 3)
        self.assertEqual(packets[0]["direction"], "TX")
        self.assertEqual(packets[1]["direction"], "RX")
        self.assertEqual(packets[2]["direction"], "RX")
        self.assertTrue(packets[1]["crc_valid"])
        self.assertFalse(packets[2]["crc_valid"])


if __name__ == "__main__":
    unittest.main()

