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

"""Setups communication between various parts of the application."""

from __future__ import annotations

from typing import Callable, Type

from googleads_housekeeper.domain import commands, events
from googleads_housekeeper.services import unit_of_work

Message = commands.Command | events.Event


class MessageBus:
  def __init__(
    self,
    uow: unit_of_work.AbstractUnitOfWork,
    event_handlers: dict[Type[events.Event], Callable],
    command_handlers: dict[Type[commands.Command], Callable],
    dependencies: dict,
  ) -> None:
    self.uow = uow
    self.event_handlers = event_handlers
    self.command_handlers = command_handlers
    self.dependencies = dependencies
    self.return_value = None
    self.queue = []

  def handle(self, message: Message):
    self.queue = [message]
    while self.queue:
      message = self.queue.pop(0)
      if isinstance(message, events.Event):
        self.handle_event(message)
      elif isinstance(message, commands.Command):
        self.handle_command(message)

    if self.return_value is not None:
      return self.return_value
    return None

  def handle_command(self, command: commands.Command) -> None:
    handler = self.command_handlers[type(command)]
    result = handler(command)
    self.return_value = result
    self.queue.extend(self.uow.collect_new_events())

  def handle_event(self, event: events.Event) -> None:
    for handler in self.event_handlers[type(event)]:
      handler(event)
      self.queue.extend(self.uow.collect_new_events())
