# -*- coding: utf-8 -*-

"""Implementation of DistMult."""

from typing import Optional

import torch
import torch.autograd
from torch import nn
from torch.nn import functional

from ..base import BaseModule
from ..init import embedding_xavier_uniform_
from ...triples import TriplesFactory
from ...typing import Loss

__all__ = ['DistMult']


class DistMult(BaseModule):
    """An implementation of DistMult from [yang2014]_.

    This model simplifies RESCAL by restricting matrices representing relations as diagonal matrices.

    Note:
      - For FB15k, Yang *et al.* report 2 negatives per each positive.

    .. seealso::

       - OpenKE `implementation of DistMult <https://github.com/thunlp/OpenKE/blob/master/models/DistMult.py>`_

    """

    def __init__(
        self,
        triples_factory: TriplesFactory,
        embedding_dim: int = 50,
        entity_embeddings: Optional[nn.Embedding] = None,
        relation_embeddings: Optional[nn.Embedding] = None,
        criterion: Optional[Loss] = None,
        preferred_device: Optional[str] = None,
        random_seed: Optional[int] = None,
        init: bool = True,
    ) -> None:
        """Initialize the model."""
        if criterion is None:
            criterion = nn.MarginRankingLoss(margin=1., reduction='mean')

        super().__init__(
            triples_factory=triples_factory,
            embedding_dim=embedding_dim,
            entity_embeddings=entity_embeddings,
            criterion=criterion,
            preferred_device=preferred_device,
            random_seed=random_seed,
        )
        self.relation_embeddings = relation_embeddings

        if init:
            self.init_empty_weights_()

    def init_empty_weights_(self):  # noqa: D102
        if self.entity_embeddings is None:
            self.entity_embeddings = nn.Embedding(self.num_entities, self.embedding_dim)
            embedding_xavier_uniform_(self.entity_embeddings)

        if self.relation_embeddings is None:
            self.relation_embeddings = nn.Embedding(self.num_relations, self.embedding_dim)
            embedding_xavier_uniform_(self.relation_embeddings)
            # Initialise relation embeddings to unit length
            functional.normalize(self.relation_embeddings.weight.data, out=self.relation_embeddings.weight.data)

        return self

    def clear_weights_(self):  # noqa: D102
        self.entity_embeddings = None
        self.relation_embeddings = None
        return self

    def _apply_forward_constraints_if_necessary(self) -> None:
        # Normalize embeddings of entities
        if not self.forward_constraint_applied:
            functional.normalize(self.entity_embeddings.weight.data, out=self.entity_embeddings.weight.data)
            self.forward_constraint_applied = True

    @staticmethod
    def interaction_function(
        h: torch.FloatTensor,
        r: torch.FloatTensor,
        t: torch.FloatTensor,
    ) -> torch.FloatTensor:
        """Evaluate the interaction function for given embeddings.

        The embeddings have to be in a broadcastable shape.

        WARNING: Does not ensure forward constraints.

        :param h: shape: (..., e)
            Head embeddings.
        :param r: shape: (..., e)
            Relation embeddings.
        :param t: shape: (..., e)
            Tail embeddings.

        :return: shape: (...)
            The scores.
        """
        # ComplEx space bilinear product (equivalent to HolE)
        # *: Elementwise multiplication
        return torch.sum(h * r * t, dim=-1)

    def forward_owa(self, batch: torch.LongTensor) -> torch.FloatTensor:  # noqa: D102
        # Normalize embeddings
        self._apply_forward_constraints_if_necessary()

        # Get embeddings
        h = self.entity_embeddings(batch[:, 0])
        r = self.relation_embeddings(batch[:, 1])
        t = self.entity_embeddings(batch[:, 2])

        # Compute score
        scores = self.interaction_function(h=h, r=r, t=t).view(-1, 1)

        return scores

    def forward_cwa(self, batch: torch.LongTensor) -> torch.FloatTensor:  # noqa: D102
        # Normalize embeddings
        self._apply_forward_constraints_if_necessary()

        # Get embeddings
        h = self.entity_embeddings(batch[:, 0]).view(-1, 1, self.embedding_dim)
        r = self.relation_embeddings(batch[:, 1]).view(-1, 1, self.embedding_dim)
        t = self.entity_embeddings.weight.view(1, -1, self.embedding_dim)

        # Rank against all entities
        scores = self.interaction_function(h=h, r=r, t=t)

        return scores

    def forward_inverse_cwa(self, batch: torch.LongTensor) -> torch.FloatTensor:  # noqa: D102
        # Normalize embeddings
        self._apply_forward_constraints_if_necessary()

        # Get embeddings
        h = self.entity_embeddings.weight.view(1, -1, self.embedding_dim)
        r = self.relation_embeddings(batch[:, 0]).view(-1, 1, self.embedding_dim)
        t = self.entity_embeddings(batch[:, 1]).view(-1, 1, self.embedding_dim)

        # Rank against all entities
        scores = self.interaction_function(h=h, r=r, t=t)

        return scores
