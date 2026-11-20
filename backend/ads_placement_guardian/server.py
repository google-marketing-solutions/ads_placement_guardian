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

import base64
import binascii
import hmac
import http
import json
import logging
import os
from urllib import parse

import flask
import googleads_housekeeper
from garf_executors.entrypoints import utils as garf_utils
from googleads_housekeeper import bootstrap, views
from googleads_housekeeper.domain import commands
from opentelemetry.instrumentation.flask import FlaskInstrumentor

import ads_placement_guardian

app = flask.Flask(__name__)
FlaskInstrumentor().instrument_app(app)

STATIC_DIR = os.getenv('STATIC_DIR', 'static')

DEPLOYMENT_TYPE = os.getenv('ADS_HOUSEKEEPER_DEPLOYMENT_TYPE', 'Dev')

bus = bootstrap.Bootstrapper(
  deployment_type=DEPLOYMENT_TYPE,
  topic_prefix=os.getenv('TOPIC_PREFIX'),
  database_uri=os.getenv('DATABASE_URI'),
).bootstrap_app()


logger = garf_utils.init_logging(
  name='cpr', loglevel='INFO', logger_type='gcloud'
)
logging.getLogger('google.ads.googleads.client').setLevel(logging.WARNING)


if DEPLOYMENT_TYPE == 'Google Cloud':
  from google.appengine.api import wrap_wsgi_app

  app.wsgi_app = wrap_wsgi_app(app.wsgi_app)


@app.before_request
def check_youtube_data_api_key():
  if not os.getenv('GOOGLE_API_KEY'):
    raise RuntimeError('GOOGLE_API_KEY is not set')


def _is_authorized_request(expected_key: str) -> bool:
  """Validate Bearer or HTTP Basic credentials in constant time."""
  auth_header = flask.request.headers.get('Authorization', '')
  scheme, _, credentials = auth_header.partition(' ')
  expected_bytes = expected_key.encode('utf-8')
  if scheme == 'Bearer':
    return hmac.compare_digest(credentials.encode('utf-8'), expected_bytes)
  if scheme == 'Basic':
    try:
      decoded = base64.b64decode(credentials, validate=True).decode('utf-8')
    except (binascii.Error, UnicodeDecodeError):
      return False
    _, has_colon, password = decoded.partition(':')
    return bool(has_colon) and hmac.compare_digest(
      password.encode('utf-8'), expected_bytes
    )
  return False


@app.before_request
def require_api_key() -> flask.Response | None:
  """Enforce APG_API_KEY authentication on all API routes.

  When APG_API_KEY is set (required in docker-compose and recommended for any
  deployment not fronted by Cloud IAP), every API request must carry a matching
  Authorization: Bearer <key> header (for CLI/scheduler callers) or HTTP Basic
  password (so the browser UI prompts once and authenticates /api/* XHR calls).
  IAP-fronted App Engine deployments leave APG_API_KEY unset.
  """
  expected = os.environ.get('APG_API_KEY')
  if not expected:
    return None
  is_api_route = flask.request.path.startswith(
    '/api/'
  ) or flask.request.endpoint not in (None, 'catch_all', 'static')
  if not is_api_route or _is_authorized_request(expected):
    return None
  return flask.Response(
    'Unauthorized',
    status=401,
    headers={'WWW-Authenticate': 'Basic realm="Ads Placement Guardian"'},
  )


_DEFAULT_PORTS = {'http': 80, 'https': 443}
_STATE_CHANGING_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})


def _extract_origin_host(url: str) -> str | None:
  """Extract normalized host[:port] from an Origin or Referer URL."""
  parsed = parse.urlparse(url)
  default_port = _DEFAULT_PORTS.get(parsed.scheme)
  if default_port is None or not parsed.hostname:
    return None
  try:
    port = parsed.port
  except ValueError:
    return None
  host = f'[{parsed.hostname}]' if ':' in parsed.hostname else parsed.hostname
  host = host.lower()
  if port and port != default_port:
    return f'{host}:{port}'
  return host


@app.before_request
def _reject_cross_origin_state_change() -> None:
  """Reject state-changing API requests from cross-origin browser contexts."""
  is_api_route = flask.request.path.startswith(
    '/api/'
  ) or flask.request.endpoint not in (None, 'catch_all', 'static')
  if flask.request.method not in _STATE_CHANGING_METHODS or not is_api_route:
    return
  sec_fetch_site = flask.request.headers.get('Sec-Fetch-Site', '').lower()
  if sec_fetch_site not in ('', 'same-origin', 'none'):
    flask.abort(http.HTTPStatus.FORBIDDEN)
  source_url = flask.request.headers.get(
    'Origin'
  ) or flask.request.headers.get('Referer')
  if not source_url:
    return
  request_url = f'{flask.request.scheme}://{flask.request.host}'
  source_host = _extract_origin_host(source_url)
  if not source_host or source_host != _extract_origin_host(request_url):
    flask.abort(http.HTTPStatus.FORBIDDEN)


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
  data = flask.request.get_json()
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
  data = flask.request.get_json()
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
  data = flask.request.get_json()
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
  data = flask.request.get_json()
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
  data = flask.request.get_json()
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
  data = flask.request.get_json()
  cmd = commands.AddToAllowlisting(**data)
  bus.handle(cmd)
  return _build_response(json.dumps('success'))


@app.route('/api/placements/allowlist', methods=['DELETE'])
def remove_from_allowlisting():
  data = flask.request.get_json()
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
  data = flask.request.get_json()
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
  if not flask.request.get_data(cache=True):
    mcc_ids = [account.get('id') for account in views.mcc_ids(bus.uow)]
  else:
    data = flask.request.get_json()
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
  return app.response_class(msg, status=status, mimetype=mimetype)


def _get_mcc_from_ads_client() -> str:
  ads_client = bus.dependencies.get('ads_api_client').client
  if not (mcc_id := ads_client.login_customer_id):
    mcc_id = ads_client.linked_customer_id
  return mcc_id


if __name__ == '__main__':
  app.run(debug=True, port=5000)
