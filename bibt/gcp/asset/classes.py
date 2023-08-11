"""
Classes
~~~~~~~

Classes which may be used to handle or interact with the Asset API.

"""
import logging

from google.cloud import asset_v1

_LOGGER = logging.getLogger(__name__)


class Client:
    r"""This class can be used to call methods in this library using the same
    credentials object, cutting down on API authentication flows.
    """

    def __init__(self, gcp_org_id, credentials=None):
        self._client = asset_v1.AssetServiceClient(credentials=credentials)
        self.gcp_org_id = gcp_org_id

    def list_assets(self, parent, asset_types=None, content_type=None, page_size=1000):
        """https://cloud.google.com/asset-inventory/docs/reference/rest/v1/assets/list"""
        _LOGGER.info(
            f"Building list_assets request with parent [{parent}] and type {asset_types}"
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
        result = self._client.list_assets(request=request)
        if len(result.results) < 1:
            _LOGGER.warning(f"No assets returned for list_assets({request})")
        return result

    def get_asset(self, scope, asset_name, asset_types=None, detailed=True):
        _LOGGER.info(
            f"Searching for asset: {asset_name} under scope {scope} with type {asset_types}"
        )
        result = self.search_assets(
            scope, f'name="{asset_name}"', asset_types=asset_types, page_size=1
        )
        if len(result.results) > 0:
            asset = result.results[0]
        else:
            _LOGGER.warning(
                f"No asset returned for {asset_name} under scope {scope} with type {asset_types}"
            )
            asset = None
        if asset and detailed:
            _LOGGER.info(f"Getting detailed metadata from list_assets endpoint...")
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
        _LOGGER.info(
            f"Trying to get parent project of {asset.name} using scope {scope}"
        )
        if (asset.asset_type == "cloudresourcemanager.googleapis.com/Folder") or (
            asset.asset_type == "cloudresourcemanager.googleapis.com/Organization"
        ):
            raise Exception(
                f"Parent project cannot be retrieved for folders or organizations!"
            )
        if asset.asset_type == ("cloudresourcemanager.googleapis.com/Project"):
            return asset
        try:
            _LOGGER.debug(
                f"Trying to get parent project using asset.project attribute..."
            )
            return self.get_asset(
                scope,
                f"//cloudresourcemanager.googleapis.com/{asset.project}",
                asset_types=["cloudresourcemanager.googleapis.com/Project"],
                detailed=False,
            )
        except Exception as e:
            _LOGGER.debug(f"That didn't work: {type(e).__name__}: {e}")
            pass

        _LOGGER.debug(
            f"Trying to get parent project using asset.parent_full_resource_name attribute..."
        )
        parent = self.get_asset(
            scope,
            asset.parent_full_resource_name,
            asset_types=[asset.parent_asset_type],
            detailed=False,
        )
        if parent:
            parent_project = self.get_parent_project(scope, parent)
            if not parent_project:
                _LOGGER.warning(f"No parent project returned for {asset}")
            return parent_project
        _LOGGER.warning(
            f"No asset returned by get_asset({asset.parent_full_resource_name})"
        )
        return None

    def search_assets(
        self, scope, query, asset_types=None, order_by=None, page_size=1000
    ):
        """https://cloud.google.com/asset-inventory/docs/query-syntax
        https://cloud.google.com/asset-inventory/docs/searching-resources#search_resources
        https://cloud.google.com/asset-inventory/docs/supported-asset-types#searchable_asset_types
        """
        _LOGGER.info(
            f"Searching assets with scope {scope} query [{query}] asset_types = {asset_types}"
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
        result = self._client.search_all_resources(request)
        if len(result.results) < 1:
            _LOGGER.warning(f"No assets returned for search_assets({request})")
        return result

    def search_asset_iam_policy(self, scope, query):
        """https://cloud.google.com/asset-inventory/docs/query-syntax
        https://cloud.google.com/asset-inventory/docs/searching-iam-policies#search_policies
        https://cloud.google.com/asset-inventory/docs/supported-asset-types#searchable_asset_types
        """
        _LOGGER.info(f"Searching IAM policies with scope {scope} and query {query}")
        request = {"scope": scope, "query": query}
        result = self._client.search_all_iam_policies(request=request)
        if len(result.results) < 1:
            _LOGGER.warning(
                f"No IAM policy returned for search_asset_iam_policy({request})"
            )
        return result
