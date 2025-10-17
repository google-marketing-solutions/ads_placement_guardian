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

"""Specifies Task to store exclusion specific information."""

from __future__ import annotations

import dataclasses
import datetime
import enum
import math
import uuid
from typing import Final

from croniter import croniter

from googleads_housekeeper.services import enums

_HOURS_IN_DAY: Final[int] = 24


class TaskStatus(enum.Enum):
  """An enumeration representing the status of a task.

  Attributes:
    ACTIVE (int): Represents an active task.
    INACTIVE (int): Represents an inactive task.
  """

  ACTIVE = 0
  INACTIVE = 1


class TaskOutput(enum.Enum):
  """An enumeration representing the artifact/output options for a task.

  Attributes:
    NOTIFY: Output option to notify about the task.
    EXCLUDE: Output option to exclude the task.
    EXCLUDE_AND_NOTIFY: Output option to exclude the task and notify about it.
  """

  NOTIFY = 1
  EXCLUDE = 2
  EXCLUDE_AND_NOTIFY = 3


@dataclasses.dataclass
class OldTask:
  """Defines old_task that needs to be run by an application."""

  _id: int
  customer_id: str
  date_created: str
  email_alerts: bool
  from_days_ago: str
  gads_data_display: bool
  gads_data_youtube: bool
  gads_filter: str
  include_youtube: bool
  lookback_days: str
  schedule: str
  task_id: str
  task_name: str
  yt_country_operator: str
  yt_country_value: str
  yt_language_operator: str
  yt_language_value: str
  yt_std_character: str
  yt_subscriber_operator: str
  yt_subscriber_value: str
  yt_video_operator: str
  yt_video_value: str
  yt_view_operator: str
  yt_view_value: str

  def __post_init__(self) -> None:
    """Ensures safe casting to proper enums."""
    self.__name__ = 'tasks'

  def to_dict(self) -> dict[str, int | str | bool]:
    """Converts class to dictionary.

    Enum attributes of the class are represented as names.
    """
    task_dict = {}
    for key, value in dataclasses.asdict(self).items():
      if hasattr(value, 'value'):
        task_dict[key] = value.name
      else:
        task_dict[key] = value
    return task_dict


@dataclasses.dataclass
class Task:
  """Defines task that needs to be run by an application.

  Task contains all necessary information to find the appropriate placements
  that should be excluded and perform the exclusion.

  Attributes:
    name: Task name.
    exclusion_rule: String version of exclusion rule.
    date_range: Lookback days for data fetching from Google Ads API.
    from_days_ago: start_date of data fetching from Google Ads API.
    exclusion_level: Level of exclusion (AD_GROUP, CAMPAIGN, etc.).
    output: Desired action (EXCLUDE, NOTIFY, etc.)
    status: Task status.
    schedule: Optional task schedule.
    creation_date: Time when task was created.
    id: Unique task identifier.
  """

  name: str
  exclusion_rule: str
  customer_ids: str
  date_range: int = 7
  from_days_ago: int = 0
  exclusion_level: enums.ExclusionLevelEnum = enums.ExclusionLevelEnum.AD_GROUP
  placement_types: str | None = None
  output: TaskOutput = TaskOutput.EXCLUDE_AND_NOTIFY
  status: TaskStatus = TaskStatus.ACTIVE
  schedule: str = '0'
  creation_date: datetime.datetime = datetime.datetime.now()
  id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))

  def __post_init__(self) -> None:
    """Ensures safe casting to proper enums."""
    self.output = self._cast_to_enum(TaskOutput, self.output)
    self.status = self._cast_to_enum(TaskStatus, self.status)
    self.exclusion_level = self._cast_to_enum(
      enums.ExclusionLevelEnum, self.exclusion_level
    )

  def to_dict(self) -> dict[str, int | str]:
    """Converts class to dictionary.

    Enum attributes of the class are represented as names.
    """
    task_dict = {}
    for key, value in dataclasses.asdict(self).items():
      if hasattr(value, 'value'):
        task_dict[key] = value.name
      else:
        task_dict[key] = value
    return task_dict

  @property
  def cron_schedule(self) -> str | None:
    """Builds cron schedule based on creation time and schedule."""
    minute = self.creation_date.strftime('%M')
    hour = self.creation_date.strftime('%H')

    if not (schedule := self.schedule) or self.schedule == '0':
      return None
    if 0 < int(schedule) < _HOURS_IN_DAY:
      schedule = f'{minute} */{schedule} * * *'
    elif int(schedule) >= _HOURS_IN_DAY:
      days = math.floor(int(self.schedule) / _HOURS_IN_DAY)
      schedule = f'{minute} {hour} */{days} * *'
    return schedule

  @property
  def start_date(self) -> str:
    """Formatted start_date."""
    return (
      (
        datetime.datetime.now()
        - datetime.timedelta(days=int(self.from_days_ago + self.date_range))
      )
      .date()
      .strftime('%Y-%m-%d')
    )

  @property
  def end_date(self) -> str:
    """Formatted end_date."""
    return (
      (
        datetime.datetime.now()
        - datetime.timedelta(days=int(self.from_days_ago))
      )
      .date()
      .strftime('%Y-%m-%d')
    )

  @property
  def accounts(self) -> list[str]:
    """Formatted account list."""
    return (
      self.customer_ids.split(',')
      if isinstance(self.customer_ids, str)
      else self.customer_ids
    )

  @property
  def next_run(self) -> str:
    """Next task run as a cron expression."""
    if not (schedule := self.cron_schedule):
      return 'Not scheduled'
    return (
      croniter(schedule, datetime.datetime.now())
      .get_next(datetime.datetime)
      .strftime('%Y-%m-%d %H:%M')
    )

  def _cast_to_enum(
    self, enum_: type[enum.Enum], value: str | enum.Enum
  ) -> enum.Enum:
    """Helper method for converted in string to desired enum.

    Args:
      enum_: Enum class to server as conversion base.
      value: Value to perform the conversion.

    Returns:
      Correct enum based on provided value.
    """
    return enum_[value] if isinstance(value, str) else value
