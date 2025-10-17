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

"""Module for defining an interface for parsers."""

from __future__ import annotations

import abc
import collections
import dataclasses
import datetime
import uuid
from typing import TypeVar


@dataclasses.dataclass
class EntityInfo:
  """Contains base information on parsed entity.

  Attributes:
      placement: Name of parsed placement.
      last_processed_time: Current time when processing happened.
      id: Unique identifier of placement.
  """

  placement: str
  last_processed_time: datetime = dataclasses.field(
    default=datetime.datetime.now(), compare=False
  )
  id: str = dataclasses.field(
    default_factory=lambda: str(uuid.uuid4()), compare=False
  )


T = TypeVar('T', bound='EntityInfo')


class BaseParser(abc.ABC):
  """Base class for all external parsers."""

  @abc.abstractmethod
  def parse(self, placements: collections.abs.Sequence[str]) -> list[T]:
    """Parses provided placements.

    Placement could be website URL, YouTube channel or video id.

    Args:
        placements: Sequence of placements identifiers.

    Returns:
        List of parsed entities in subclass *Info format.
    """
    raise NotImplementedError


class NullParser(BaseParser):
  """Special case of invalid parser."""

  def parse(self, placements):
    return placements
