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

"""Module for defining configuration entities."""

from __future__ import annotations

import dataclasses
import uuid


@dataclasses.dataclass
class Config:
  """Represents configuration settings of the application.

  Attributes:
    mcc_id:
      Manager account perform operations.
    email_address:
      Email address to send notofications to.
    always_fetch_youtube_preview_mode:
      Whether to fetch YouTube metadata when previewing placements.
    save_to_db:
      Whether to save external parsing results to a database.
    id: Unique identifier of the configuration.
  """

  mcc_id: str
  email_address: str
  always_fetch_youtube_preview_mode: bool = True
  save_to_db: bool = True
  id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))


@dataclasses.dataclass
class CustomerIds:
  """Represents mapping between manager and child accounts.

  Attributes:
    mcc_id: Manager account perform operations.
    account_name: Child account name.
    account_name: Child account id.
  """

  mcc_id: str
  account_name: str
  id: str


@dataclasses.dataclass
class MccIds:
  """Represents mapping between manager name and its id.

  Attributes:
    id: Manager account perform operations.
    account_name: Manager account name.
  """

  id: str
  account_name: str
