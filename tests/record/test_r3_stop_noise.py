"""R3 驗證缺陷 D1：沒有 record.pid 時 meeting record stop 回 3，stderr 不得夾帶 shell 的「No such file」錯誤行。"""
import unittest

from tests.record._helpers import Sandbox


class TestR3StopNoise(unittest.TestCase):
    def test_stop_without_pid_file_is_clean(self):
        sb = Sandbox(self)
        self.assertFalse((sb.home / "record.pid").exists())
        r = sb.meeting("record", "stop")
        self.assertEqual(r.returncode, 3, f"沒有錄製時 stop 應回 3\nstderr:{r.stderr}")
        self.assertIn("沒有錄製在跑", r.stderr)
        self.assertNotIn("No such file", r.stderr, f"stderr 不應有 shell 錯誤行：{r.stderr}")


if __name__ == "__main__":
    unittest.main()
