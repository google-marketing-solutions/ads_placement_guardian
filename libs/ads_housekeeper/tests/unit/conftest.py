# Copyright 2024 Google LLC
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

# pylint: disable=C0330, g-bad-import-order, g-multiple-import, missing-class-docstring, missing-module-docstring, missing-function-docstring


from __future__ import annotations

import collections

import pytest
from googleads_housekeeper import bootstrap
from googleads_housekeeper.adapters import notifications, publisher
from googleads_housekeeper.services import unit_of_work


class FakeGoogleAdsApiClient:
  def __init__(self):
    self.api_version = '1.17'


class FakeNotifications(notifications.BaseNotifications):
  def __init__(self):
    self.sent = collections.defaultdict(list)  # type: Dict[str, List[str]]

  def publish(self, topic, event):
    self.sent[topic].append(event)


class FakePublisher(publisher.BasePublisher):
  def __init__(self):
    self.events = []  # type: Dict[str, List[str]]

  def publish(self, topic, event):
    self.events.append(event)


@pytest.fixture(scope='session')
def in_memory_sqlite_db():
  return 'sqlite:///:memory:'


@pytest.fixture(scope='session')
def fake_publisher():
  return FakePublisher()


@pytest.fixture(scope='session')
def bus(fake_publisher, in_memory_sqlite_db):
  return bootstrap.bootstrap(
    start_orm=True,
    ads_api_client=FakeGoogleAdsApiClient(),
    uow=unit_of_work.SqlAlchemyUnitOfWork(in_memory_sqlite_db),
    publish_service=fake_publisher,
  )
