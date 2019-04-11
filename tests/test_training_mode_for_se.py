# -*- coding: utf-8 -*-

"""Test training mode for SE."""

import logging
import os
import tempfile
import unittest

import numpy as np

import pykeen
import pykeen.constants as pkc
from tests.constants import RESOURCES_DIRECTORY

logging.basicConfig(level=logging.INFO)
logging.getLogger('pykeen').setLevel(logging.INFO)

CONFIG = dict(
    training_set_path=os.path.join(RESOURCES_DIRECTORY, 'data', 'rdf.nt'),
    execution_mode=pkc.TRAINING_MODE,
    random_seed=0,
    kg_embedding_model_name=pkc.SE_NAME,
    embedding_dim=50,
    scoring_function=1,  # corresponds to L1
    normalization_of_entities=2,  # corresponds to L2
    margin_loss=1,
    learning_rate=0.01,
    num_epochs=20,
    batch_size=64,
    preferred_device='cpu'
)


class TestTrainingModeForSE(unittest.TestCase):
    """Test that SE can be trained and evaluated correctly in training mode."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.dir.cleanup()

    def test_training(self):
        """Test that SE is trained correctly in training mode."""
        results = pykeen.run(
            config=CONFIG,
            output_directory=self.dir.name,
        )

        self.assertIsNotNone(results)
        self.assertIsNotNone(results.results[pkc.TRAINED_MODEL])
        self.assertIsNotNone(results.results[pkc.LOSSES])
        self.assertIsNotNone(results.results[pkc.ENTITY_TO_EMBEDDING])
        self.assertNotIn(pkc.EVAL_SUMMARY, results.results)
        self.assertIsNotNone(results.results[pkc.ENTITY_TO_ID])
        self.assertIsNotNone(results.results[pkc.RELATION_TO_ID])
        self.assertIsNotNone(results.results[pkc.FINAL_CONFIGURATION])

    def test_evaluation(self):
        """Test that SE is trained and evaluated correctly in training mode. """
        # 10 % of training set will be used as a test set
        config = CONFIG.copy()
        config[pkc.TEST_SET_RATIO] = 0.1
        config[pkc.FILTER_NEG_TRIPLES] = True

        results = pykeen.run(
            config=config,
            output_directory=self.dir.name,
        )

        self.assertIsNotNone(results)
        self.assertIsNotNone(results.results[pkc.TRAINED_MODEL])
        self.assertIsNotNone(results.results[pkc.LOSSES])
        self.assertIsNotNone(results.results[pkc.ENTITY_TO_EMBEDDING])
        self.assertIn(pkc.EVAL_SUMMARY, results.results)
        self.assertIn(pkc.MEAN_RANK, results.results[pkc.EVAL_SUMMARY])
        self.assertEqual(type(results.results[pkc.EVAL_SUMMARY][pkc.MEAN_RANK]), float)
        self.assertIn(pkc.HITS_AT_K, results.results[pkc.EVAL_SUMMARY])
        self.assertEqual(type(results.results[pkc.EVAL_SUMMARY][pkc.HITS_AT_K][1]), np.float64)
        self.assertEqual(type(results.results[pkc.EVAL_SUMMARY][pkc.HITS_AT_K][3]), np.float64)
        self.assertEqual(type(results.results[pkc.EVAL_SUMMARY][pkc.HITS_AT_K][5]), np.float64)
        self.assertEqual(type(results.results[pkc.EVAL_SUMMARY][pkc.HITS_AT_K][10]), np.float64)
        self.assertIsNotNone(results.results[pkc.ENTITY_TO_ID])
        self.assertIsNotNone(results.results[pkc.RELATION_TO_ID])
        self.assertIsNotNone(results.results[pkc.FINAL_CONFIGURATION])