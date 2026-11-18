import unittest

from journal.security import hash_password, verify_password


class SecurityTests(unittest.TestCase):
    def test_correct_password(self):
        self.assertTrue(verify_password("secret123", hash_password("secret123")))

    def test_wrong_password(self):
        self.assertFalse(verify_password("wrong", hash_password("secret123")))

    def test_salt_makes_hashes_different(self):
        self.assertNotEqual(hash_password("secret123"), hash_password("secret123"))

    def test_bad_stored_value(self):
        self.assertFalse(verify_password("x", "broken"))
