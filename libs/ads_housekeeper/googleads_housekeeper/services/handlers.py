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
"""Application handlers."""

# pylint: disable=C0330, g-bad-import-order, g-multiple-import, g-importing-member
from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any

from gaarf.api_clients import GoogleAdsApiClient
from gaarf.cli import utils as gaarf_utils
from gaarf.report import GaarfReport
from gaarf.report_fetcher import AdsReportFetcher

from googleads_housekeeper.adapters.legacy_adapter import TaskAdapter
from googleads_housekeeper.adapters.notifications import MessagePayload
from googleads_housekeeper.adapters.publisher import BasePublisher
from googleads_housekeeper.domain import commands, events
from googleads_housekeeper.domain.core import execution, settings, task
from googleads_housekeeper.domain.placement_handler import (
  entities as placement_entities,
)
from googleads_housekeeper.domain.placement_handler import (
  placement_excluder,
  placement_fetcher,
  placement_service,
)
from googleads_housekeeper.services import enums, unit_of_work

logger = gaarf_utils.init_logging(loglevel='INFO', name='ahk')


def get_mcc_accounts(
  cmd: commands.GetMccIds,
  uow: unit_of_work.AbstractUnitOfWork,
  ads_api_client: GoogleAdsApiClient,
) -> list[dict[str, str]]:
  """Fetches and updates mcc accounts in the repository.

  Args:
      cmd: command for getting MccIds.
      uow: unit of work to handle the transaction.
      ads_api_client: client to perform report fetching.

  Returns:
      All mcc accounts available under given root_mcc_id.
  """
  mccs = get_accessible_mccs(ads_api_client, cmd.root_mcc_id)
  result: list[dict[str, str]] = []
  with uow:
    saved_mcc_ids = {int(account.id) for account in uow.mcc_ids.list()}
    fetched_mcc_ids = set(
      mccs['account_id'].to_list(flatten=True, distinct=True)
    )
    new_accounts = fetched_mcc_ids.difference(saved_mcc_ids)
    to_be_removed_accounts = saved_mcc_ids.difference(fetched_mcc_ids)
    for row in mccs:
      row_dict = {'id': row.account_id, 'account_name': row.account_name}
      result.append(row_dict)
      if row.account_id in new_accounts:
        uow.mcc_ids.add(settings.MccIds(**row_dict))
    for account_id in to_be_removed_accounts:
      uow.mcc_ids.delete(account_id)
    uow.commit()
  return result


def get_accessible_mccs(
  ads_api_client: GoogleAdsApiClient, root_mcc_id: int
) -> GaarfReport:
  """Fetches all available mccs under a root_mcc_id.

  Args:
      ads_api_client: client to perform report fetching.
      root_mcc_id: root mmc id for which leaf mccs should be fetched.

  Returns:
  Report with mcc names and ids.
  """
  query = """
        SELECT
            customer_client.descriptive_name AS account_name,
            customer_client.id AS account_id
        FROM customer_client
        WHERE customer_client.manager = TRUE
        AND customer_client.status = "ENABLED"
        """
  report_fetcher = AdsReportFetcher(api_client=ads_api_client)
  return report_fetcher.fetch(query, root_mcc_id)


def get_customer_ids(
  cmd: commands.GetCustomerIds,
  uow: unit_of_work.AbstractUnitOfWork,
  ads_api_client: GoogleAdsApiClient,
) -> list[dict[str, int]]:
  """Fetches accounts under a given mcc_id and update them in the repository.

  Args:
      cmd: command for getting customer ids under a given mcc_id.
      uow: unit of work to handle the transaction.
      ads_api_client: client to perform report fetching.

  Returns:
      All accounts available under given mcc_id.
  """
  customer_ids_query = """
    SELECT
        customer_client.descriptive_name AS account_name,
        customer_client.id AS account_id
    FROM customer_client
    WHERE customer_client.manager = FALSE
    AND customer_client.status = "ENABLED"
    """
  report_fetcher = AdsReportFetcher(api_client=ads_api_client)
  customer_ids = report_fetcher.fetch(
    customer_ids_query, customer_ids=cmd.mcc_id
  )
  saved_customer_ids = {
    int(account.id)
    for account in uow.customer_ids.get_by_conditions({'mcc_id': cmd.mcc_id})
  }
  fetched_customer_ids = set(
    customer_ids['account_id'].to_list(flatten=True, distinct=True)
  )
  new_accounts = fetched_customer_ids.difference(saved_customer_ids)
  to_be_removed_accounts = saved_customer_ids.difference(fetched_customer_ids)
  result: list[dict[str, int]] = []
  with uow:
    for row in customer_ids:
      result.append({'account_name': row.account_name, 'id': row.account_id})
      if row.account_id in new_accounts:
        uow.customer_ids.add(
          settings.CustomerIds(
            mcc_id=cmd.mcc_id,
            account_name=row.account_name,
            id=str(row.account_id),
          )
        )
    for account_id in to_be_removed_accounts:
      uow.customer_ids.delete(account_id)
    uow.commit()
  return result


def run_manual_exclusion_task(
  cmd: commands.RunManualExclusion,
  uow: unit_of_work.AbstractUnitOfWork,
  ads_api_client: GoogleAdsApiClient,
  is_observe_mode: bool,
) -> dict[str, int]:
  if is_observe_mode:
    logger.warning(
      'Ads Housekeeper is in observe mode. No exclusions will be performed.'
    )
    return {
      'excluded_placements': 0,
      'associated_with_list_placements': 0,
      'excludable_from_account_only': 0,
    }
  with uow:
    report_fetcher = AdsReportFetcher(ads_api_client)
    excluder = placement_excluder.PlacementExcluder(
      ads_api_client, enums.ExclusionLevelEnum[cmd.exclusion_level]
    )
    fetcher = placement_fetcher.PlacementFetcher(report_fetcher)
    placement_exclusion_lists = fetcher.get_placement_exclusion_lists(
      customer_ids=cmd.customer_ids
    )
    exclusion_result = excluder.exclude_placements(
      to_be_excluded_placements=GaarfReport(
        results=cmd.placements, column_names=cmd.header
      ),
      placement_exclusion_lists=placement_exclusion_lists,
    )
    n_excluded_placements = len(exclusion_result.excluded_placements or [])
    n_associated_with_list_placements = len(
      exclusion_result.associated_with_list_placements or []
    )
    n_excludable_from_account_only = len(
      exclusion_result.excludable_from_account_only or []
    )
    return {
      'excluded_placements': n_excluded_placements,
      'associated_with_list_placements': n_associated_with_list_placements,
      'excludable_from_account_only': n_excludable_from_account_only,
    }


def task_created(event: events.TaskCreated, publisher: BasePublisher) -> None:
  publisher.publish('task_created', event)


def task_with_schedule_created(
  event: events.TaskWithScheduleCreated, publisher: BasePublisher
) -> None:
  publisher.publish('task_created', event)


def task_updated(event: events.TaskUpdated, publisher: BasePublisher) -> None:
  publisher.publish('task_updated', event)


def task_schedule_updated(
  event: events.TaskScheduleUpdated, publisher: BasePublisher
) -> None:
  publisher.publish('task_updated', event)


def task_deleted(event: events.TaskDeleted, publisher: BasePublisher) -> None:
  publisher.publish('task_deleted', event)


def task_schedule_deleted(
  event: events.TaskScheduleDeleted, publisher: BasePublisher
) -> None:
  publisher.publish('task_deleted', event)


def run_task(
  cmd: commands.RunTask,
  uow: unit_of_work.AbstractUnitOfWork,
  ads_api_client: GoogleAdsApiClient,
  is_observe_mode: bool,
  save_to_db: bool = False,
) -> tuple[dict[str, int], MessagePayload]:
  with uow:
    if is_observe_mode:
      logger.warning('Task <%s> is run in observe mode', cmd.id)
    settings = uow.settings.list()
    task_obj = uow.tasks.get(entity_id=cmd.id)
    start_time = datetime.now()
    if task_obj.output == task.TaskOutput.NOTIFY or is_observe_mode:
      report_fetcher = AdsReportFetcher(api_client=ads_api_client)
      to_be_excluded_placements = (
        placement_service.find_placements_for_exclusion(
          task_obj=task_obj,
          uow=uow,
          report_fetcher=report_fetcher,
        )
      )
      exclusion_result = placement_excluder.ExclusionResult(
        excluded_placements=to_be_excluded_placements
      )
    else:
      exclusion_result = placement_service.exclude_placements(
        task_obj=task_obj,
        uow=uow,
        client=ads_api_client,
        runtime_options=placement_service.RuntimeOptions(
          always_fetch_youtube_preview_mode=False
        ),
      )
    end_time = datetime.now()
    n_excluded_placements = len(exclusion_result.excluded_placements or [])
    n_associated_with_list_placements = len(
      exclusion_result.associated_with_list_placements or []
    )
    execution_obj = execution.Execution(
      task=cmd.id,
      start_time=start_time,
      end_time=end_time,
      placements_excluded=n_excluded_placements,
      type=cmd.type,
    )
    uow.executions.add(execution_obj)
    if save_to_db and exclusion_result.excluded_placements:
      for placement in exclusion_result.excluded_placements:
        if hasattr(placement, 'reason'):
          exclusion_reason = placement.reason
        else:
          exclusion_reason = ''
        uow.execution_details.add(
          execution.ExecutionDetails(
            execution_id=execution_obj.id,
            placement=placement.name,
            placement_type=placement.placement_type,
            reason=exclusion_reason,
          )
        )
    uow.commit()
    if excluded_placements := exclusion_result.excluded_placements:
      message_payload = MessagePayload(
        task_id=task_obj.id,
        task_name=task_obj.name,
        task_formula=task_obj.exclusion_rule,
        task_output=task_obj.output,
        placements_excluded_sample=excluded_placements[0:10],
        total_placement_excluded=len(excluded_placements),
        recipient=settings[0].email_address,
      )
    else:
      message_payload = MessagePayload(
        task_id=task_obj.id,
        task_name=task_obj.name,
        task_formula=task_obj.exclusion_rule,
        task_output=task_obj.output,
        placements_excluded_sample=None,
        total_placement_excluded=0,
        recipient=settings[0].email_address,
      )
    return {
      'task_id': task_obj.id,
      'execution_id': execution_obj.id,
      'excluded_placements': n_excluded_placements,
      'associated_with_list_placements': n_associated_with_list_placements,
    }, message_payload


def _generate_date_range_json(date_range: int, from_days_ago: int) -> str:
  """Generates a JSON string with a date range.

  Args:
    date_range:
    from_days_ago:

  Returns:
    str: A JSON string in the format
    {"date_from": "YYYY-MM-DD", "date_to": "YYYY-MM-DD"}.
  """
  date_to = datetime.today() - timedelta(days=from_days_ago)
  date_from = date_to - timedelta(days=date_range)
  date_to_str = date_to.strftime('%Y-%m-%d')
  date_from_str = date_from.strftime('%Y-%m-%d')
  return json.dumps({'date_from': date_from_str, 'date_to': date_to_str})


def run_preview_placements(
  cmd: commands.PreviewPlacements,
  uow: unit_of_work.AbstractUnitOfWork,
  ads_api_client: GoogleAdsApiClient,
  save_to_db: bool = False,
) -> dict[str, dict[str, Any]]:
  """Executes a preview placement task.

  Args:
    cmd: The command containing parameters for previewing placements.
    uow: The unit of work managing database transactions.
    ads_api_client: The client used to interact with the Google Ads API.
    save_to_db: Whether to save the fetched results to the database.

  Returns:
    All placements matching the rule and a period of fetching.
  """
  report_fetcher = AdsReportFetcher(api_client=ads_api_client)
  task_obj = task.Task(
    name='',
    exclusion_rule=cmd.exclusion_rule,
    customer_ids=cmd.customer_ids,
    date_range=cmd.date_range,
    from_days_ago=cmd.from_days_ago,
    exclusion_level=enums.ExclusionLevelEnum[cmd.exclusion_level],
    placement_types=cmd.placement_types,
  )
  to_be_excluded_placements = placement_service.find_placements_for_exclusion(
    task_obj=task_obj,
    uow=uow,
    report_fetcher=report_fetcher,
    runtime_options=placement_service.RuntimeOptions(
      always_fetch_youtube_preview_mode=cmd.always_fetch_youtube_preview_mode,
      save_to_db=save_to_db,
    ),
    limit=cmd.limit,
  )
  if not to_be_excluded_placements:
    data = {}
  else:
    data = json.loads(
      to_be_excluded_placements.to_pandas().to_json(orient='records')
    )
  return {
    'data': data,
    'dates': {'date_from': task_obj.start_date, 'date_to': task_obj.end_date},
  }


def save_task(
  cmd: commands.SaveTask,
  uow: unit_of_work.AbstractUnitOfWork,
) -> str:
  with uow:
    if hasattr(cmd, 'task_id') and cmd.task_id:
      task_id = cmd.task_id
      task_obj = uow.tasks.get(entity_id=task_id)
      task_schedule = str(task_obj.schedule)
      update_dict = asdict(cmd)
      update_dict.pop('task_id')
      uow.tasks.update(task_obj.id, update_dict)
      uow.commit()
      if cmd.schedule not in ('0', task_schedule):
        uow.published_events.append(
          events.TaskScheduleUpdated(
            task_id=cmd.task_id,
            schedule=cmd.schedule,
            appengine_service=os.getenv('GAE_SERVICE'),
          )
        )
      elif cmd.schedule == '0' and cmd.schedule != task_schedule:
        uow.published_events.append(events.TaskScheduleDeleted(cmd.task_id))
      else:
        uow.published_events.append(events.TaskUpdated(cmd.task_id))
    else:
      task_dict = asdict(cmd)
      task_dict.pop('task_id')
      task_obj = task.Task(**task_dict)
      uow.tasks.add(task_obj)
      uow.commit()
      task_id = task_obj.id
      if cmd.schedule != '0':
        uow.published_events.append(
          events.TaskWithScheduleCreated(
            task_id=task_id,
            task_name=cmd.name,
            schedule=cmd.schedule,
            appengine_service=os.getenv('GAE_SERVICE'),
          )
        )
      else:
        uow.published_events.append(events.TaskCreated(task_id))
    task_id = task_obj.id
    return str(task_id)


def delete_task(
  cmd: commands.DeleteTask,
  uow: unit_of_work.AbstractUnitOfWork,
):
  with uow:
    task_obj = uow.tasks.get(entity_id=cmd.task_id)
    if task_obj:
      uow.tasks.update(cmd.task_id, {'status': 'INACTIVE'})
      uow.commit()
      uow.published_events.append(events.TaskDeleted(cmd.task_id))
    else:
      logger.warning('No task with id %d found!', cmd.id)


def save_config(
  cmd: commands.SaveConfig,
  uow: unit_of_work.AbstractUnitOfWork,
):
  with uow:
    if hasattr(cmd, 'id') and cmd.id:
      config_id = cmd.id
      config = uow.settings.get(config_id)
      update_dict = asdict(cmd)
      update_dict.pop('id')
      uow.settings.update(config.id, update_dict)
    else:
      config_dict = asdict(cmd)
      config_dict.pop('id')
      config = settings.Config(**config_dict)
      uow.settings.add(config)
    uow.commit()


def add_to_allowlisting(
  cmd: commands.AddToAllowlisting, uow: unit_of_work.AbstractUnitOfWork
) -> None:
  with uow:
    if not uow.allowlisting.get_by_conditions(asdict(cmd)):
      placement = placement_entities.AllowlistedPlacement(**asdict(cmd))
      uow.allowlisting.add(placement)
      uow.commit()


def remove_from_allowlisting(
  cmd: commands.RemoveFromAllowlisting, uow: unit_of_work.AbstractUnitOfWork
) -> None:
  with uow:
    if allowlisted_placement := uow.allowlisting.get_by_conditions(asdict(cmd)):
      uow.allowlisting.delete(allowlisted_placement[0].id)
      uow.commit()


def migrate_from_old_tasks(
  cmd: commands.MigrateFromOldTasks, uow: unit_of_work.AbstractUnitOfWork
) -> int:
  migrated = 0
  with uow:
    for item in uow.old_tasks.list():
      migrated_task = TaskAdapter(item.to_dict()).from_task_v1()
      uow.tasks.add(migrated_task)
      migrated += 1
    uow.commit()
  return migrated


EVENT_HANDLERS = {
  events.TaskWithScheduleCreated: [task_with_schedule_created],
  events.TaskScheduleUpdated: [task_schedule_updated],
  events.TaskScheduleDeleted: [task_schedule_deleted],
  events.TaskCreated: [task_created],
  events.TaskUpdated: [task_updated],
  events.TaskDeleted: [task_deleted],
}

COMMAND_HANDLERS = {
  commands.RunTask: run_task,
  commands.SaveTask: save_task,
  commands.DeleteTask: delete_task,
  commands.RunManualExclusion: run_manual_exclusion_task,
  commands.PreviewPlacements: run_preview_placements,
  commands.SaveConfig: save_config,
  commands.GetCustomerIds: get_customer_ids,
  commands.GetMccIds: get_mcc_accounts,
  commands.AddToAllowlisting: add_to_allowlisting,
  commands.RemoveFromAllowlisting: remove_from_allowlisting,
  commands.MigrateFromOldTasks: migrate_from_old_tasks,
}
