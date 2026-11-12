"""The assistant's local recommendation path must not load a model."""
import unittest
from unittest.mock import patch

from app import manga_vector


class AssistantWithoutEmbeddingsTests(unittest.TestCase):
    def test_query_encoding_does_not_load_model(self):
        with patch.object(manga_vector, "_model", None), \
                patch.object(manga_vector, "is_model_cached", side_effect=AssertionError("model cache accessed")):
            self.assertIsNone(manga_vector.encode_query("温馨漫画"))
