"""
Classes
~~~~~~~

"""
import logging
import re

import google.auth.transport.requests
from google.cloud import asset_v1

_LOGGER = logging.getLogger(__name__)

_GCP_PROJECT_NUM_REGEX = (
    r"^//cloudresourcemanager.googleapis.com/(?P<project_id>projects/[0-9]{5,20}$)"
)


class Client:
    """Instantiates a Client object for further API calls.

    .. code:: python

        from bibt.gcp import asset

        client = asset.Client(os.environ["GCP_ORG_ID"])
        asset = client.get_asset(...)

    :type gcp_org_id: :py:class:`str`
    :param gcp_org_id: your GCP organization ID.
        needed to query the Cloud Asset Inventory API.

    :type credentials: :py:class:`google_auth:google.oauth2.credentials.Credentials`
    :param credentials: the credentials object to use when making API calls, if not
        using the account running the function for authentication.
    """

    def __init__(self, gcp_org_id, credentials=None):
        self._client = asset_v1.AssetServiceClient(credentials=credentials)
        self.gcp_org_id = gcp_org_id

    def _ensure_valid_client(self):
        if not self._client._transport._credentials.valid:
            logging.info(
                "Refreshing client credentials, token expired: "
                f"[{self._client._transport._credentials.expiry}]"
            )
            request = google.auth.transport.requests.Request()
            self._client._transport._credentials.refresh(request=request)
            logging.info(
                f"New expiration: [{self._client._transport._credentials.expiry}]"
            )
        return

    def list_assets(self, parent, asset_types=None, content_type=None, page_size=1000):
        """List assets from the CAI API. For more information, view
            `the documentation <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/assets/list>`__.

        :type parent: :py:class:`str`
        :param parent: the parent resource to search under. Can be one of:
            ``organizations/1234``, ``folders/1234``, ``projects/1234``,
            or ``projects/name``.

        :type asset_types: :py:class:`list`
        :param asset_types: a list of asset types to return, in the format
            ``compute.googleapis.com/Disk`` (for example). See
            `here <https://cloud.google.com/asset-inventory/docs/supported-asset-types#searchable_asset_types>`__
            for all supported types.

        :type content_type: :py:class:`str`
        :param content_type: the type of data to return. usually you'll want
            ``RESOURCE``, but can be any value from
            `here <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/feeds#ContentType>`__.

        :type page_size: :py:class:`int`
        :param page_size: the number of results to return per page. a lower number will
            result in more API calls.

        :rtype: `ListAssetsPager <https://cloud.google.com/python/docs/reference/cloudasset/latest/google.cloud.asset_v1.services.asset_service.pagers.ListAssetsPager>`__
        :returns: a pager which may be iterated on to retrieve results. contains
            `Asset <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/Asset>`__ objects.
        """  # noqa E501
        _LOGGER.info(
            "Building list_assets request with parent "
            f"[{parent}] and type {asset_types}"
        )
        request = {
            "parent": parent,
            "read_time": None,
            "page_size": page_size,
        }
        if type(asset_types) is not list and asset_types is not None:
            asset_types = [asset_types]
        if asset_types is not None:
            request["asset_types"] = asset_types
        if content_type is not None:
            request["content_type"] = content_type

        _LOGGER.debug(f"Request: {request}")
        self._ensure_valid_client()
        result = self._client.list_assets(request=request)
        if len(result.assets) < 1:
            _LOGGER.warning(f"No assets returned for list_assets({request})")
        return result

    def get_asset(self, scope, asset_name, asset_types=None, detailed=True):
        """Get a specific asset by name from the CAI API.

        :type scope: :py:class:`str`
        :param scope: the parent resource to search under. Can be one of: ``organizations/1234``,
            ``folders/1234``, ``projects/1234``, or ``projects/name``.

        :type asset_name: :py:class:`str`
        :param asset_name: the name of the asset, in the form of ``//cloudsql.googleapis.com/projects/my-project/instances/my-db``.

        :type asset_types: :py:class:`list`
        :param asset_types: a list of asset types to return, in the format ``compute.googleapis.com/Disk`` (for example).
            See `here <https://cloud.google.com/asset-inventory/docs/supported-asset-types#searchable_asset_types>`__
            for all supported types.

        :type detailed: :py:class:`bool`
        :param detailed: if true, will get the full resource metadata from a ``list_assets`` call, otherwise
            just returns basic metadata from ``search_assets``.

        :rtype: `Asset <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/Asset>`__
        :returns: an asset object (or ``None``).
        """  # noqa E501
        _LOGGER.info(
            f"Searching for asset: {asset_name} under scope "
            f"{scope} with type {asset_types}"
        )
        search_str = self._generate_asset_search_str(asset_name)
        _LOGGER.debug(f"Searching: {search_str}")
        result = self.search_assets(
            scope,
            search_str,
            asset_types=asset_types,
            page_size=1,
        )
        if len(result.results) > 0:
            asset = result.results[0]
        else:
            _LOGGER.warning(
                f"No asset returned for {search_str} under scope "
                f"{scope} with type {asset_types}"
            )
            asset = None
        if asset and detailed:
            _LOGGER.info("Getting detailed metadata from list_assets endpoint...")
            for _asset in self.list_assets(
                asset.project,
                asset_types=[asset.asset_type],
                content_type="RESOURCE",
                page_size=10,
            ):
                if _asset.name == asset.name:
                    _LOGGER.debug(f"Match found on {asset.name}")
                    asset = _asset
                    break
                else:
                    _LOGGER.debug(f"Does not match: {_asset.name} != {asset.name}")
        return asset

    def get_parent_project(self, scope, asset):
        """For a given scope and asset, attempts to retrieve the parent project. If a project, folder,
        or organization is passed, simply returns that.

        :type scope: :py:class:`str`
        :param scope: the parent resource to search under. Can be one of: ``organizations/1234``,
            ``folders/1234``, ``projects/1234``, or ``projects/name``.

        :type asset: `Asset <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/Asset>`__
        :param asset: the asset object for which to return the parent.

        :rtype: `Asset <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/Asset>`__
        :returns: an asset object representing a project, folder, or organization (or ``None``).
        """  # noqa E501
        _LOGGER.info(
            f"Trying to get parent project of {asset.name} using scope {scope}"
        )
        if (asset.asset_type == "cloudresourcemanager.googleapis.com/Folder") or (
            asset.asset_type == "cloudresourcemanager.googleapis.com/Organization"
        ):
            raise Exception(
                "Parent project cannot be retrieved for folders or organizations!"
            )
        if asset.asset_type == ("cloudresourcemanager.googleapis.com/Project"):
            return asset
        try:
            _LOGGER.debug(
                "Trying to get parent project using asset.project attribute..."
            )
            return self.search_assets(
                scope,
                f'project="{asset.project}"',
                asset_types=["cloudresourcemanager.googleapis.com/Project"],
                page_size=1,
            ).results[0]
        except Exception as e:
            _LOGGER.debug(f"That didn't work: {type(e).__name__}: {e}")
            pass

        _LOGGER.debug(
            "Trying to get parent project using "
            "asset.parent_full_resource_name attribute..."
        )
        search_str = self._generate_asset_search_str(asset.parent_full_resource_name)
        _LOGGER.debug(f"Searching: {search_str}")
        parent = self.search_assets(
            scope,
            search_str,
            asset_types=[asset.parent_asset_type],
            page_size=1,
        )
        if len(parent.results) > 0:
            return self.get_parent_project(scope, parent.results[0])
        _LOGGER.warning(f'No asset returned for get_parent_project({asset})")')
        return None

    def search_assets(
        self, scope, query, asset_types=None, order_by=None, page_size=1000
    ):
        """Search assets from the CAI API. This provides minimal asset metadata, use ``list_assets`` for full information.
        For more information, view `the documentation <https://cloud.google.com/asset-inventory/docs/searching-resources#search_resources>`__.

        :type scope: :py:class:`str`
        :param scope: the parent resource to search under. Can be one of: ``organizations/1234``,
            ``folders/1234``, ``projects/1234``, or ``projects/name``.

        :type query: :py:class:`str`
        :param query: an asset query, see `here <https://cloud.google.com/asset-inventory/docs/query-syntax>`__
            for more information.

        :type asset_types: :py:class:`list`
        :param asset_types: a list of asset types to return, in the format ``compute.googleapis.com/Disk`` (for example).
            See `here <https://cloud.google.com/asset-inventory/docs/supported-asset-types#searchable_asset_types>`__
            for all supported types.

        :type order_by: :py:class:`str`
        :param order_by: the field(s) to order results by. sorting can increase response wait time. view the documentation linked
            above for usable fields.

        :type page_size: :py:class:`int`
        :param page_size: the number of results to return per page. a lower number will result in more API calls.

        :rtype: `SearchAllResourcesPager <https://cloud.google.com/python/docs/reference/cloudasset/latest/google.cloud.asset_v1.services.asset_service.pagers.SearchAllResourcesPager>`__
        :returns: a pager which may be iterated on to retrieve results. contains
            `ResourceSearchResult <https://cloud.google.com/python/docs/reference/cloudasset/latest/google.cloud.asset_v1.types.ResourceSearchResult>`__ objects.
        """  # noqa E501
        _LOGGER.info(
            f"Searching assets with scope {scope} query "
            f"[{query}] asset_types = {asset_types}"
        )
        request = {
            "scope": scope,
            "query": query,
            "page_size": page_size,
        }
        if type(asset_types) is not list and asset_types is not None:
            asset_types = [asset_types]
        if asset_types is not None:
            request["asset_types"] = asset_types
        if order_by is not None:
            request["order_by"] = order_by
        _LOGGER.debug(f"Request: {request}")
        self._ensure_valid_client()
        result = self._client.search_all_resources(request)
        if len(result.results) < 1:
            _LOGGER.warning(f"No assets returned for search_assets({request})")
        return result

    def search_asset_iam_policy(self, scope, query):
        """Search IAM policies from the CAI API.
        For more information, view `the documentation <https://cloud.google.com/asset-inventory/docs/searching-iam-policies#search_policies>`__.

        :type scope: :py:class:`str`
        :param scope: the parent resource to search under. Can be one of: ``organizations/1234``,
            ``folders/1234``, ``projects/1234``, or ``projects/name``.

        :type query: :py:class:`str`
        :param query: an asset query, see `here <https://cloud.google.com/asset-inventory/docs/query-syntax>`__
            for more information.

        :rtype: `SearchAllIamPoliciesPager <https://cloud.google.com/python/docs/reference/cloudasset/latest/google.cloud.asset_v1.services.asset_service.pagers.SearchAllIamPoliciesPager>`__
        :returns: a pager which may be iterated on to retrieve results. contains
            `IamPolicySearchResult <https://cloud.google.com/python/docs/reference/cloudasset/latest/google.cloud.asset_v1.types.IamPolicySearchResult>`__ objects.
        """  # noqa E501
        _LOGGER.info(f"Searching IAM policies with scope {scope} and query {query}")
        request = {"scope": scope, "query": query}
        self._ensure_valid_client()
        result = self._client.search_all_iam_policies(request=request)
        if len(result.results) < 1:
            _LOGGER.warning(
                f"No IAM policy returned for search_asset_iam_policy({request})"
            )
        return result

    def _generate_asset_search_str(self, asset_name):
        """Generates a query string for ``get_asset`` based
        on whether or not a project ID is passed.
        """
        match = re.match(_GCP_PROJECT_NUM_REGEX, asset_name)
        if match:
            project_id = match.group("project_id")
            return f'project="{project_id}"'
        return f'name="{asset_name}"'
