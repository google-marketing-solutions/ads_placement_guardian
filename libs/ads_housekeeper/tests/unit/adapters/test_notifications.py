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

# pylint: disable=C0330, g-bad-import-order, g-multiple-import, missing-class-docstring, missing-module-docstring, missing-function-docstring

from __future__ import annotations

import gaarf
import pytest
from googleads_housekeeper.adapters import notifications
from googleads_housekeeper.domain.core.task import TaskOutput


class TestNotifications:
  @pytest.fixture
  def empty_payload(self):
    return notifications.MessagePayload(
      task_id='450c7bc6-5fe1-402c-9c23-53f1818903e1',
      task_name='test_task',
      task_formula='GOOGLE_ADS_INFO:impressions > 10',
      task_output=TaskOutput.EXCLUDE,
      placements_excluded_sample=None,
      total_placement_excluded=0,
      recipient='test_recipient',
    )

  @pytest.mark.parametrize(
    'notification_type, notification_class',
    [
      ('slack', notifications.SlackNotifications),
      ('email', notifications.GoogleCloudAppEngineEmailNotifications),
      ('console', notifications.ConsoleNotifications),
      ('unknown', notifications.NullNotifications),
    ],
  )
  def test_create_notification_service_creates_correct_notification_class(
    self, notification_type, notification_class
  ):
    notification_service = (
      notifications.NotificationFactory().create_notification_service(
        notification_type=notification_type
      )
    )
    assert isinstance(notification_service, notification_class)

  def test_sendnotification_raises_error_for_unknown_notification_type(
    self, empty_payload
  ):
    notification_service = notifications.NullNotifications(
      notification_type='unknown'
    )
    with pytest.raises(ValueError):
      notification_service.send(empty_payload)


class TestGoogleCloudAppEngineEmailNotifications:
  def test_prepare_message_returns_correct_message_elements_for_empty_payload(
    self,
  ):
    empty_payload = notifications.MessagePayload(
      task_id='450c7bc6-5fe1-402c-9c23-53f1818903e1',
      task_name='test_task',
      task_formula='GOOGLE_ADS_INFO:impressions > 10',
      task_output=TaskOutput.EXCLUDE,
      placements_excluded_sample=None,
      total_placement_excluded=0,
      recipient='test_recipient',
    )
    sender = notifications.GoogleCloudAppEngineEmailNotifications(
      project_id='fake-project', appengine_region='fake-region'
    )
    message = sender._prepare_message(empty_payload)
    assert message.body == ''
    assert message.to == ['test_recipient']
    assert message.subject == 'No placements were detected'
    assert message.sender == 'exclusions@fake-project.appspotmail.com'
    assert '' in message.body

  def test_prepare_message_returns_correct_message_elements_for_non_empty_payload(
    self,
  ):
    excluded_placements = gaarf.report.GaarfReport(
      results=[
        [
          'test-placement',
          'example.com',
          'GOOGLE_ADS_INFO:impressions > 10',
        ]
      ],
      column_names=['name', 'placement', 'reason'],
    )
    payload_with_placements = notifications.MessagePayload(
      task_id='450c7bc6-5fe1-402c-9c23-53f1818903e1',
      task_name='test_task',
      task_formula='GOOGLE_ADS_INFO:impressions > 10',
      task_output=TaskOutput.EXCLUDE,
      placements_excluded_sample=excluded_placements,
      total_placement_excluded=1,
      recipient='test_recipient',
    )
    sender = notifications.GoogleCloudAppEngineEmailNotifications(
      project_id='fake-project', appengine_region='fake-region'
    )
    message = sender._prepare_message(payload_with_placements)
    assert message.to == ['test_recipient']
    assert message.subject == 'Excluded 1 placements'
    assert message.sender == 'exclusions@fake-project.appspotmail.com'
    print(message.html)
    assert 'test-placement' in message.html
    assert 'example.com' in message.html

  def test_prepare_message_for_notify_returns_detection_text(self):
    excluded_placements = gaarf.report.GaarfReport(
      results=[
        [
          'test-placement',
          'example.com',
          'GOOGLE_ADS_INFO:impressions > 10',
        ]
      ],
      column_names=['name', 'placement', 'reason'],
    )
    payload_with_placements = notifications.MessagePayload(
      task_id='450c7bc6-5fe1-402c-9c23-53f1818903e1',
      task_name='test_task',
      task_formula='GOOGLE_ADS_INFO:impressions > 10',
      task_output=TaskOutput.NOTIFY,
      placements_excluded_sample=excluded_placements,
      total_placement_excluded=1,
      recipient='test_recipient',
    )
    sender = notifications.GoogleCloudAppEngineEmailNotifications(
      project_id='fake-project', appengine_region='fake-region'
    )
    message = sender._prepare_message(payload_with_placements)
    assert message.subject == 'Detected 1 placements'
    assert 'CPR tool has detected' in message.html

  def test_prepare_message_for_exclude_and_notify_returns_exclusion_text(self):
    excluded_placements = gaarf.report.GaarfReport(
      results=[
        [
          'test-placement',
          'example.com',
          'GOOGLE_ADS_INFO:impressions > 10',
        ]
      ],
      column_names=['name', 'placement', 'reason'],
    )
    payload_with_placements = notifications.MessagePayload(
      task_id='450c7bc6-5fe1-402c-9c23-53f1818903e1',
      task_name='test_task',
      task_formula='GOOGLE_ADS_INFO:impressions > 10',
      task_output=TaskOutput.EXCLUDE_AND_NOTIFY,
      placements_excluded_sample=excluded_placements,
      total_placement_excluded=1,
      recipient='test_recipient',
    )
    sender = notifications.GoogleCloudAppEngineEmailNotifications(
      project_id='fake-project', appengine_region='fake-region'
    )
    message = sender._prepare_message(payload_with_placements)
    assert message.subject == 'Excluded 1 placements'
    assert 'CPR tool has excluded' in message.html
