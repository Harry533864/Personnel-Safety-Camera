import tempfile
import unittest
import os
from pathlib import Path

os.environ.setdefault("CAM_AUTO_START", "0")

from app.services.config_service import ConfigService


class ConfigServiceTest(unittest.TestCase):
    def test_update_mutates_and_persists_yaml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "AIConfig.yaml"
            path.write_text("model:\n  detect_enable: false\n", encoding="utf-8")
            service = ConfigService(path)

            def mutate(cfg):
                cfg.setdefault("model", {})["detect_enable"] = True
                return "changed"

            cfg, result = service.update(mutate)

            self.assertEqual(result, "changed")
            self.assertTrue(cfg["model"]["detect_enable"])
            self.assertTrue(service.read()["model"]["detect_enable"])


if __name__ == "__main__":
    unittest.main()
