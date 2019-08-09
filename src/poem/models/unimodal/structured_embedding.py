# -*- coding: utf-8 -*-

"""Implementation of structured model (SE)."""

import logging
from typing import Optional

import numpy as np
import torch
import torch.autograd
from torch import nn
from torch.nn import functional

from ..base import BaseModule
from ...instance_creation_factories import TriplesFactory
from ...typing import OptionalLoss

__all__ = [
    'StructuredEmbedding',
]

log = logging.getLogger(__name__)


class StructuredEmbedding(BaseModule):
    """An implementation of Structured Embedding (SE) from [bordes2011]_.

    This model projects different matrices for each relation head and tail entity.
    """

    margin_ranking_loss_size_average: bool = True

    def __init__(
            self,
            triples_factory: TriplesFactory,
            embedding_dim: int = 50,
            left_relation_embeddings: Optional[nn.Embedding] = None,
            right_relation_embeddings: Optional[nn.Embedding] = None,
            scoring_fct_norm: int = 1,
            criterion: OptionalLoss = None,
            preferred_device: Optional[str] = None,
            random_seed: Optional[int] = None,
    ) -> None:
        if criterion is None:
            criterion = nn.MarginRankingLoss(margin=1., reduction='mean')

        super().__init__(
            triples_factory=triples_factory,
            embedding_dim=embedding_dim,
            criterion=criterion,
            preferred_device=preferred_device,
            random_seed=random_seed,
        )

        # Embeddings
        self.scoring_fct_norm = scoring_fct_norm

        self.left_relation_embeddings = left_relation_embeddings
        self.right_relation_embeddings = right_relation_embeddings

        if None in [self.left_relation_embeddings, self.right_relation_embeddings]:
            self._init_embeddings()

    def _init_embeddings(self):
        super()._init_embeddings()
        self.left_relation_embeddings = nn.Embedding(self.num_relations, self.embedding_dim ** 2)
        self.right_relation_embeddings = nn.Embedding(self.num_relations, self.embedding_dim ** 2)

        init_bound = 6 / np.sqrt(self.embedding_dim)
        nn.init.uniform_(
            self.entity_embeddings.weight.data,
            a=-init_bound,
            b=+init_bound,
        )
        nn.init.uniform_(
            self.left_relation_embeddings.weight.data,
            a=-init_bound,
            b=+init_bound,
        )
        nn.init.uniform_(
            self.right_relation_embeddings.weight.data,
            a=-init_bound,
            b=+init_bound,
        )

        # Initialise left relation embeddings to unit length
        functional.normalize(self.left_relation_embeddings.weight.data, out=self.left_relation_embeddings.weight.data)
        functional.normalize(self.right_relation_embeddings.weight.data, out=self.right_relation_embeddings.weight.data)

    def _apply_forward_constraints_if_necessary(self):
        if not self.forward_constraint_applied:
            # Normalise embeddings of entities
            functional.normalize(self.entity_embeddings.weight.data, out=self.entity_embeddings.weight.data)
            self.forward_constraint_applied = True

    def forward_owa(self, batch: torch.Tensor) -> torch.Tensor:
        """Forward pass for training with the OWA."""
        self._apply_forward_constraints_if_necessary()

        # Get embeddings
        h = self.entity_embeddings(batch[:, 0]).view(-1, self.embedding_dim, 1)
        rel_h = self.left_relation_embeddings(batch[:, 1]).view(-1, self.embedding_dim, self.embedding_dim)
        rel_t = self.right_relation_embeddings(batch[:, 1]).view(-1, self.embedding_dim, self.embedding_dim)
        t = self.entity_embeddings(batch[:, 2]).view(-1, self.embedding_dim, 1)

        # Project entities
        proj_h = self._project_entities(entity_embeddings=h, relation_embeddings=rel_h)
        proj_t = self._project_entities(entity_embeddings=t, relation_embeddings=rel_t)

        scores = -torch.norm(proj_h - proj_t, dim=1, p=self.scoring_fct_norm)
        return scores

    def forward_cwa(self, batch: torch.Tensor) -> torch.Tensor:
        """Forward pass using right side (object) prediction for training with the CWA."""
        self._apply_forward_constraints_if_necessary()

        # Get embeddings
        h = self.entity_embeddings(batch[:, 0]).view(-1, self.embedding_dim, 1)
        rel_h = self.left_relation_embeddings(batch[:, 1]).view(-1, self.embedding_dim, self.embedding_dim)
        rel_t = self.right_relation_embeddings(batch[:, 1]).view(-1, 1, self.embedding_dim, self.embedding_dim)
        t = self.entity_embeddings.weight.view(1, -1, self.embedding_dim, 1)

        # Project entities
        proj_h = self._project_entities(entity_embeddings=h, relation_embeddings=rel_h)
        proj_t = self._project_entities(entity_embeddings=t, relation_embeddings=rel_t)

        scores = -torch.norm(proj_h[:, None, :, 0] - proj_t[:, :, :, 0], dim=-1, p=self.scoring_fct_norm)

        return scores

    def forward_inverse_cwa(self, batch: torch.Tensor) -> torch.Tensor:
        """Forward pass using left side (subject) prediction for training with the CWA."""
        self._apply_forward_constraints_if_necessary()

        # Get embeddings
        h = self.entity_embeddings.weight.view(1, -1, self.embedding_dim, 1)
        rel_h = self.left_relation_embeddings(batch[:, 0]).view(-1, 1, self.embedding_dim, self.embedding_dim)
        rel_t = self.right_relation_embeddings(batch[:, 0]).view(-1, self.embedding_dim, self.embedding_dim)
        t = self.entity_embeddings(batch[:, 1]).view(-1, self.embedding_dim, 1)

        # Project entities
        proj_h = self._project_entities(entity_embeddings=h, relation_embeddings=rel_h)
        proj_t = self._project_entities(entity_embeddings=t, relation_embeddings=rel_t)

        scores = -torch.norm(proj_h[:, :, :, 0] - proj_t[:, None, :, 0], dim=-1, p=self.scoring_fct_norm)

        return scores

    def _project_entities(
            self,
            entity_embeddings,
            relation_embeddings,
    ):
        entity_embeddings = entity_embeddings
        projected_entity_embs = torch.matmul(relation_embeddings, entity_embeddings)
        return projected_entity_embs
