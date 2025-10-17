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

import pytest
import requests
from googleads_housekeeper.domain.external_parsers import website_parser


class TestWebSiteParser:
  @pytest.mark.parametrize(
    'input_url,formatted_url',
    [
      ('example.com', 'https://example.com'),
      ('http://example.com', 'http://example.com'),
      ('https://example.com', 'https://example.com'),
    ],
  )
  def test_convert_url(self, input_url, formatted_url):
    url = website_parser.WebSiteParser()._convert_placement_to_url(input_url)
    assert url == formatted_url

  @pytest.mark.parametrize(
    'attribute,expected_value',
    [
      ('is_processed', True),
      ('title', 'example title'),
      ('description', 'example description'),
      ('keywords', 'example keywords'),
    ],
  )
  def test_parse_website_success(self, mocker, attribute, expected_value):
    mocker.patch(
      'googleads_housekeeper.domain.external_parsers.website_parser.'
      'WebSiteParser.parse',
      return_value=[
        website_parser.WebsiteInfo(
          placement='example.com',
          title='example title',
          description='example description',
          keywords='example keywords',
          is_processed=True,
        )
      ],
    )

    parser = website_parser.WebSiteParser()
    website_info = parser.parse(['example.com'])
    assert getattr(website_info[0], attribute) == expected_value
    parser.parse.assert_called_once_with(['example.com'])

  @pytest.mark.parametrize(
    'attribute,expected_value',
    [
      ('is_processed', False),
      ('title', ''),
      ('description', ''),
      ('keywords', ''),
    ],
  )
  def test_parse_website_raise_error_empty_result(
    self, mocker, attribute, expected_value
  ):
    mocker.patch(
      'requests.get', side_effect=requests.exceptions.ConnectionError
    )
    parser = website_parser.WebSiteParser()
    website_info = parser.parse(['non-example.com'])
    assert getattr(website_info[0], attribute) == expected_value
