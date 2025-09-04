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
"""Main entrypoint for the application."""

# pylint: disable=C0330, g-bad-import-order, g-multiple-import, g-import-not-at-top, missing-function-doctring

from __future__ import annotations

import json
import logging
import os

import flask
import googleads_housekeeper
from gaarf.cli import utils as gaarf_utils
from googleads_housekeeper import bootstrap, views
from googleads_housekeeper.domain import commands

import ads_placement_guardian

app = flask.Flask(__name__)

STATIC_DIR = os.getenv('STATIC_DIR', 'static')

DEPLOYMENT_TYPE = os.getenv('ADS_HOUSEKEEPER_DEPLOYMENT_TYPE', 'Dev')

bus = bootstrap.Bootstrapper(
  deployment_type=DEPLOYMENT_TYPE,
  topic_prefix=os.getenv('TOPIC_PREFIX'),
  database_uri=os.getenv('DATABASE_URI'),
).bootstrap_app()


logger = gaarf_utils.init_logging(name='cpr', loglevel='INFO')
logging.getLogger('google.ads.googleads.client').setLevel(logging.WARNING)


if DEPLOYMENT_TYPE == 'Google Cloud':
  from google.appengine.api import wrap_wsgi_app

  app.wsgi_app = wrap_wsgi_app(app.wsgi_app)


@app.before_request
def check_youtube_data_api_key():
  if not os.getenv('GOOGLE_API_KEY'):
    raise RuntimeError('GOOGLE_API_KEY is not set')


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
  file_requested = os.path.join(app.root_path, STATIC_DIR, path)
  if not os.path.isfile(file_requested):
    path = 'index.html'
  max_age = 0 if path == 'index.html' else None
  return flask.send_from_directory(STATIC_DIR, path, max_age=max_age)


# Tasks
@app.route('/api/tasks', methods=['GET'])
def get_tasks():
  result = views.tasks(bus.uow)
  return _build_response(json.dumps(result, default=str))


@app.route('/api/tasks', methods=['POST'])
def save_task():
  data = flask.request.get_json(force=True)
  cmd = commands.SaveTask(**data)
  task_id = bus.handle(cmd)
  return _build_response(json.dumps(str(task_id)))


@app.route('/api/tasks/<task_id>', methods=['GET'])
def get_task(task_id):
  result = views.task(task_id, bus.uow)
  if not result:
    return 'not found', 404
  return _build_response(json.dumps(result, default=str))


@app.route('/api/tasks/<task_id>/executions', methods=['GET'])
def get_task_executions(task_id):
  result = views.executions(task_id, bus.uow)
  if not result:
    return 'not found', 404
  return _build_response(json.dumps(result, default=str))


@app.route('/api/tasks/<task_id>/executions/<execution_id>', methods=['GET'])
def get_task_execution(task_id, execution_id):
  result = views.execution_details(task_id, execution_id, bus.uow)
  if not result:
    return 'not found', 404
  return _build_response(json.dumps(result, default=str))


@app.route('/api/tasks/<task_id>', methods=['POST'])
def update_task(task_id):
  data = flask.request.get_json(force=True)
  cmd = commands.SaveTask(task_id=task_id, **data)
  task_id = bus.handle(cmd)
  return _build_response(json.dumps(str(task_id)))


@app.route('/api/tasks/<task_id>', methods=['DELETE'])
def delete_task(task_id):
  bus.handle(commands.DeleteTask(task_id))
  return _build_response(json.dumps(str(task_id)))


@app.route('/api/tasks/<task_id>:run', methods=['POST'])
def run_task(task_id):
  """Runs task based on provided task_id."""
  [config] = views.config(bus.uow)
  data = flask.request.get_json(force=True)
  data.update({'save_to_db': config.get('save_to_db', True)})
  cmd = commands.RunTask(id=task_id, **data)
  result, message_payload = bus.handle(cmd)
  logger.info('Command <%s> is executed with results: %s', cmd, result)
  if message_payload.total_placement_excluded:
    notification_service = bus.dependencies.get('notification_service')
    notification_service.send(message_payload)
    logger.info(
      'Task <%s> sent a notification to notification service: %s',
      task_id,
      notification_service.__class__.__name__,
    )
  return _build_response(json.dumps(result))


@app.route('/api/tasks/<task_id>/scheduled_run', methods=['GET'])
def run_task_from_schedule(task_id):
  """Runs scheduled task."""
  cmd = commands.RunTask(id=task_id, type='SCHEDULED')
  result, message_payload = bus.handle(cmd)
  logger.info('Command <%s> is executed with results: %s', cmd, result)
  if message_payload.total_placement_excluded:
    notification_service = bus.dependencies.get('notification_service')
    notification_service.send(message_payload)
    logger.info(
      'Task <%s> sent a notification to notification service: %s',
      task_id,
      notification_service.__class__.__name__,
    )
  return _build_response(json.dumps(result))


# Placements
@app.route('/api/placements/preview', methods=['POST'])
def preview_placements():
  """Sends API request for getting placements satisfying the condition."""
  if not (config := views.config(bus.uow)):
    ads_client = bus.dependencies.get('ads_api_client').client
    if not (mcc_id := ads_client.login_customer_id):
      mcc_id = ads_client.linked_customer_id
    cmd = commands.SaveConfig(mcc_id=mcc_id, email_address='', id=None)
    bus.handle(cmd)
    config = {'mcc_id': mcc_id, 'email_address': ''}
  else:
    config = config[0]
  data = flask.request.get_json(force=True)
  cmd = commands.PreviewPlacements(
    **data,
    save_to_db=config.get('save_to_db', True),
    always_fetch_youtube_preview_mode=config.get(
      'always_fetch_youtube_preview_mode', False
    ),
  )
  logger.info('Running command: %s', cmd)
  result = bus.handle(cmd)
  logger.info(
    'Running task %s returned %d placements', cmd, len(result.get('data'))
  )
  return _build_response(msg=json.dumps(result))


@app.route('/api/placements/exclude', methods=['POST'])
def run_manual_excluder():
  data = flask.request.get_json(force=True)
  cmd = commands.RunManualExclusion(**data)
  result = bus.handle(cmd)
  logger.info('Running command: %s returned  %s', cmd, result)
  return _build_response(json.dumps(result))


@app.route('/api/placements/allowlist', methods=['GET'])
def get_allowlisted_placements():
  if result := views.allowlisted_placements(bus.uow):
    return _build_response(json.dumps(result, default=str))
  return 'no allowlisted placements', 200


@app.route('/api/placements/allowlist', methods=['POST'])
def add_to_allowlisting():
  data = flask.request.get_json(force=True)
  cmd = commands.AddToAllowlisting(**data)
  bus.handle(cmd)
  return _build_response(json.dumps('success'))


@app.route('/api/placements/allowlist', methods=['DELETE'])
def remove_from_allowlisting():
  data = flask.request.get_json(force=True)
  cmd = commands.RemoveFromAllowlisting(**data)
  bus.handle(cmd)
  return _build_response(json.dumps('success'))


@app.route('/api/migrateOldTasks', methods=['GET'])
def migrate_old_tasks():
  cmd = commands.MigrateFromOldTasks()
  migrated = bus.handle(cmd)
  return _build_response(
    json.dumps(f'Migrated {migrated} old tasks', default=str)
  )


# Config
@app.route('/api/configs', methods=['GET'])
def get_config():
  """Returns application config."""
  if not (result := views.config(bus.uow)):
    ads_client = bus.dependencies.get('ads_api_client').client
    if not (mcc_id := ads_client.login_customer_id):
      mcc_id = ads_client.linked_customer_id
    cmd = commands.SaveConfig(mcc_id=mcc_id, email_address='', id=None)
    bus.handle(cmd)
    result = {'mcc_id': mcc_id, 'email_address': ''}
  else:
    result = result[0]
  return _build_response(json.dumps(result))


@app.route('/api/configs', methods=['POST'])
def set_config():
  data = flask.request.get_json(force=True)
  if existing_config := views.config(bus.uow):
    config_data = existing_config[0]
    config_data.update(data)
    cmd = commands.SaveConfig(**config_data)
  else:
    cmd = commands.SaveConfig(**data)
  bus.handle(cmd)
  return _build_response(json.dumps('success'))


# Accounts
@app.route('/api/accounts/mcc', methods=['GET'])
def get_all_mcc_ids():
  if not (mcc_ids := views.mcc_ids(bus.uow)):
    root_mcc_id = _get_mcc_from_ads_client()
    cmd = commands.GetMccIds(root_mcc_id)
    mcc_ids = bus.handle(cmd)
  return _build_response(json.dumps(mcc_ids))


@app.route('/api/accounts/mcc', methods=['POST'])
def update_mcc_ids():
  root_mcc_id = _get_mcc_from_ads_client()
  cmd = commands.GetMccIds(str(root_mcc_id))
  mccs = bus.handle(cmd)
  for mcc in mccs:
    cmd = commands.GetCustomerIds(mcc_id=mcc.get('id'))
    bus.handle(cmd)
  return _build_response(json.dumps(mccs))


@app.route('/api/accounts/customers', methods=['GET'])
def get_customer_ids():
  if not (config := views.config(bus.uow)):
    mcc_id = _get_mcc_from_ads_client()
  else:
    mcc_id = config[0].get('mcc_id')
  result = views.customer_ids(bus.uow, mcc_id)
  if not result:
    cmd = commands.GetCustomerIds(mcc_id=mcc_id)
    result = bus.handle(cmd)
  return _build_response(json.dumps(result))


@app.route('/api/accounts/customers', methods=['POST'])
def update_customer_ids():
  """Updates available account ids based on root MCC."""
  if not flask.request.values:
    mcc_ids = [account.get('id') for account in views.mcc_ids(bus.uow)]
  else:
    data = flask.request.get_json(force=True)
    if not (mcc_id := data.get('mcc_id')):
      if not (config := views.config(bus.uow)):
        mcc_id = _get_mcc_from_ads_client()
      else:
        mcc_id = config[0].get('mcc_id')
    mcc_ids = [mcc_id]
  results = []
  for mcc_id in mcc_ids:
    cmd = commands.GetCustomerIds(mcc_id=mcc_id)
    results.append(bus.handle(cmd))
  return _build_response(json.dumps(results))


@app.route('/api/version', methods=['GET'])
def get_version():
  return _build_response(json.dumps(ads_placement_guardian.__version__))


@app.route('/api/info', methods=['GET'])
def get_application_info():
  info = {
    'version': ads_placement_guardian.__version__,
    'backend_version': googleads_housekeeper.__version__,
    'topic': os.getenv('TOPIC_PREFIX'),
    'db': os.getenv('DATABASE_URI'),
    'is_observe_mode': bus.dependencies.get('is_observe_mode'),
  }
  return _build_response(json.dumps(info))


def _build_response(msg='', status=200, mimetype='application/json'):
  """Helper method to build the response."""
  response = app.response_class(msg, status=status, mimetype=mimetype)
  response.headers['Access-Control-Allow-Origin'] = '*'
  return response


def _get_mcc_from_ads_client() -> str:
  ads_client = bus.dependencies.get('ads_api_client').client
  if not (mcc_id := ads_client.login_customer_id):
    mcc_id = ads_client.linked_customer_id
  return mcc_id


if __name__ == '__main__':
  app.run(debug=True, port=5000)
