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

"""Module for performing parsing of web pages."""

from __future__ import annotations

import asyncio
import collections
import dataclasses

import aiohttp
import bs4

from googleads_housekeeper.domain.external_parsers import base_parser


@dataclasses.dataclass
class WebsiteInfo(base_parser.EntityInfo):
  """Contains meta information of websites.

  Attributes:
      placement: URL of website's domain.
      title: Title of website.
      description: Website description from 'meta' tags.
      keywords: Website keywords from 'meta' tags.
      is_processed: Whether website was successfully parsed.
  """

  placement: str
  title: str = ''
  description: str = ''
  keywords: str = ''
  is_processed: bool = True


class WebSiteParser(base_parser.BaseParser):
  """Performs website parsing."""

  def parse(
    self, placements: collections.abc.Sequence[str]
  ) -> list[WebsiteInfo]:
    """Parses provided websites.

    Args:
        placements: Sequence of website domains.

    Returns:
        Parsed information in WebsiteInfo format.
    """
    return asyncio.run(self._parse_placements(placements))

  async def _parse_placements(
    self, placements: collections.abc.Sequence[str]
  ) -> list[WebsiteInfo]:
    """Parses provided websites asynchronously.

    Args:
        placements: Sequence of website domains.

    Returns:
        Parsed information in WebsiteInfo format.
    """
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
      results = []
      for placement in placements:
        results.append(self._parse_placement(placement, session))
      values = await asyncio.gather(*results)
    return values

  async def _parse_placement(
    self, placement: str, session: aiohttp.ClientSession
  ) -> WebsiteInfo:
    """Parses single website.

    Args:
        placement: Website domain.

    Returns:
        Parsed information in WebsiteInfo format.
    """
    url = self._convert_placement_to_url(placement)
    try:
      html = await self._fetch_html(url, session)
      placement_info = await self._extract_from_html(placement, html)
      return placement_info
    except Exception:
      return WebsiteInfo(placement=placement, is_processed=False)

  def _convert_placement_to_url(self, placement: str) -> str:
    """Normalizes url."""
    if 'http' not in placement:
      url = f'https://{placement}'
    else:
      url = placement
    return url

  async def _fetch_html(self, url: str, session: aiohttp.ClientSession):
    """Gets website content."""
    response = await session.request(method='GET', url=url)
    response.raise_for_status()
    html = await response.text()
    return html

  async def _extract_from_html(self, url: str, html: str) -> WebsiteInfo:
    """Extracts tags from html."""
    soup = bs4.BeautifulSoup(html, 'html.parser')
    keywords = soup.find('meta', attrs={'name': 'keywords'})
    description = soup.find('meta', attrs={'name': 'description'})
    return WebsiteInfo(
      placement=url,
      title=soup.title.string if soup.title else None,
      keywords=keywords.get('content') if keywords else None,
      description=description.get('content') if description else None,
      is_processed=True,
    )
