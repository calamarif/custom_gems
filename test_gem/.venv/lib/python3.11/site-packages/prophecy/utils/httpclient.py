import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import gzip
import json


class HTTPClientError(Exception):
    """Custom exception for HTTP client errors"""

    pass


class HttpClientLib:
    def __init__(self, base_url: str, token: str = ""):
        # Store provided base_url and token as instance variables
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504]
        )

        # Configure the adapter with retry strategy and pooling
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=5,
            pool_block=True,
        )

        # Mount the adapter for both HTTP and HTTPS
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set default headers
        session.headers.update(
            {"Accept": "application/json", "Authorization": f"Bearer {self.token}"}
        )

        # Set default timeout for all requests (Note: requests.Session does not use a default timeout)
        session.timeout = (10, 30)  # (connect timeout, read timeout)

        return session

    def _handle_response(self, response: requests.Response) -> str:
        """Handle the HTTP response and return the response body"""
        try:
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            raise HTTPClientError(f"HTTP Request failed: {str(e)}") from e

    def _build_url(self, endpoint: str) -> str:
        """Build the full URL from the endpoint"""
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    def get(self, endpoint: str) -> str:
        """
        Execute a GET request
        Args:
            endpoint: The API endpoint to call
        Returns:
            The response body as a string
        Raises:
            HTTPClientError: If the request fails
        """
        try:
            response = self.session.get(self._build_url(endpoint))
            return self._handle_response(response)
        except Exception as e:
            raise HTTPClientError(f"GET request failed: {str(e)}") from e

    def post(self, endpoint: str, body: str) -> str:
        """
        Execute a POST request
        Args:
            endpoint: The API endpoint to call
            body: The request body as a string
        Returns:
            The response body as a string
        Raises:
            HTTPClientError: If the request fails
        """
        try:
            response = self.session.post(
                self._build_url(endpoint),
                data=body,
                headers={"Content-Type": "application/json"},
            )
            return self._handle_response(response)
        except Exception as e:
            raise HTTPClientError(f"POST request failed: {str(e)}") from e

    def post_compressed(self, endpoint: str, body: str) -> str:
        """
        Execute a POST request with gzipped body
        Args:
            endpoint: The API endpoint to call
            body: The request body as a string
        Returns:
            The response body as a string
        Raises:
            HTTPClientError: If the request fails
        """
        try:
            compressed_data = gzip.compress(body.encode("utf-8"))
            response = self.session.post(
                self._build_url(endpoint),
                data=compressed_data,
                headers={
                    "Content-Type": "application/json",
                    "Content-Encoding": "gzip",
                },
            )
            return self._handle_response(response)
        except Exception as e:
            raise HTTPClientError(f"Compressed POST request failed: {str(e)}") from e

    def close(self):
        """Close the session explicitly"""
        self.session.close()

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures session is closed"""
        self.close()


class ProphecyRequestsLib:

    @staticmethod
    def ping(base_url: str, endpoint: str, token: str = ""):
        try:
            print(f"Prophecy Base URL: {base_url}")
            with HttpClientLib(base_url, token) as client:
                response = client.get(endpoint)
                print(f"Ping Response: {response}")
        except HTTPClientError as e:
            print(f"Ping Request Failed: {str(e)}")

    @staticmethod
    def send_diff_dataframe_payload(
        base_url: str,
        key: str,
        job: str,
        endpoint: str,
        token: str = "",
        df_offset: int = 0,
    ):
        from .datasampleloader import DataSampleLoaderLib

        try:
            payload = DataSampleLoaderLib.get_payload(key, job, df_offset)
            with HttpClientLib(base_url, token) as client:
                response = client.post_compressed(endpoint, payload or '')
        except HTTPClientError as e:
            print(f"Interims Request Failed HTTPClientError: {str(e)}. Payload: {payload} Endpoint: {endpoint}")
        except Exception as e:
            print(f"Interims Request Failed: {str(e)}")
