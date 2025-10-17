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

"""Module for defining execution objects."""

from __future__ import annotations

import dataclasses
import datetime
import enum
import uuid


class ExecutionTypeEnum(enum.Enum):
  """Holds type of Task execution."""

  SCHEDULED = 0
  MANUAL = 1


@dataclasses.dataclass
class Execution:
  """Holds information of a particular task run.

  Attributes:
    task: Id of a task.
    start_date: Time when execution started.
    end_date: Time when execution ended.
    placements_excluded: Number of excluded placements.
    type: Type of execution (MANUAL, SCHEDULED).
    id: Unique identifier of execution.
  """

  task: int
  start_time: datetime.datetime
  end_time: datetime.datetime
  placements_excluded: int
  type: ExecutionTypeEnum
  id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))

  def __post_init__(self) -> None:
    """Ensures that strings are always cast to proper enum."""
    self.type = self._cast_to_enum(ExecutionTypeEnum, self.type)

  def _cast_to_enum(
    self, enum_: type[enum.Enum], value: str | enum.Enum
  ) -> enum.Enum:
    """Cast to proper enum."""
    return enum_[value] if isinstance(value, str) else value


@dataclasses.dataclass
class ExecutionDetails:
  """Holds detailed information on a particular execution.

  Attributes:
    execution_id: Unique identifier of an execution.
    placement: Placement identifier that was excluded during the execution.
    placement_type: Type of excluded placement.
    reason: Reason for exclusion.
    id: Unique identifier of execution details entry.
  """

  execution_id: str
  placement: str
  placement_type: str
  reason: str
  id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
