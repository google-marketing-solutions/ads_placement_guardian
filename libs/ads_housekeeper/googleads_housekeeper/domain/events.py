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
"""Specifies events to be sent to message bus."""

# pylint: disable=C0330, g-bad-import-order, missing-class-docstring

from __future__ import annotations

from dataclasses import dataclass


class Event:
  """Base class for all events."""


@dataclass
class TaskCreated(Event):
  task_id: str


@dataclass
class TaskWithScheduleCreated(Event):
  task_id: str
  task_name: str
  schedule: str
  appengine_service: str | None = None


@dataclass
class TaskUpdated(Event):
  task_id: str


@dataclass
class TaskScheduleUpdated(Event):
  task_id: str
  schedule: str
  appengine_service: str | None = None


@dataclass
class TaskRun(Event):
  task_id: str


@dataclass
class TaskDeleted(Event):
  task_id: str


@dataclass
class TaskScheduleDeleted(Event):
  task_id: str


@dataclass
class EntityExcluded(Event):
  criterion_id: int
  criterion_type: str
  customer_id: int
  level_id: int  # can be ad_group, campaign_id, or customer_id


@dataclass
class EntityAllowlisted(Event):
  criterion_id: int
  criterion_type: str
  customer_id: int
  level_id: int  # can be ad_group, campaign_id, or customer_id
