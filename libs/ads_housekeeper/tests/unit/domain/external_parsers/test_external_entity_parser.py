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

from gaarf.report import GaarfReport
from googleads_housekeeper.domain.core import exclusion_specification
from googleads_housekeeper.domain.external_parsers import (
  external_entity_parser,
  website_parser,
)


def test_external_entity_parser(mocker, fake_tracer):
  external_parser = external_entity_parser.ExternalEntitiesParser(
    tracer=fake_tracer
  )
  specification = (
    exclusion_specification.ExclusionSpecification.from_expression(
      'WEBSITE_INFO:title contains example'
    )
  )
  report = GaarfReport(
    results=[['parsed-example.com', 'WEBSITE']],
    column_names=['placement', 'placement_type'],
  )
  values = {
    'title': 'example title',
    'description': 'example description',
    'keywords': 'example keywords',
  }
  mocker.patch(
    'googleads_housekeeper.domain.external_parsers.website_parser.'
    'WebSiteParser.parse',
    return_value=[
      website_parser.WebsiteInfo(
        **values,
        placement='parsed-example.com',
        is_processed=True,
      )
    ],
  )

  external_parser.parse_specification_chain(
    entities=report, specification=specification
  )
  assert report[0]['extra_info'].to_dict() == values
