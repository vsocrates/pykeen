# -*- coding: utf-8 -*-
import logging
import timeit
from collections import OrderedDict

import numpy as np
import torch
import torch.optim as optim
from sklearn.model_selection import train_test_split

from utilities.constants import READER, KG_EMBEDDING_MODEL, NUM_ENTITIES, NUM_RELATIONS, EVALUATOR, PREFERRED_DEVICE, \
    GPU, CPU
from utilities.pipeline_helper import get_reader, get_kg_embedding_model, create_triples_and_mappings, \
    create_negative_triples, get_evaluator

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class Pipeline(object):

    def __init__(self, config):
        self.config = config
        self.corpus_reader = None
        self.kg_embedding_model = None
        self.eval_module = None
        self.device = torch.device(
            'cuda:0' if torch.cuda.is_available() and self.config[PREFERRED_DEVICE] == GPU else 'cpu')

    def start_pipeline(self, learning_rate, num_epochs, ratio_of_neg_triples, batch_size, ratio_test_data, seed):
        """
        :return:
        """

        # Initialize reader
        log.info("-------------Read Corpus-------------")
        reader_config = self.config[READER]
        self.corpus_reader = get_reader(config=reader_config)
        path_to_kg = self.corpus_reader.retreive_knowledge_graph()

        pos_tripels_of_ids, entity_to_id, rel_to_id = create_triples_and_mappings(path_to_kg=path_to_kg)

        # Initialize KG embedding model
        kb_embedding_model_config = self.config[KG_EMBEDDING_MODEL]
        kb_embedding_model_config[NUM_ENTITIES] = len(entity_to_id)
        kb_embedding_model_config[NUM_RELATIONS] = len(rel_to_id)
        self.kg_embedding_model = get_kg_embedding_model(config=kb_embedding_model_config)

        log.info("-------------Create negative triples-------------")
        neg_triples = create_negative_triples(seed=seed, pos_triples=pos_tripels_of_ids,
                                              ratio_of_negative_triples=ratio_of_neg_triples)

        train_pos, test_pos, train_neg, test_neg = train_test_split(pos_tripels_of_ids, neg_triples,
                                                                    test_size=ratio_test_data, random_state=seed)

        log.info("-------------Train KG Embeddings-------------")
        self._train(learning_rate, num_epochs, batch_size, train_pos, train_neg, seed)

        # Initialize KG evaluator
        evaluator_config = self.config[EVALUATOR]
        evaluator = get_evaluator(config=evaluator_config)

        log.info("-------------Start Evaluation-------------")
        eval_result, metric_string = evaluator.start_evaluation(test_data=test_pos,
                                                                kg_embedding_model=self.kg_embedding_model)

        # Prepare Output
        eval_summary = OrderedDict()
        eval_summary[metric_string] = eval_result
        id_to_entity = {value: key for key, value in entity_to_id.items()}
        id_to_rel = {value: key for key, value in rel_to_id.items()}
        entity_to_embedding = {id_to_entity[id]: embedding.detach().numpy() for id, embedding in
                               enumerate(self.kg_embedding_model.entities_embeddings.weight)}
        relation_to_embedding = {id_to_rel[id]: embedding.detach().numpy() for id, embedding in
                                 enumerate(self.kg_embedding_model.relation_embeddings.weight)}

        return self.kg_embedding_model, eval_summary, entity_to_embedding, relation_to_embedding

    def _train(self, learning_rate, num_epochs, batch_size, pos_triples, neg_triples, seed):

        np.random.seed(seed=seed)
        indices = np.arange(pos_triples.shape[0])
        np.random.shuffle(indices)
        pos_triples = pos_triples[indices]
        neg_triples = neg_triples[indices]

        self.kg_embedding_model = self.kg_embedding_model.to(self.device)

        optimizer = optim.SGD(self.kg_embedding_model.parameters(), lr=learning_rate)

        total_loss = 0

        num_instances = pos_triples.shape[0]
        # num_batches = num_instances // num_epochs

        log.info('****Run Model On %s****' % str(self.device).upper())

        for epoch in range(num_epochs):
            start = timeit.default_timer()
            for step in range(num_instances):
                pos_triple = torch.tensor(pos_triples[step], dtype=torch.long, device=self.device)
                neg_triple = torch.tensor(neg_triples[step], dtype=torch.long, device=self.device)

                # Recall that torch *accumulates* gradients. Before passing in a
                # new instance, you need to zero out the gradients from the old
                # instance
                # model.zero_grad()
                # When to use model.zero_grad() and when optimizer.zero_grad() ?
                optimizer.zero_grad()

                loss = self.kg_embedding_model(pos_triple, neg_triple)

                loss.backward()
                optimizer.step()

                # Get the Python number from a 1-element Tensor by calling tensor.item()
                total_loss += loss.item()

            stop = timeit.default_timer()
            log.info("Epoch %s took %s seconds \n" % (str(epoch), str(round(stop - start))))
