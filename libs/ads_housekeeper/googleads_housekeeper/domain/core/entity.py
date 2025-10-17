# Copyright 2022 Google LLC
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

"""Module for specifying base classes for concrete queries.

Ads Housekeeper can perform changes to Google Ads in various ways (i.e. by
excluding placements from accounts). In order to enforce certain rules when
extending the solution various base classes are added so child classes always
contain required fields.
"""

from __future__ import annotations

from gaarf import base_query


class Entity:
  """Base class for all entities."""


class ExcludableEntity(base_query.BaseQuery):
  """Specifies fields that form an entity that can be excluded.

  Attributes:
    base_query_text:
      A Gaarf query text template that contains aliases specified
      in `required_fields`.

  Raises:
    ValueError:
      If subclass base_query_text does not contain all required fields.
  """

  base_query_text = ''

  def __init_subclass__(cls) -> None:
    required_fields = (
      'placement_type',
      'placement',
    )
    super().__init_subclass__()
    missing_fields: list[str] = []
    missing_fields = [
      field for field in required_fields if field not in cls.base_query_text
    ]
    if missing_fields:
      raise ValueError(
        'query_text does not contain required fields: ' f'{missing_fields}'
      )
