# Copyright 2024 Google LLC
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

"""Module for converting legacy task v1 to v2."""

from __future__ import annotations

from datetime import datetime

from googleads_housekeeper.domain.core import task
from googleads_housekeeper.services import enums


class TaskAdapter:
  """Maps a V1 Task (dict) into a V2 Task object.

  Attributes:
      task_v1_data: A dictionary containing data of a V1 Task object.
  """

  def __init__(self, task_v1_data: dict) -> None:
    """Initializes a TaskAdapter object.

    Args:
        task_v1_data:
            A dictionary containing data of a V1 Task object.
    """
    self.task_v1_data = task_v1_data

  def from_task_v1(self) -> task.Task:
    """Converts a V1 Task into a V2 Task object.

    Returns:
        Task: A V2 Task object.
    """
    task_dict = {
      'name': self.task_v1_data['task_name'],
      'exclusion_rule': self._build_condition_rules(),
      'customer_ids': self.task_v1_data['customer_id'],
      'date_range': int(self.task_v1_data.get('lookback_days', 0)),
      'from_days_ago': int(self.task_v1_data.get('from_days_ago', 0)),
      'exclusion_level': enums.ExclusionLevelEnum.AD_GROUP,
      'placement_types': self._build_placement_types(),
      'output': self._build_task_output(),
      'status': task.TaskStatus.ACTIVE,
      'schedule': self.task_v1_data.get('schedule', 0),
      'creation_date': datetime.strptime(
        self.task_v1_data['date_created'], '%Y-%m-%d'
      ),
    }
    return task.Task(**task_dict)

  def _build_placement_types(self) -> str:
    placement_types = set()
    if self.task_v1_data.get('gads_data_youtube'):
      placement_types.add('YOUTUBE_VIDEO')
      placement_types.add('YOUTUBE_CHANNEL')
    if self.task_v1_data.get('gads_data_display'):
      placement_types.add('WEBSITE')
    return ', '.join(sorted(placement_types))

  def _build_condition_rules(self) -> str:
    youtube_filters = self._build_youtube_filters()
    google_ads_filters = self._build_gads_filters()
    return ' AND '.join([google_ads_filters] + youtube_filters)

  def _build_youtube_filters(self) -> list[str]:
    youtube_filters: list[str] = []
    yt_country_operator = self.task_v1_data.get('yt_country_operator')
    yt_country_value = self.task_v1_data.get('yt_country_value')
    yt_language_operator = self.task_v1_data.get('yt_language_operator')
    yt_language_value = self.task_v1_data.get('yt_language_value')
    yt_std_character = self.task_v1_data.get('yt_std_character')
    yt_subscriber_operator = self.task_v1_data.get('yt_subscriber_operator')
    yt_subscriber_value = self.task_v1_data.get('yt_subscriber_value')
    yt_video_operator = self.task_v1_data.get('yt_video_operator')
    yt_video_value = self.task_v1_data.get('yt_video_value')
    yt_view_operator = self.task_v1_data.get('yt_view_operator')
    yt_view_value = self.task_v1_data.get('yt_view_value')

    if yt_subscriber_operator is not None and yt_subscriber_value is not None:
      youtube_filters.append(
        'YOUTUBE_CHANNEL_INFO:subscriberCount '
        f'{yt_subscriber_operator}, {yt_subscriber_value},'
      )
    if yt_view_operator is not None and yt_view_value is not None:
      youtube_filters.append(
        'YOUTUBE_CHANNEL_INFO:yt_view_operator '
        f'{yt_view_operator} {yt_view_value}'
      )
    if yt_video_operator is not None and yt_video_value is not None:
      youtube_filters.append(
        'YOUTUBE_CHANNEL_INFO:yt_video_operator '
        f'{yt_video_operator} {yt_video_value}'
      )
    if yt_country_operator is not None and yt_country_value is not None:
      youtube_filters.append(
        'YOUTUBE_CHANNEL_INFO:country '
        f'{yt_country_operator} {yt_country_value}'
      )
    if yt_language_operator is not None and yt_language_value is not None:
      youtube_filters.append(
        'YOUTUBE_CHANNEL_INFO:defaultLanguage '
        f'{yt_language_operator}, {yt_language_value},'
      )
    if yt_std_character is not None and yt_std_character != '':
      youtube_filters.append(
        'YOUTUBE_CHANNEL_INFO:title letter_set latin_only'
        if yt_std_character == '1'
        else 'YOUTUBE_CHANNEL_INFO:title letter_set no_latin'
        if yt_std_character == '0'
        else 'YOUTUBE_CHANNEL_INFO:title letter_set unknown'
      )
    return youtube_filters

  def _build_gads_filters(self) -> str:
    if google_ads_filters := self.task_v1_data.get('gads_filter'):
      return google_ads_filters.replace('metrics.', 'GOOGLE_ADS_INFO:')
    return ''

  def _build_task_output(self) -> task.TaskOutput:
    schedule = int(self.task_v1_data.get('schedule', 0))
    email_alerts = bool(self.task_v1_data.get('email_alerts', False))
    if email_alerts and schedule == 1:
      return task.TaskOutput.EXCLUDE_AND_NOTIFY
    if not email_alerts and schedule == 1:
      return task.TaskOutput.EXCLUDE
    if email_alerts and schedule == 0:
      return task.TaskOutput.NOTIFY
    return task.TaskOutput.EXCLUDE_AND_NOTIFY
