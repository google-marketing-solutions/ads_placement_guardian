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
"""Defines Unit of Work to handle transactions."""

# pylint: disable=C0330, g-bad-import-order, g-multiple-import

from __future__ import annotations

import abc

import sqlalchemy

from googleads_housekeeper.adapters import repository
from googleads_housekeeper.domain import events
from googleads_housekeeper.domain.core import (
  execution,
  settings,
  task,
)
from googleads_housekeeper.domain.placement_handler import (
  entities as placement_entities,
)


class AbstractUnitOfWork(abc.ABC):
  tasks: repository.AbstractRepository
  old_tasks: repository.AbstractRepository
  settings: repository.AbstractRepository
  customer_ids: repository.AbstractRepository
  mcc_ids: repository.AbstractRepository
  allowlisting: repository.AbstractRepository
  executions: repository.AbstractRepository
  execution_details: repository.AbstractRepository
  published_events: list[events.Event] = []

  def __enter__(self):
    return self

  def __exit__(self, *args):
    self.rollback()

  def commit(self):
    self._commit()

  def collect_new_events(self):
    while self.published_events:
      yield self.published_events.pop(0)

  @abc.abstractmethod
  def _commit(self): ...

  @abc.abstractmethod
  def rollback(self): ...


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
  def __init__(self, session_factory: str) -> None:
    self.engine = sqlalchemy.create_engine(
      session_factory, connect_args={'check_same_thread': False}
    )
    self.session_factory = sqlalchemy.orm.sessionmaker(self.engine)
    self.published_events: list[events.Event] = []

  def __enter__(self) -> None:
    self.session = self.session_factory()
    self.tasks = repository.SqlAlchemyRepository(self.session)
    self.old_tasks = repository.SqlAlchemyRepository(
      self.session, entity=task.OldTask
    )
    self.settings = repository.SqlAlchemyRepository(
      session=self.session, entity=settings.Config
    )
    self.customer_ids = repository.SqlAlchemyRepository(
      session=self.session, entity=settings.CustomerIds
    )
    self.mcc_ids = repository.SqlAlchemyRepository(
      session=self.session, entity=settings.MccIds
    )
    self.allowlisting = repository.SqlAlchemyRepository(
      self.session, entity=placement_entities.AllowlistedPlacement
    )
    self.executions = repository.SqlAlchemyRepository(
      self.session, entity=execution.Execution
    )
    self.execution_details = repository.SqlAlchemyRepository(
      self.session, entity=execution.ExecutionDetails
    )
    super().__enter__()

  def __exit__(self, *args):
    super().__exit__(*args)
    self.session.close()

  def _commit(self):
    self.session.commit()

  def rollback(self):
    self.session.rollback()


class FirestoreUnitOfWork(AbstractUnitOfWork):
  def __init__(self, client: 'google.cloud.firestore.Client') -> None:
    self.client = client
    self.published_events: list[events.Event] = []

  def __enter__(self):
    self.tasks = repository.FirestoreRepository(
      client=self.client, entity=task.Task
    )

    self.old_tasks = repository.FirestoreRepository(
      client=self.client, entity=task.OldTask
    )
    self.settings = repository.FirestoreRepository(
      client=self.client, entity=settings.Config
    )
    self.customer_ids = repository.FirestoreRepository(
      client=self.client, entity=settings.CustomerIds
    )
    self.mcc_ids = repository.FirestoreRepository(
      client=self.client, entity=settings.MccIds
    )
    self.allowlisting = repository.FirestoreRepository(
      self.client, entity=placement_entities.AllowlistedPlacement
    )
    self.executions = repository.FirestoreRepository(
      self.client, entity=execution.Execution
    )
    self.execution_details = repository.FirestoreRepository(
      self.client, entity=execution.ExecutionDetails
    )
    return super().__enter__()

  def _commit(self): ...

  def rollback(self): ...
