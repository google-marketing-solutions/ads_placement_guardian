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
"""Injects dependencies to run the application."""

# pylint: disable=C0330, g-bad-import-order g-multiple-import, g-import-not-at-top

from __future__ import annotations

import importlib
import inspect
import os

import smart_open
import yaml
from gaarf.api_clients import GoogleAdsApiClient

if os.environ.get(
  'ADS_HOUSEKEEPER_DEPLOYMENT_TYPE'
) == 'Google Cloud' and not importlib.util.find_spec('google.cloud.firestore'):
  raise ImportError(
    'Please install googleads-housekeeper with Google Cloud support - '
    '`pip install googleads-housekeeper[gcp]`'
  )
from google.cloud import firestore, pubsub_v1

from googleads_housekeeper.adapters import notifications, orm, publisher
from googleads_housekeeper.services import handlers, messagebus, unit_of_work


class GoogleCloudBootstrapper:
  """Prepares dependencies to run application on Google Cloud."""

  def __init__(
    self,
    topic_prefix: str | None = None,
    database_uri: str = os.environ.get('FIRESTORE_DB', '(default)'),
    project_id: str = os.environ.get('GOOGLE_CLOUD_PROJECT'),
    appengine_region: str = os.environ.get('APPENGINE_REGION', 'europe-west1'),
  ) -> None:
    self.start_orm = False
    self.uow = unit_of_work.FirestoreUnitOfWork(
      firestore.Client(project=project_id, database=database_uri)
    )
    self.notification_service = (
      notifications.GoogleCloudAppEngineEmailNotifications(
        project_id=project_id, appengine_region=appengine_region
      )
    )
    self.publish_service = publisher.GoogleCloudPubSubPublisher(
      client=pubsub_v1.PublisherClient(),
      project_id=project_id,
      topic_prefix=topic_prefix,
    )


class LocalBootstrapper:
  """Prepares dependencies to run application locally."""

  def __init__(
    self, topic_prefix: str | None = None, database_uri: str | None = None
  ) -> None:
    self.start_orm = True
    self.uow = unit_of_work.SqlAlchemyUnitOfWork(database_uri or _get_db_uri())
    self.publish_service = publisher.LogPublisher(topic_prefix)
    self.notification_service = notifications.ConsoleNotifications()


class DevBootstrapper:
  """Prepares dependencies to run application in development environment."""

  def __init__(
    self, topic_prefix: str | None = None, database_uri: str | None = None
  ) -> None:
    self.start_orm = True
    self.uow = unit_of_work.SqlAlchemyUnitOfWork(
      database_uri or f'sqlite:///{os.getcwd()}/ads_housekeeper_tasks.db'
    )
    self.publish_service = publisher.LogPublisher(topic_prefix)
    self.notification_service = notifications.ConsoleNotifications()


DEPLOYMENT_TYPES = {
  'Local': LocalBootstrapper,
  'Google Cloud': GoogleCloudBootstrapper,
  'Dev': DevBootstrapper,
}


class Bootstrapper:
  """Prepares application dependencies based on a provided deployment type."""

  def __init__(
    self,
    deployment_type: str = 'Dev',
    topic_prefix: str | None = None,
    database_uri: str | None = None,
    **kwargs: str,
  ) -> None:
    self.deployment_type = deployment_type
    self.topic_prefix = topic_prefix
    self.database_uri = database_uri
    self.bootstrapper_parameters = kwargs or {}

  def bootstrap_app(
    self,
  ) -> messagebus.MessageBus:
    """Builds MessageBus based on specified deployment type."""
    bootstrapper = DEPLOYMENT_TYPES[self.deployment_type](
      topic_prefix=self.topic_prefix,
      database_uri=self.database_uri,
    )
    return bootstrap(
      start_orm=bootstrapper.start_orm,
      uow=bootstrapper.uow,
      notification_service=bootstrapper.notification_service,
      publish_service=bootstrapper.publish_service,
    )


def _get_db_uri(
  host: str = os.environ.get('DB_HOST', 'localhost'),
  port: int = int(os.environ.get('DB_PORT', 54321)),
  user: str = os.environ.get('DB_USER', 'ads_housekeeper'),
  password: str = os.environ.get('DB_PASSWORD', 'ads_housekeeper'),
  db_name: str = os.environ.get('DB_NAME', 'ads_housekeeper'),
  db_engine: str = os.environ.get('DB_ENGINE', 'postgresql'),
) -> str:
  if dev_db := os.environ.get('DEV_DB_HOST'):
    return f'sqlite:///{dev_db}'
  return f'{db_engine}://{user}:{password}@{host}:{port}/{db_name}'


def _get_default_google_ads_api_client():
  path_to_config = os.environ.get(
    'GOOGLE_ADS_PATH_TO_CONFIG', '~/google-ads.yaml'
  )
  with smart_open.open(path_to_config, 'r', encoding='utf-8') as f:
    google_ads_config_dict = yaml.safe_load(f)
  return GoogleAdsApiClient(config_dict=google_ads_config_dict)


def _get_notification_service() -> notifications.BaseNotifications:
  notification_service_factory = notifications.NotificationFactory()
  notification_type = os.environ.get(
    'ADS_HOUSEKEEPER_NOTIFICATION_TYPE', 'console'
  )
  return notification_service_factory.create_notification_service(
    notification_type=notification_type
  )


def bootstrap(
  ads_api_client: GoogleAdsApiClient | None = None,
  start_orm: bool = True,
  uow: unit_of_work.AbstractUnitOfWork = unit_of_work.SqlAlchemyUnitOfWork(
    _get_db_uri()
  ),
  notification_service: notifications.BaseNotifications = (
    _get_notification_service()
  ),
  publish_service: publisher.BasePublisher = publisher.LogPublisher(),
) -> messagebus.MessageBus:
  """Injects dependencies to run the application.

  Args:
    ads_api_client: Google Ads API client to fetch data and perform mutates.
    start_orm: Whether to initialize ORM object in DB.
    uow: Unit of Work to handle transactions.
    notification_service: Service to send notifications on operations retults.
    publish_service: Service to send events.

  Returns:
    MessageBus with injected dependencies.
  """
  if start_orm:
    orm.start_mappers(engine=uow.engine)

  dependencies = {
    'uow': uow,
    'ads_api_client': ads_api_client or _get_default_google_ads_api_client(),
    'notification_service': notification_service,
    'publisher': publish_service,
    'is_observe_mode': os.getenv('ADS_HOUSEKEEPER_MODE', 'exclusions').lower()
    == 'observe',
  }
  injected_event_handlers = {
    event_type: [
      _inject_dependencies(handler, dependencies) for handler in handlers
    ]
    for event_type, handlers in handlers.EVENT_HANDLERS.items()
  }
  injected_command_handlers = {
    command_type: _inject_dependencies(handler, dependencies)
    for command_type, handler in handlers.COMMAND_HANDLERS.items()
  }
  return messagebus.MessageBus(
    uow=uow,
    event_handlers=injected_event_handlers,
    command_handlers=injected_command_handlers,
    dependencies=dependencies,
  )


def _inject_dependencies(handler, dependencies):
  params = inspect.signature(handler).parameters
  deps = {
    name: dependency
    for name, dependency in dependencies.items()
    if name in params
  }
  return lambda message: handler(message, **deps)
