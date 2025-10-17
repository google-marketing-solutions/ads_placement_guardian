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

# pylint: disable=C0330, g-bad-import-order, g-multiple-import

"""Module for defining publishers.

Publisher connects Ads Housekeeper with external systems.
"""

from __future__ import annotations

import dataclasses
import json
import logging

from typing_extensions import override

from googleads_housekeeper.domain import events


class BasePublisher:
  """Interface to inherit all publishers from."""

  def publish(self, topic: str, event: events.Event) -> None:
    """Publishes event to a topic."""


class RedisPublisher(BasePublisher):
  """Publishes messages to Redis.

  Attributes:
    client: Instantiated Redis client.
    topic_prefix: Prefix to identify topics related to the application.
  """

  def __init__(
    self, client: 'redis.Redis', topic_prefix: str | None = None
  ) -> None:
    """Initializes RedisPublisher.

    Args:
      client: Instantiated Redis client.
      topic_prefix: Prefix to identify topics related to the application.
    """
    self.client = client
    self.topic_prefix = topic_prefix

  @override
  def publish(self, topic: str, event: events.Event) -> None:
    if self.topic_prefix:
      topic = f'{self.topic_prefix}_{topic}'
    self.client.publish(
      topic, json.dumps(dataclasses.asdict(event), default=str)
    )


class GoogleCloudPubSubPublisher(BasePublisher):
  """Publishes messages to Google Cloud PubSub.

  Attributes:
    client: Instantiated Pubsub client.
    topic_prefix: Prefix to identify topics related to the application.
  """

  def __init__(
    self,
    client: 'google.cloud.pubsub_v1.PublisherClient',
    project_id: str,
    topic_prefix: str | None = None,
  ) -> None:
    """Initializes GoogleCloudPubSubPublisher.

    Args:
      client: Instantiated Pubsub client.
      project_id: Google Cloud project identifier.
      topic_prefix: Prefix to identify topics related to the application.
    """
    self.client = client
    self.project_id = project_id
    self.topic_prefix = topic_prefix

  @override
  def publish(self, topic: str, event: events.Event) -> None:
    if self.topic_prefix:
      topic = f'{self.topic_prefix}_{topic}'
    topic_name = f'projects/{self.project_id}/topics/{topic}'
    data = str(json.dumps(dataclasses.asdict(event), default=str)).encode(
      'utf-8'
    )
    future = self.client.publish(topic_name, data=data)
    future.result()


class LogPublisher(BasePublisher):
  """Sends message to a log.

  Attributes:
    topic_prefix: Prefix to identify topics related to the application.
  """

  def __init__(self, topic_prefix: str | None = None) -> None:
    """Initializes LogPublisher.

    Args:
      topic_prefix: Prefix to identify topics related to the application.
    """
    self.topic_prefix = topic_prefix

  @override
  def publish(self, topic: str, event: events.Event) -> None:
    if self.topic_prefix:
      topic = f'{self.topic_prefix}_{topic}'
    logging.info(
      "Published to topic '%s': %s", topic, dataclasses.asdict(event)
    )
