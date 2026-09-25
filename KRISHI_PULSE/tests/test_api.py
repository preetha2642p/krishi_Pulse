"""Integration tests for the Flask API, run against a temp data directory."""
import sys, os, json, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        import krishi_pulse.store as store
        store._DATA_DIR = self.tmp
        store._FARMS_FILE = os.path.join(self.tmp, "farms.json")
        store._READINGS_FILE = os.path.join(self.tmp, "readings.json")
        from krishi_pulse.app import app
        self.client = app.test_client()

    def test_full_flow(self):
        r = self.client.post("/api/farms", json={
            "name": "API test plot", "crop": "maize", "soil_type": "black_clay",
            "sowing_date": "2026-07-01", "area_acres": 2, "irrigation": "furrow"})
        self.assertEqual(r.status_code, 201)
        farm_id = r.get_json()["id"]

        r = self.client.get("/api/farms/%s/advice" % farm_id)
        self.assertEqual(r.status_code, 409)  # no reading yet

        r = self.client.post(f"/api/farms/{farm_id}/readings", json={"moisture_pct": 18.0, "ph": 6.5})
        self.assertEqual(r.status_code, 201)

        r = self.client.get(f"/api/farms/{farm_id}/advice")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertIn(body["primary"]["action"], ("IRRIGATE", "WAIT", "ACT"))
        self.assertTrue(len(body["primary"]["steps"]) > 0)

    def test_unknown_crop_rejected(self):
        r = self.client.post("/api/farms", json={
            "name": "Bad crop", "crop": "durian", "soil_type": "sandy",
            "sowing_date": "2026-01-01"})
        self.assertEqual(r.status_code, 400)

    def test_pest_detection_flow(self):
        r = self.client.get("/api/pests?crop=maize")
        self.assertEqual(r.status_code, 200)
        signs = r.get_json()["pests"][0]["symptoms"]
        r = self.client.post("/api/pest-detection", json={
            "crop": "maize", "symptoms": ["windowpanes_on_leaves", "frass_in_whorl"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["matches"][0]["key"], "fall_armyworm")
        r = self.client.post("/api/pest-detection", json={"crop": "maize", "symptoms": []})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
