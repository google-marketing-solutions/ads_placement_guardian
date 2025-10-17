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
"""Pre-build views for simplifying reads from DB."""

from __future__ import annotations

# pylint: disable=C0330, g-bad-import-order
from dataclasses import asdict
from typing import Any

from googleads_housekeeper.services import unit_of_work


def task(
  task_id: int, uow: unit_of_work.AbstractUnitOfWork
) -> dict[str, Any] | None:
  with uow:
    if uow_task := uow.tasks.get(task_id):
      return asdict(uow_task)
    return None


def tasks(uow: unit_of_work.AbstractUnitOfWork) -> list[dict[str, Any]]:
  with uow:
    uow_tasks: list[dict[str, Any]] = []
    for uow_task in uow.tasks.list():
      if uow_task.status.name == 'INACTIVE':
        continue
      task_dict = uow_task.to_dict()
      task_dict['next_run'] = uow_task.next_run
      accounts = customer_ids(
        uow=uow, accounts=uow_task.customer_ids.split(',')
      )
      task_dict['accounts'] = list({a.get('account_name') for a in accounts})
      if task_executions := executions(uow_task.id, uow):
        for current_execution in sorted(
          task_executions, key=lambda x: x.get('end_time'), reverse=True
        ):
          task_dict['placements_excluded'] = current_execution.get(
            'placements_excluded'
          )
          task_dict['last_run'] = current_execution.get('end_time').strftime(
            '%Y-%m-%d %H-%M'
          )
          break
      else:
        task_dict['placements_excluded'] = None
      uow_tasks.append(task_dict)
    return uow_tasks


def config(uow: unit_of_work.AbstractUnitOfWork) -> list[dict[str, Any]]:
  with uow:
    return [asdict(c) for c in uow.settings.list()]


def allowlisted_placements(
  uow: unit_of_work.AbstractUnitOfWork, account_id: str | None = None
) -> list[dict] | None:
  with uow:
    if account_id:
      if uow_allowlisted_placements := uow.allowlisting.get_by_conditions(
        {'account_id': account_id}
      ):
        return [asdict(t) for t in uow_allowlisted_placements]
    if uow_allowlisted_placements := uow.allowlisting.list():
      return [asdict(t) for t in uow_allowlisted_placements]
  return None


def allowlisted_placements_as_tuples(
  uow: unit_of_work.AbstractUnitOfWork, account_id: str | None = None
) -> list[tuple[str, str, str]]:
  if placements := allowlisted_placements(uow, account_id):
    return [
      (p.get('account_id'), p.get('type'), p.get('name')) for p in placements
    ]
  return []


def execution(
  execution_id: str, uow: unit_of_work.AbstractUnitOfWork
) -> dict[str, Any] | None:
  with uow:
    if task_execution := uow.executions.get(execution_id):
      return asdict(task_execution)
  return None


def executions(
  task_id: str, uow: unit_of_work.AbstractUnitOfWork
) -> list[dict[str, Any]] | None:
  with uow:
    if task_executions := uow.executions.get_by_condition('task', task_id):
      return [asdict(t) for t in task_executions]
  return None


def execution_details(
  task_id: str,
  execution_id: str,
  uow: unit_of_work.AbstractUnitOfWork,
  first_n_placements: int | None = None,
) -> list[dict[str, Any]] | None:
  with uow:
    if uow.executions.get_by_condition('task', task_id):
      if uow_execution_details := uow.execution_details.get_by_condition(
        'execution_id', execution_id
      ):
        results = [asdict(t) for t in uow_execution_details]
        if first_n_placements and first_n_placements < len(results):
          results = results[:first_n_placements]
        return results
  return None


def customer_ids(
  uow: unit_of_work.AbstractUnitOfWork,
  mcc_id: str | None = None,
  accounts: list[str] | None = None,
) -> list[dict[str, Any]]:
  with uow:
    if mcc_id:
      uow_customer_ids = [
        asdict(r)
        for r in uow.customer_ids.list()
        if str(r.mcc_id) == str(mcc_id)
      ]
    elif accounts:
      uow_customer_ids = [
        asdict(r) for r in uow.customer_ids.list() if r.id in accounts
      ]
    else:
      raise ValueError('Neither mcc_id nor accounts were provided')
    return uow_customer_ids


def mcc_ids(uow: unit_of_work.AbstractUnitOfWork) -> list[dict[str, str]]:
  with uow:
    return [asdict(r) for r in uow.mcc_ids.list()]
