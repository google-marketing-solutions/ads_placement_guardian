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
"""Module for performing parsing of external entities.

External entity represents a YouTube Channel or Video, Webpage,
Mobile Application or anything that requires connection to external
(non Google Ads) system in order to get information from it.
"""

# pylint: disable=C0330, g-bad-import-order, g-multiple-import

from __future__ import annotations

from garf_core import report

from googleads_housekeeper.domain.external_parsers import parsers


class ExternalEntitiesParser:
  """Performance parsing of external entities (YouTube, Websites, etc.).

  Attributes:
      uow: Unit of work to handle transaction.
  """

  def __init__(self) -> None:
    """Initializes an instance of ExternalEntitiesParser."""

  def parse_specification_chain(
    self,
    entities: report.GarfReport,
    specification,
  ) -> None:
    """Performance parsing of entities via all parsers in specification.

    Args:
        entities:
            Report containing entities that should be parsed.
        specification:
            All possible non Ads specifications. Entities within a report
            can be parsed via different parsers (YouTube, Website, etc.)
        parse_options:
            Options for performing parsing.
    """
    extra_info = {}
    for specification_entries in specification.specifications:
      for specification_entry in specification_entries:
        exclusion_type = specification_entry.exclusion_type.name
        placement_type = exclusion_type.replace('_INFO', '')
        if parsing_callable := parsers.PARSER_MAPPING.get(
          specification_entry.exclusion_type.name
        ):
          extra_info.update(
            parsing_callable(entities, placement_type=placement_type)
          )

    for row in entities:
      if extra_info_entry := extra_info.get(row.placement):
        row['extra_info'] = extra_info_entry
      else:
        row['extra_info'] = None
