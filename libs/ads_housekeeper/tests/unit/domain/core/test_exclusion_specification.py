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

import dataclasses

import pytest
from gaarf.report import GaarfReport
from googleads_housekeeper.domain.core import (
  exclusion_specification,
  rules_parser,
)


@dataclasses.dataclass
class FakePlacement:
  campaign_id: int = 1
  campaign_name: str = '01_test_campaign'
  placement: str = 'example.com'
  clicks: int = 10
  ctr: float = 0.4
  placement_type: str = 'WEBSITE'


@pytest.fixture
def placement():
  return FakePlacement()


class TestAdsExclusionSpecificationEntry:
  @pytest.mark.parametrize('expression', ['single_name', 'single_name >'])
  def test_invalid_expression_length_raises_value_error(self, expression):
    with pytest.raises(ValueError, match='Incorrect expression *'):
      exclusion_specification.AdsExclusionSpecificationEntry(expression)

  def test_invalid_expression_operator_raises_value_error(self):
    with pytest.raises(ValueError, match='Incorrect operator *'):
      exclusion_specification.AdsExclusionSpecificationEntry('clicks ? 0')

  @pytest.fixture(
    params=[
      'clicks > 1',
      'clicks = 10',
      'ctr < 0.6',
      'placement_type = WEBSITE',
      'placement_type contains WEB',
      'campaign_name regexp ^01.+',
    ]
  )
  def ads_exclusion_specification_success(self, request):
    return exclusion_specification.AdsExclusionSpecificationEntry(request.param)

  @pytest.fixture(
    params=[
      'clicks > 100',
      'clicks != 10',
      'ctr > 0.6',
      'placement_type = MOBILE_APPLICATION',
      'placement_type contains MOBILE',
      'campaign_name regexp ^02.+',
    ]
  )
  def ads_exclusion_specification_fail(self, request):
    return exclusion_specification.AdsExclusionSpecificationEntry(request.param)

  def test_placement_safisties_ads_exclusion_specification(
    self, placement, ads_exclusion_specification_success
  ):
    assert ads_exclusion_specification_success.is_satisfied_by(placement)

  def test_placement_does_not_satisfy_ads_exclusion_specification(
    self, placement, ads_exclusion_specification_fail
  ):
    assert not ads_exclusion_specification_fail.is_satisfied_by(placement)

  def test_is_satisfied_by_raises_value_error_when_non_existing_entity_name_is_provided(  # noqa: E501
    self, placement
  ):
    specification = exclusion_specification.AdsExclusionSpecificationEntry(
      'fake_name > 0'
    )
    with pytest.raises(ValueError):
      specification.is_satisfied_by(placement)


class TestExclusionSpecificationEntry:
  @pytest.fixture
  def rules(self):
    return rules_parser.generate_rules(
      raw_rules=[
        (
          'GOOGLE_ADS_INFO:clicks > 1, '
          'GOOGLE_ADS_INFO:conversion_name regexp test_conversion'
        )
      ]
    )

  @pytest.fixture
  def ads_specification_entry(self):
    return exclusion_specification.AdsExclusionSpecificationEntry(
      expression='clicks > 1'
    )

  @pytest.fixture
  def ads_specification_entry_conversion_split(self):
    return exclusion_specification.AdsExclusionSpecificationEntry(
      expression='conversion_name regexp test_conversion'
    )

  @pytest.fixture
  def sample_exclusion_specification(
    self,
    ads_specification_entry,
    ads_specification_entry_conversion_split,
  ):
    return exclusion_specification.ExclusionSpecification(
      specifications=[
        [ads_specification_entry, ads_specification_entry_conversion_split],
      ]
    )

  @pytest.fixture
  def placements(self):
    return GaarfReport(
      results=[
        [
          'youtube_video',
          'YOUTUBE_VIDEO',
          10,
          'test_conversion',
          0,
        ]
      ],
      column_names=[
        'placement',
        'placement_type',
        'clicks',
        'conversion_name',
        'conversions_',
      ],
    )

  def test_true_exclusion_specification(self, sample_exclusion_specification):
    assert bool(sample_exclusion_specification) is True

  def test_placement_satisfies_ads_exclusion_specifications_list(
    self, ads_specification_entry
  ):
    specification = exclusion_specification.ExclusionSpecification(
      specifications=[[ads_specification_entry]]
    )
    assert specification.satisfies(FakePlacement(clicks=10))

  def test_placement_does_not_satisfy_ads_exclusion_specifications_list(
    self, ads_specification_entry
  ):
    specification = exclusion_specification.ExclusionSpecification(
      specifications=[[ads_specification_entry]]
    )
    assert not specification.satisfies(FakePlacement(clicks=0))

  def test_get_correct_ads_entries(
    self,
    sample_exclusion_specification,
    ads_specification_entry,
    ads_specification_entry_conversion_split,
  ):
    expected_exclusion_specifications = (
      exclusion_specification.ExclusionSpecification(
        specifications=[
          [ads_specification_entry, ads_specification_entry_conversion_split]
        ]
      )
    )
    ads_specs = sample_exclusion_specification.ads_specs_entries
    assert ads_specs == expected_exclusion_specifications

  def test_parser_generate_rules_explicit_types(
    self, rules, sample_exclusion_specification
  ):
    specification = exclusion_specification.ExclusionSpecification.from_rules(
      rules
    )
    assert specification == sample_exclusion_specification

  def test_apply_specifications(
    self, sample_exclusion_specification, placements
  ):
    expected_result = GaarfReport(
      results=[
        [
          'youtube_video',
          'YOUTUBE_VIDEO',
          10,
          'test_conversion',
          0,
        ],
      ],
      column_names=[
        'placement',
        'placement_type',
        'clicks',
        'conversion_name',
        'conversions_',
      ],
    )
    result = sample_exclusion_specification.apply_specifications(placements)
    assert result['placement'] == expected_result['placement']
