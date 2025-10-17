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
"""Module for building and applying various specification.

ExclusionSpecification holds an expression is checked against a particular
GaarfRow object to verify whether or not this expression is true.
"""
# pylint: disable=C0330, g-bad-import-order, g-multiple-import

from __future__ import annotations

import dataclasses
import itertools
import logging
import math
import re
from collections.abc import Sequence

from gaarf import report

from googleads_housekeeper.domain.core import rules_parser
from googleads_housekeeper.services import enums


@dataclasses.dataclass(frozen=True)
class RuntimeOptions:
  """Defines options for applying specifications.

  Attributes:
    is_conversion_query: Whether Gaarf query contains conversion split.
    conversion_name: Name(s) of conversion(s) for conversion query.
    conversion_rules: All rules related to conversion split.
  """

  is_conversion_query: bool = False
  conversion_name: str = ''
  conversion_rules: list[BaseExclusionSpecificationEntry] = dataclasses.field(
    default_factory=list
  )


class BaseExclusionSpecificationEntry:
  """Base class for holding logic applicable to all specifications.

  Attributes:
    name:
      Name of the metric/dimension from Google Ads.
    operator:
      Comparator used to evaluate the expression.
    value:
      Expected value metric should take.
    exclusion_type:
      Type of the parseable entity, depending on it additional data might
      be fetched from the repository.
  """

  def __init__(
    self, expression: str, exclusion_type: enums.ExclusionTypeEnum
  ) -> None:
    """Constructor for the class.

    Args:
      expression: Exclusion expression in a form of `name > value`.
      exclusion_type: Type of the exclusion.
    """
    elements = [
      element.strip() for element in expression.split(' ', maxsplit=2)
    ]
    if len(elements) != 3:
      raise ValueError("Incorrect expression, specify in 'name > value' format")
    if elements[1] not in (
      '>',
      '>=',
      '<',
      '<=',
      '=',
      '!=',
      'regexp',
      'contains',
    ):
      raise ValueError(
        'Incorrect operator for expression, '
        "only '>', '>=', '<', '<=', '=', '!=', 'regexp', 'contains' ",
      )

    self.name = elements[0]
    self.operator = '==' if elements[1] == '=' else elements[1]
    self.__raw_value = elements[2].replace("'", '').replace('"', '')
    if self.__raw_value.lower() == 'true':
      self.value = True
    elif self.__raw_value.lower() == 'false':
      self.value = False
    else:
      self.value = self.__raw_value
    self.exclusion_type = exclusion_type

  def is_satisfied_by(self, placement_info: report.GaarfRow) -> bool:
    """Verifies whether given entity satisfies stored expression.

    Args:
      placement_info: GaarfRow object that contains entity data.

    Returns:
      Tuple with results of evaluation and all necessary information on
      placement (formatted as a dict).
    """
    if not hasattr(placement_info, self.name):
      raise ValueError(f'{placement_info} has no {self.name} attribute!')
    if (
      hasattr(placement_info, 'is_processed')
      and not placement_info.is_processed
    ):
      logging.debug(
        'Cannot get internal information on %s entity of type %s',
        placement_info.entity,
        placement_info.entity_type,
      )
      return False, {}
    if self.operator in ('regexp', 'contains'):
      return self._check_regexp(placement_info)
    return self._eval_expression(placement_info)

  def _check_regexp(self, placement: report.GaarfRow) -> bool:
    if placement_element := getattr(placement, self.name):
      return bool(
        re.search(
          rf'{self.value}',
          re.sub(r'[,.;@#?!&$]+', '', placement_element),
          re.IGNORECASE,
        )
      )
    return False

  def _eval_expression(self, placement):
    try:
      value = float(self.value)
    except ValueError:
      value = self.value
    if isinstance(value, float):
      return eval(
        f'{self._nan_to_zero(getattr(placement, self.name))}{self.operator} {value}'
      )
    return getattr(placement, self.name) == value

  def _nan_to_zero(self, value: str) -> float | str:
    return 0.0 if math.isnan(value) else value

  def __str__(self):
    return (
      f'{self.exclusion_type.name}:{self.name} {self.operator} {self.value}'
    )

  def __repr__(self):
    return (
      f'{self.__class__.__name__}'
      f"(exclusion_type='{self.exclusion_type.name}', "
      f"name='{self.name}', "
      f"operator='{self.operator}', value='{self.value}')"
    )

  def __eq__(self, other):
    return (self.exclusion_type, self.name, self.operator, self.value) == (
      other.exclusion_type,
      other.name,
      other.operator,
      other.value,
    )


class AdsExclusionSpecificationEntry(BaseExclusionSpecificationEntry):
  """Stores Google Ads specific rules."""

  def __init__(self, expression):
    super().__init__(
      expression, exclusion_type=enums.ExclusionTypeEnum.GOOGLE_ADS_INFO
    )


class ContentExclusionSpecificationEntry(BaseExclusionSpecificationEntry):
  """Stores Website specific rules."""

  def __init__(self, expression) -> None:
    super().__init__(
      expression=expression, exclusion_type=enums.ExclusionTypeEnum.WEBSITE_INFO
    )


class YouTubeChannelExclusionSpecificationEntry(
  BaseExclusionSpecificationEntry
):
  """Stores YouTube Channel specific rules."""

  def __init__(self, expression) -> None:
    super().__init__(
      expression=expression,
      exclusion_type=enums.ExclusionTypeEnum.YOUTUBE_CHANNEL_INFO,
    )


class YouTubeVideoExclusionSpecificationEntry(BaseExclusionSpecificationEntry):
  """Stores YouTube Video specific rules."""

  def __init__(self, expression) -> None:
    super().__init__(
      expression=expression,
      exclusion_type=enums.ExclusionTypeEnum.YOUTUBE_VIDEO_INFO,
    )


def create_exclusion_specification_entry(
  specification_type: str, condition: str
) -> BaseExclusionSpecificationEntry:
  """Builds concrete specification entry class based on type.

  Args:
    specification_type: Type of desired specification entry.
    condition: Expression to use for building the specification entry.

  Returns:
    Any subclass of instance of BaseExclusionSpecificationEntry.
  """
  if specification_type == 'GOOGLE_ADS_INFO':
    return AdsExclusionSpecificationEntry(condition)
  if specification_type == 'WEBSITE_INFO':
    return ContentExclusionSpecificationEntry(condition)
  if specification_type == 'YOUTUBE_CHANNEL_INFO':
    return YouTubeChannelExclusionSpecificationEntry(condition)
  if specification_type == 'YOUTUBE_VIDEO_INFO':
    return YouTubeVideoExclusionSpecificationEntry(condition)
  raise ValueError(f'Incorrect type of rule: {specification_type}')


class ExclusionSpecification:
  """Verifies whether entities matches set of specification entries.

  Attributes:
    specifications: All specification entries within the specification.
  """

  def __init__(
    self,
    specifications: Sequence[Sequence[BaseExclusionSpecificationEntry]]
    | None = None,
  ) -> None:
    """Initializes ExclusionSpecification.

    Args:
      specifications: All specification entries within the specification.
    """
    self.specifications = specifications

  def apply_specifications(
    self,
    entities: report.GaarfReport,
    include_reason: bool = True,
    include_matching_entity: bool = True,
  ) -> report.GaarfReport:
    """Gets entities that satisfy exclusion specifications entries.

    Args:
      entities:
        Report to be checked against specifications.
      include_reason:
        Whether to include exclusion reason to output report.
      include_matching_entity:
        Whether to include matching placement to output report.

    Returns:
      Report filtered to entities that matches all
      specification entries.
    """
    if not self.specifications and not include_matching_entity:
      return entities
    to_be_excluded_entities = []
    for entity in entities:
      if reason := self.satisfies(entity):
        if include_reason:
          entity['reason'] = ','.join(list(itertools.chain(*reason)))
          if include_matching_entity:
            if hasattr(entity, 'extra_info') and entity.extra_info:
              entity['extra_info'] = entity.extra_info.to_dict()
            else:
              entity['extra_info'] = {}
        to_be_excluded_entities.append(entity.data)
    return report.GaarfReport(
      results=to_be_excluded_entities,
      column_names=entities.column_names,
    )

  def satisfies(self, placement: report.GaarfRow) -> list[str]:
    """Verifies whether a single entity satisfies the specifications.

    Args:
      placement: GaarfRow object with placement data.

    Returns:
      Tuple with list of rules that placement satisfies and
      placement itself.
    """
    rules_satisfied: list[str] = []
    for spec_entry in self.specifications:
      spec_satisfied: list[str] = []
      for spec in spec_entry:
        if spec.exclusion_type != enums.ExclusionTypeEnum.GOOGLE_ADS_INFO:
          formatted_exclusion_type = spec.exclusion_type.name.replace(
            '_INFO', ''
          )
          if formatted_exclusion_type != placement.placement_type:
            continue
          if not placement.extra_info:
            continue
          placement_to_check = placement.extra_info
        else:
          placement_to_check = placement
        if spec.is_satisfied_by(placement_to_check):
          spec_satisfied.append(str(spec))
          continue
      if len(spec_satisfied) == len(spec_entry):
        rules_satisfied.append(spec_satisfied)
    return rules_satisfied

  @property
  def ads_specs_entries(self) -> ExclusionSpecification:
    """Specification filtered to Ads specific specification entries."""
    return self._get_specification_subset(
      include_exclusion_types={
        enums.ExclusionTypeEnum.GOOGLE_ADS_INFO,
      }
    )

  @property
  def non_ads_specs_entries(self) -> ExclusionSpecification:
    """Specification filtered to non-Ads specific specification entries."""
    return self._get_specification_subset(
      exclude_exclusion_types={
        enums.ExclusionTypeEnum.GOOGLE_ADS_INFO,
      }
    )

  def _get_specification_subset(
    self,
    include_exclusion_types: set[enums.ExclusionTypeEnum] | None = None,
    exclude_exclusion_types: set[enums.ExclusionTypeEnum] | None = None,
  ) -> ExclusionSpecification:
    """Builds new specification from a subset.

    Args:
      include_exclusion_types:
        Set of exclusion to include into new specifications.
      exclude_exclusion_types:
        Set of exclusion to include from new specifications.

    Returns:
      New ExclusionSpecification.
    """
    if not self.specifications:
      return ExclusionSpecification()
    specifications: list[list[BaseExclusionSpecificationEntry]] = []
    if include_exclusion_types:
      allowed_exclusion_types = include_exclusion_types
    else:
      exclude_exclusion_types = exclude_exclusion_types or set()
      allowed_exclusion_types = set(enums.ExclusionTypeEnum).difference(
        exclude_exclusion_types
      )
    for specification in self.specifications:
      matching_specification = []
      for specification_entry in specification:
        if specification_entry.exclusion_type in allowed_exclusion_types:
          matching_specification.append(specification_entry)
      if matching_specification:
        specifications.append(matching_specification)
    return ExclusionSpecification(specifications=specifications)

  def define_runtime_options(self) -> RuntimeOptions:
    """Generates runtime options based on provided specifications."""
    if not self.specifications:
      return RuntimeOptions()
    is_conversion_query = False
    conversion_name = ''
    conversion_rules: list[BaseExclusionSpecificationEntry] = []
    for specification in self.specifications:
      for rule in specification:
        if rule.name == 'conversion_name':
          is_conversion_query = True
          conversion_name = rule.value
          conversion_rules.append(rule)
    return RuntimeOptions(
      is_conversion_query=is_conversion_query,
      conversion_name=conversion_name,
      conversion_rules=conversion_rules,
    )

  @classmethod
  def from_rules(
    cls, parsed_rules: list[list[rules_parser.Rule]] | None
  ) -> ExclusionSpecification:
    """Convert Exclusion rules into specifications."""
    if not parsed_rules:
      return ExclusionSpecification()
    specifications = []
    for rules in parsed_rules:
      specification_entry = []
      for rule in rules:
        specification_entry.append(
          create_exclusion_specification_entry(
            rule.exclusion_type, rule.exclusion_rule
          )
        )
      specifications.append(specification_entry)
    return ExclusionSpecification(specifications)

  @classmethod
  def from_expression(cls, rule_expression: str) -> ExclusionSpecification:
    """Convert raw string rules into specifications."""
    return ExclusionSpecification.from_rules(
      rules_parser.generate_rules(rule_expression)
    )

  def __eq__(self, other) -> bool:
    return self.specifications == other.specifications

  def __bool__(self) -> bool:
    return bool(self.specifications)
