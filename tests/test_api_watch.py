import importlib
import sys
import types
import unittest


ratio1 = types.ModuleType("ratio1")
ratio1.Session = object
ratio1.CustomPluginTemplate = object
sys.modules["ratio1"] = ratio1

bot = importlib.import_module("ratio1_tg_bot")


class FakeResponse:
  def __init__(self, status_code):
    self.status_code = status_code


class FakeRequests:
  def __init__(self, status_codes=None, exceptions=None):
    self.status_codes = list(status_codes or [200])
    self.exceptions = list(exceptions or [])
    self.calls = []

  def get(self, url, timeout=None):
    self.calls.append((url, timeout))
    if self.exceptions:
      raise self.exceptions.pop(0)
    if len(self.status_codes) > 1:
      return FakeResponse(self.status_codes.pop(0))
    return FakeResponse(self.status_codes[0])


class FakeEpochManager:
  def get_last_sync_epoch(self):
    return 1


class FakeNetmon:
  def __init__(self):
    self.epoch_manager = FakeEpochManager()
    self.available_nodes_prefixed = []

  def network_node_is_online(self, node):
    return True

  def network_node_eeid(self, node):
    return node


class FakeBC:
  def is_valid_eth_address(self, address):
    return address.startswith("0x") and len(address) == 42

  def eth_addr_to_checksum_address(self, address):
    return address

  def eth_addr_to_internal_addr(self, address):
    return address

  def get_wallet_nodes(self, wallet):
    return []


class FakePlugin:
  cfg_chat_id = "community-chat"
  cfg_version = "test"
  cfg_admins = []
  cfg_offline_node_min_seens = 2
  ee_id = "fake-ee"

  def __init__(self, requests=None, disk=None):
    self.obj_cache = {}
    self.requests = requests or FakeRequests()
    self.disk = disk or {}
    self.saved = []
    self.sent_messages = []
    self.now = 1000
    self.netmon = FakeNetmon()
    self.bc = FakeBC()

  def diskapi_load_pickle_from_data(self, filename):
    return self.disk.get(filename)

  def diskapi_save_pickle_to_data(self, data, filename):
    self.disk[filename] = data
    self.saved.append((filename, data))

  def time(self):
    return self.now

  def send_message_to_user(self, user_id, text):
    self.sent_messages.append((user_id, text))

  def P(self, *args, **kwargs):
    pass


class ApiWatchUrlTests(unittest.TestCase):
  def test_normalizes_api_url_and_default_health_endpoint(self):
    self.assertEqual(
      bot.build_health_url("api.example.com/", "yes"),
      ("https://api.example.com", "/health", "https://api.example.com/health"),
    )
    self.assertEqual(
      bot.build_health_url("https://api.example.com/v1", "status"),
      ("https://api.example.com/v1", "/status", "https://api.example.com/v1/status"),
    )

  def test_rejects_invalid_api_urls(self):
    for api_url in ["", "not a url", "ftp://example.com", "http://", "https://exa mple.com"]:
      with self.subTest(api_url=api_url):
        self.assertIsNone(bot.normalize_api_base_url(api_url))

  def test_rejects_absolute_health_endpoint_url(self):
    self.assertEqual(
      bot.build_health_url("https://api.example.com", "https://evil.example.com/health"),
      (None, None, None),
    )


class WatchApiCommandTests(unittest.TestCase):
  def test_watch_api_prompts_for_default_health_endpoint(self):
    plugin = FakePlugin()

    response = bot.reply(plugin, "/watch_api https://api.example.com", "u1", "1")

    self.assertIn("Default health endpoint is /health", response)
    self.assertEqual(
      plugin.obj_cache["ratio1_pending_api_watch"]["1"]["api_url"],
      "https://api.example.com",
    )

  def test_watch_api_rejects_invalid_url_without_requesting_health(self):
    plugin = FakePlugin()

    response = bot.reply(plugin, "/watch_api not a url", "u1", "1")

    self.assertIn("Invalid API URL", response)
    self.assertEqual(plugin.requests.calls, [])
    self.assertEqual(plugin.obj_cache["ratio1_pending_api_watch"], {})

  def test_confirms_default_endpoint_and_persists_watch(self):
    plugin = FakePlugin()
    bot.reply(plugin, "/watch_api https://api.example.com", "u1", "1")

    response = bot.reply(plugin, "yes", "u1", "1")

    self.assertEqual(
      response,
      "You are now watching API https://api.example.com using health endpoint /health.",
    )
    self.assertEqual(plugin.requests.calls, [("https://api.example.com/health", 10)])
    self.assertEqual(plugin.obj_cache["ratio1_pending_api_watch"], {})
    watched_api = plugin.obj_cache["ratio1_watched_apis"]["https://api.example.com/health"]
    self.assertEqual(watched_api["subscribers"], ["1"])
    self.assertTrue(watched_api["is_online"])
    self.assertEqual(plugin.saved[-1][0], "ratio1_watched_apis_data.pkl")

  def test_custom_endpoint_is_used(self):
    plugin = FakePlugin()
    bot.reply(plugin, "/watch_api https://api.example.com", "u1", "1")

    response = bot.reply(plugin, "/status/live", "u1", "1")

    self.assertEqual(
      response,
      "You are now watching API https://api.example.com using health endpoint /status/live.",
    )
    self.assertIn("https://api.example.com/status/live", plugin.obj_cache["ratio1_watched_apis"])

  def test_failed_health_check_does_not_add_watch_and_keeps_pending_endpoint(self):
    plugin = FakePlugin(requests=FakeRequests(status_codes=[503]))
    bot.reply(plugin, "/watch_api https://api.example.com", "u1", "1")

    response = bot.reply(plugin, "yes", "u1", "1")

    self.assertIn("Could not add API watch", response)
    self.assertEqual(plugin.obj_cache["ratio1_watched_apis"], {})
    self.assertIn("1", plugin.obj_cache["ratio1_pending_api_watch"])

  def test_two_users_subscribe_to_one_global_api_watch(self):
    plugin = FakePlugin()

    bot.reply(plugin, "/watch_api https://api.example.com", "u1", "1")
    bot.reply(plugin, "yes", "u1", "1")
    bot.reply(plugin, "/watch_api https://api.example.com/", "u2", "2")
    bot.reply(plugin, "/health", "u2", "2")

    watched_apis = plugin.obj_cache["ratio1_watched_apis"]
    self.assertEqual(list(watched_apis.keys()), ["https://api.example.com/health"])
    self.assertEqual(watched_apis["https://api.example.com/health"]["subscribers"], ["1", "2"])

  def test_watchlist_includes_wallets_and_apis(self):
    plugin = FakePlugin()
    plugin.obj_cache["ratio1_watched_wallets"] = {"1": ["0x1111111111111111111111111111111111111111"]}
    plugin.obj_cache["ratio1_watched_apis"] = {
      "https://api.example.com/health": {
        "api_url": "https://api.example.com",
        "health_url": "https://api.example.com/health",
        "subscribers": ["1"],
        "is_online": True,
      }
    }

    response = bot.reply(plugin, "/watchlist", "u1", "1")

    self.assertIn("0x1111111111111111111111111111111111111111", response)
    self.assertIn("https://api.example.com/health", response)
    self.assertIn("🟢", response)


class ApiMonitoringLoopTests(unittest.TestCase):
  def test_loop_notifies_all_subscribers_when_api_goes_offline(self):
    plugin = FakePlugin(requests=FakeRequests(status_codes=[503]))
    plugin.obj_cache["ratio1_epoch_review_already_read"] = True
    plugin.obj_cache["ratio1_epoch_review"] = {1: True}
    plugin.obj_cache["ratio1_watched_wallets"] = {}
    plugin.obj_cache["ratio1_node_alerts"] = {}
    plugin.obj_cache["ratio1_watched_wallets_loops_delay"] = 0
    plugin.obj_cache["ratio1_watched_apis_loops_delay"] = bot.API_WATCH_CHECK_LOOPS
    plugin.obj_cache["ratio1_watched_apis"] = {
      "https://api.example.com/health": {
        "api_url": "https://api.example.com",
        "health_endpoint": "/health",
        "health_url": "https://api.example.com/health",
        "subscribers": ["1", "2"],
        "is_online": True,
      }
    }

    bot.loop_processing(plugin)

    self.assertEqual(len(plugin.sent_messages), 2)
    self.assertEqual([message[0] for message in plugin.sent_messages], ["1", "2"])
    self.assertIn("is offline", plugin.sent_messages[0][1])
    self.assertFalse(
      plugin.obj_cache["ratio1_watched_apis"]["https://api.example.com/health"]["is_online"]
    )

  def test_loop_notifies_subscribers_when_api_recovers(self):
    plugin = FakePlugin(requests=FakeRequests(status_codes=[200]))
    plugin.obj_cache["ratio1_epoch_review_already_read"] = True
    plugin.obj_cache["ratio1_epoch_review"] = {1: True}
    plugin.obj_cache["ratio1_watched_wallets"] = {}
    plugin.obj_cache["ratio1_node_alerts"] = {}
    plugin.obj_cache["ratio1_watched_wallets_loops_delay"] = 0
    plugin.obj_cache["ratio1_watched_apis_loops_delay"] = bot.API_WATCH_CHECK_LOOPS
    plugin.obj_cache["ratio1_watched_apis"] = {
      "https://api.example.com/health": {
        "api_url": "https://api.example.com",
        "health_endpoint": "/health",
        "health_url": "https://api.example.com/health",
        "subscribers": ["1"],
        "is_online": False,
      }
    }

    bot.loop_processing(plugin)

    self.assertEqual(len(plugin.sent_messages), 1)
    self.assertIn("back online", plugin.sent_messages[0][1])
    self.assertTrue(
      plugin.obj_cache["ratio1_watched_apis"]["https://api.example.com/health"]["is_online"]
    )

  def test_loop_does_not_notify_when_api_state_is_unchanged(self):
    plugin = FakePlugin(requests=FakeRequests(status_codes=[200]))
    plugin.obj_cache["ratio1_epoch_review_already_read"] = True
    plugin.obj_cache["ratio1_epoch_review"] = {1: True}
    plugin.obj_cache["ratio1_watched_wallets"] = {}
    plugin.obj_cache["ratio1_node_alerts"] = {}
    plugin.obj_cache["ratio1_watched_wallets_loops_delay"] = 0
    plugin.obj_cache["ratio1_watched_apis_loops_delay"] = bot.API_WATCH_CHECK_LOOPS
    plugin.obj_cache["ratio1_watched_apis"] = {
      "https://api.example.com/health": {
        "api_url": "https://api.example.com",
        "health_endpoint": "/health",
        "health_url": "https://api.example.com/health",
        "subscribers": ["1"],
        "is_online": True,
      }
    }

    bot.loop_processing(plugin)

    self.assertEqual(plugin.sent_messages, [])


if __name__ == "__main__":
  unittest.main()
