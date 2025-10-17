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

"""Module for defining various notification channels."""

from __future__ import annotations

import abc
import dataclasses
import os

import gaarf
import slack_sdk
from google.appengine.api import mail

from googleads_housekeeper.domain.core.task import TaskOutput


@dataclasses.dataclass
class MessagePayload:
  """Contains information to be sent via a given notification channel.

  Attributes:
      task_id:
          task identifier.
      task_name:
          task name.
      task_formula:
          task full exclusion_rule.
      task_output:
          task action verb.
      placements_excluded_sample:
          optional report with top N placements that were excluded.
      total_placement_excluded:
          number of all excluded placements by a given task.
      recipient:
          who should receive the notification (could be email, slack channel).
  """

  task_id: str
  task_name: str
  task_formula: str
  task_output: TaskOutput
  placements_excluded_sample: gaarf.report.GaarfReport | None
  total_placement_excluded: int
  recipient: str


class BaseNotifications(abc.ABC):
  """Base class for sending notifications."""

  @abc.abstractmethod
  def send(self, payload: MessagePayload) -> None:
    """Transforms payload and sends it via a given notification channel."""
    raise NotImplementedError


def get_region_initials(region: str):
  """Reads the region value and returns its initials.

  Args:
      region (str): The region's name.

  Returns:
      str: The initials of the region value.
  """
  return ''.join(word[0] for word in region.lower().split('-'))


class GoogleCloudAppEngineEmailNotifications(BaseNotifications):
  """Implements sending emails with App Engine.

  Attributes:
      project_id: Google Cloud project id.
  """

  def __init__(self, project_id: str, appengine_region: str) -> None:
    """Initializes GoogleCloudAppEngineEmailNotifications class.

    Args:
        project_id: Id of Google Cloud Project.
        appengine_region: Appengine's Region.
    """
    self.project_id = project_id
    self.appengine_region_initials = get_region_initials(appengine_region)

  def send(self, payload: MessagePayload, **kwargs: str) -> None:
    """Sends payload to via appengine mailer."""
    message = self._prepare_message(payload)
    message.send()

  def _prepare_message(self, payload: MessagePayload) -> mail.Message:
    """Generates message from a payload."""
    sender = f'exclusions@{self.project_id}.appspotmail.com'
    if placements_excluded := payload.placements_excluded_sample:
      output = payload.task_output
      subject = (
        f"{'Detected' if output == TaskOutput.NOTIFY else 'Excluded'} "
        f'{payload.total_placement_excluded} placements'
      )
      body = self._generate_notification_html(
        payload.task_id,
        payload.task_name,
        payload.task_formula,
        payload.task_output,
        placements_excluded,
      )
    else:
      subject = 'No placements were detected'
      body = ''
    recipient = payload.recipient.split(',')
    if body:
      return mail.EmailMessage(
        sender=sender, to=recipient, subject=subject, html=body
      )
    return mail.EmailMessage(
      sender=sender, to=recipient, subject=subject, body=body
    )

  def _generate_notification_html(
    self,
    task_id: str,
    task_name: str,
    task_formula: str,
    task_action_verb: TaskOutput,
    placements: gaarf.report.GaarfReport,
  ) -> str:
    html_body = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width,
            initial-scale=1.0">
            <title>CPR Placement Exclusion Alert</title>
            <style type="text/css">
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f8f8f8; /* Light background for visual
            separation */
        }

        .container {
            background-color: #fff; /* White background for content */
            border: 1px solid #ddd;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1); /* Subtle shadow for depth */
        }

        h2 {
            color: #2c3e50; /* A darker heading color */
            margin-bottom: 15px;
            font-weight: bold;
        }

        .task-link {
            color: #007bff;
            text-decoration: none;
            font-weight: 600; /* Slightly bolder task link */
        }

        .placement-list {
            list-style: disc;
            margin-left: 20px;
        }

        .logo-placeholder {
            text-align: center;
            margin-top: 20px;
        }

        .logo-placeholder img {
        max-width: 150px; /* Limit logo size */
        }

            </style>
        </head>
        <body>
            <p>Please do not reply to this email.</p>

            <div class="container">
                <h2>CPR Placement Exclusion Alert</h2>"""

    html_body += f"""
                <p>The CPR tool has {('detected' if task_action_verb == TaskOutput.NOTIFY
                                                               else 'excluded')} the following placements
                based on your defined thresholds:</p>
                <p><strong>Task Name: </strong>
                <a href="https://{self.project_id}.
                {self.appengine_region_initials}.r.appspot.com/newtask?task={task_id}"
                class="task-link" target="_blank" title="View Task Details">
                {task_name}</a></p>
                <p><strong>Task Logic: </strong>{_to_human_readable(task_formula)}
                </p>"""

    for placement in placements:
      placement_name = placement.get('name')
      placement_url = placement.get('placement')
      placement_url_html = (
        '' if placement_url == placement_name else f'<br/>{placement_url}'
      )
      html_body += f"""<ul class="placement-list">
            <strong>Placement Name:</strong> {placement_name}
            {placement_url_html}
            <br/>
            Reason: {_to_human_readable(getattr(placement, 'reason',
                                                'Task without filters'))}</li>

        </ul>
                  """
    html_body += """
            </div>

            <div class="logo-placeholder">
                <img src="https://services.google.com/fh/files/emails/gtech_logo_transparent.png"
                alt="gPS Ads Logo" width="32" height="32">
            </div>

            <p>Please do not reply to this email.</p>
        </body>
        </html>
        """
    return html_body


def _to_human_readable(text: str) -> str:
  return text.lower().replace('_', ' ')


class SlackNotifications(BaseNotifications):
  """Implements sending emails with Slack.

  Attributes:
      bot_token: Slack API bot token.
      client: initialized Slack WebClient.
  """

  def __init__(self, bot_token: str) -> None:
    """Initializes SlackNotifications class.

    Args:
        bot_token: Slack API Token.
    """
    self.client = slack_sdk.WebClient(token=bot_token)

  def send(self, payload: MessagePayload) -> None:
    """Sends payload to Slack channel."""
    task_name = payload.task_name
    channel = payload.recipient
    if not (placements_excluded_sample := payload.placements_excluded_sample):
      self.client.chat_postMessage(
        channel=channel, text=f'{task_name}: No placements were excluded'
      )
    else:
      file = (
        placements_excluded_sample['name']
        .to_pandas()
        .to_csv(index=False, sep='\t')
      )
      self.client.files_upload(
        channels=channel,
        initial_comment=(
          f'{task_name}: '
          f'{payload.total_placement_excluded} placements excluded'
        ),
        filename=f'{task_name}.tsv' if task_name else 'cpr.tsv',
        content=file,
      )


class ConsoleNotifications(BaseNotifications):
  """Implements sending notification to standard output."""

  def send(self, payload: MessagePayload) -> None:
    """Prints payload to standard output."""
    print(payload)


class NullNotifications(BaseNotifications):
  """Implements special case for incorrect notification channel."""

  def __init__(self, notification_type: str) -> None:
    self.notification_type = notification_type

  def send(self, payload: MessagePayload) -> None:
    raise ValueError(
      f'Cannot send notification via '
      f'"{self.notification_type}" notification channel'
    )


class NotificationFactory:
  """Builds notification service for a given notification type.

  NotificationFactory contains all possible types of notification channels
  defined in the module.

  Attributes:
      types: mapping between name of services and its class.

  """

  types: dict[str, dict[str, BaseNotifications | dict]] = {}

  def __init__(self) -> None:
    self.load_types()

  def load_types(self) -> None:
    self.types['email'] = {
      'type': GoogleCloudAppEngineEmailNotifications,
      'args': {
        'project_id': os.environ.get('GOOGLE_CLOUD_PROJECT'),
        'appengine_region': os.environ.get('APPENGINE_REGION', 'europe-west1'),
      },
    }
    self.types['slack'] = {
      'type': SlackNotifications,
      'args': {'bot_token': os.environ.get('CPR_SLACK_BOT_TOKEN')},
    }
    self.types['console'] = {'type': ConsoleNotifications, 'args': {}}

  def create_notification_service(
    self, notification_type: str
  ) -> type[BaseNotifications]:
    if notification_type in self.types:
      if args := self.types[notification_type].get('args'):
        return self.types[notification_type].get('type')(**args)
      return self.types[notification_type].get('type')()
    return NullNotifications(notification_type)
