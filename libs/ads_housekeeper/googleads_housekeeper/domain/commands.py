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
"""Specifies commands to be sent to message bus."""

# pylint: disable=C0330, g-bad-import-order

from __future__ import annotations

import dataclasses
from collections import abc

from googleads_housekeeper.domain.core import execution, task


class Command:
  """Base class for all commands."""


@dataclasses.dataclass
class RunTask(Command):
  """Run task with a specified id."""

  id: int
  type: execution.ExecutionTypeEnum
  exclusion_rule: str = ''
  save_to_db: bool = True


@dataclasses.dataclass
class SaveTask(Command):
  """Saves tasks to DB."""

  exclusion_rule: str
  customer_ids: str | list[str]
  from_days_ago: int = 0
  date_range: int = 7
  exclusion_level: str = 'AD_GROUP'
  output: str = task.TaskOutput.EXCLUDE_AND_NOTIFY.name
  name: str | None = None
  schedule: str = '0'
  placement_types: str | None = None
  task_id: str | None = None

  def __post_init__(self):
    self.customer_ids = (
      ','.join(self.customer_ids)
      if isinstance(self.customer_ids, abc.MutableSequence)
      else self.customer_ids
    )


@dataclasses.dataclass
class DeleteTask(Command):
  """Deletes tasks with a specified id."""

  task_id: int


@dataclasses.dataclass
class RunManualExclusion(Command):
  """Performs placement exclusion at specified level."""

  customer_ids: str
  placements: list[list]
  header: list[str]
  exclusion_level: str


def ensure_tuple(value):
  """Guarantees that value is a tuple."""
  if isinstance(value, str):
    return tuple(value.split(','))
  return value


@dataclasses.dataclass
class PreviewPlacements(Command):
  """Get placements for exclusion."""

  exclusion_rule: str
  placement_types: tuple[str, ...] | None
  customer_ids: str | list[str]
  from_days_ago: int
  date_range: int
  exclusion_level: str = 'AD_GROUP'
  exclude_and_notify: str = 'EXCLUDE_AND_NOTIFY'
  save_to_db: bool = False
  always_fetch_youtube_preview_mode: bool = False
  limit: int | None = 1_000

  def __post_init__(self):
    self.placement_types = ensure_tuple(self.placement_types)
    self.from_days_ago = int(self.from_days_ago)
    self.date_range = int(self.date_range)

  def to_dict(self):
    """Converts command to dict."""
    return dataclasses.asdict(self)


@dataclasses.dataclass
class AddToAllowlisting(Command):
  """Adds placement to allowlisting for an account."""

  type: str
  name: str
  account_id: str


@dataclasses.dataclass
class RemoveFromAllowlisting(Command):
  """Removes placement to allowlisting for an account."""

  type: str
  name: str
  account_id: str


@dataclasses.dataclass
class SaveConfig(Command):
  """Saves application config to db."""

  id: str
  mcc_id: str
  email_address: str
  always_fetch_youtube_preview_mode: bool = False
  save_to_db: bool = False


@dataclasses.dataclass
class GetCustomerIds(Command):
  """Gets all child accounts under MCC."""

  mcc_id: str


@dataclasses.dataclass
class GetMccIds(Command):
  """Gets all MCC under a specified MCC."""

  root_mcc_id: int


@dataclasses.dataclass
class MigrateFromOldTasks(Command):
  """Performs migration of tasks in an old format."""
