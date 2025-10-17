# Copyright 2023 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Defines CRUD operations on entities in repository."""

# pylint: disable=C0330, g-bad-import-order, protected-access, g-multiple-import

from __future__ import annotations

import abc
from dataclasses import asdict
from typing import Any, Generic, TypeVar

from google.cloud.firestore_v1.base_query import FieldFilter

from googleads_housekeeper.domain.core import entity as domain_entity
from googleads_housekeeper.domain.core import task

T = TypeVar('T')


class AbstractRepository(abc.ABC, Generic[T]):
  """An Abstract Repository."""

  def __init__(self):
    self.seen: set[T] = set()

  def add(self, entity: domain_entity.Entity) -> None:
    """Adds an entity to the repository."""
    self._add(entity)

  def delete(self, entity_id: str) -> None:
    """Deletes an entity by its ID."""
    self._delete(entity_id)

  def get(self, entity_id: str) -> domain_entity.Entity:
    """Retrieves an entity by its ID."""
    return self._get(entity_id)

  def get_by_conditions(
    self, conditions: dict[str, Any]
  ) -> domain_entity.Entity:
    """Retrieves an entity based on specific conditions."""
    return self._get_by_conditions(conditions)

  def get_by_condition(
    self, condition_name: str, condition_value: str
  ) -> domain_entity.Entity:
    """Retrieves an entity based on specific conditions."""
    return self._get_by_conditions({condition_name: condition_value})

  def list(self) -> list[domain_entity.Entity]:
    """Retrieves all entities as a list."""
    return self._list()

  def update(
    self, entity_id: str, update_dict: dict[str, str]
  ) -> domain_entity.Entity:
    return self._update(entity_id, update_dict)

  @abc.abstractmethod
  def _add(self, entity: domain_entity.Entity) -> None:
    """Adds entity to repository."""

  @abc.abstractmethod
  def _get(self, entity_id: str) -> domain_entity.Entity:
    """Gets entity from repository by id."""

  @abc.abstractmethod
  def _get_by_conditions(
    self, conditions: dict[str, Any]
  ) -> list[domain_entity.Entity]:
    """Gets entities from repository by conditions."""

  @abc.abstractmethod
  def _list(self) -> list[domain_entity.Entity]:
    """Gets all entities from repository."""

  @abc.abstractmethod
  def _update(self, entity_id: str, update_dict: dict[str, str]) -> None:
    """Updates entity in repository."""

  @abc.abstractmethod
  def _delete(self, entity_id: str) -> None:
    """Deletes entity from repository."""


class SqlAlchemyRepository(AbstractRepository[T]):
  """An Sql Alchemy Repository."""

  def __init__(self, session, entity=task.Task):
    super().__init__()
    self.session = session
    self.entity = entity

  def _add(self, entity) -> None:
    self.session.add(entity)

  def _get(self, entity_id) -> domain_entity.Entity:
    return self.session.query(self.entity).filter_by(id=entity_id).first()

  def _get_by_conditions(
    self, conditions: dict[str, Any]
  ) -> list[domain_entity.Entity]:
    query = self.session.query(self.entity)
    for condition_name, condition_value in conditions.items():
      query = query.filter(
        getattr(self.entity, condition_name) == condition_value
      )
    return query.all()

  def _list(self) -> list[domain_entity.Entity]:
    return self.session.query(self.entity).all()

  def _update(self, entity_id, update_dict) -> domain_entity.Entity:
    return (
      self.session.query(self.entity)
      .filter_by(id=entity_id)
      .update(update_dict)
    )

  def _delete(self, entity_id) -> domain_entity.Entity:
    return self.session.query(self.entity).filter_by(id=entity_id).delete()


class FirestoreRepository(AbstractRepository[T]):
  """A Firestore Repository Repository."""

  def __init__(self, client, entity: domain_entity.Entity):
    super().__init__()
    self.client = client
    self.entity = entity
    self.collection_name = entity.__name__

  def _add(self, entity) -> None:
    element_id = entity.id if hasattr(entity, 'id') else entity._id
    element_dict = {}
    for key, value in asdict(entity).items():
      if hasattr(value, 'name'):
        value = value.name
      element_dict[key] = value
    self.client.collection(self.collection_name).document(str(element_id)).set(
      element_dict
    )

  def _get(self, entity_id: str) -> domain_entity.Entity:
    doc = self.client.collection(self.collection_name).document(entity_id).get()
    if doc.exists:
      return self.entity(**doc.to_dict())
    return None

  def _get_by_conditions(
    self, conditions: dict[str, Any]
  ) -> list[domain_entity.Entity]:
    try:
      query = self.client.collection(self.collection_name)
      for condition_name, condition_value in conditions.items():
        query = query.where(
          filter=FieldFilter(condition_name, '==', condition_value)
        )
      return [self.entity(**result.to_dict()) for result in query.stream()]
    except Exception:
      return []

  def _list(self) -> list[domain_entity.Entity]:
    results = self.client.collection(self.collection_name).stream()
    return [self.entity(**result.to_dict()) for result in results]

  def _update(self, entity_id: str, update_dict: dict[str, Any]) -> None:
    if doc := self.client.collection(self.collection_name).document(entity_id):
      doc.update(update_dict)

  def _delete(self, entity_id: str) -> None:
    self.client.collection(self.collection_name).document(entity_id).delete()
